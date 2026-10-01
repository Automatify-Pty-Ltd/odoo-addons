import json
import uuid

from odoo import fields, http
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.http import request


READ_SCOPE = "inventify:inventory:read"
WRITE_SCOPE = "inventify:inventory:write"
MAX_SYNC_ENTITIES = 200


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
        ],
        status=status,
    )


def _payload():
    value = request.httprequest.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _authenticate(required_scopes):
    return request.env["external.app.access.token"].authenticate_bearer(
        request.httprequest.headers.get("Authorization"),
        required_scopes=set(required_scopes),
    )


def _location_payload(location):
    return {
        "id": location.id,
        "name": location.name,
        "complete_name": location.complete_name,
        "usage": location.usage,
        "company_id": location.company_id.id if location.company_id else None,
    }


def _normalize_entity(raw):
    if not isinstance(raw, dict):
        raise ValidationError("Each entity must be an object.")
    entity_id = str(raw.get("id") or "").strip()
    try:
        uuid.UUID(entity_id)
    except (ValueError, AttributeError):
        raise ValidationError("Entity id must be a UUID.") from None

    parent_id = raw.get("parent_id")
    if parent_id is not None:
        parent_id = str(parent_id).strip()
        try:
            uuid.UUID(parent_id)
        except (ValueError, AttributeError):
            raise ValidationError("Parent id must be a UUID when supplied.") from None

    name = str(raw.get("name") or "").strip()
    entity_type = str(raw.get("type") or "").strip().lower()
    if not name or len(name) > 255:
        raise ValidationError("Entity name must be 1-255 characters.")
    if entity_type not in {"house", "room", "container", "item", "other"}:
        raise ValidationError("Unsupported Inventify entity type.")
    if parent_id == entity_id:
        raise ValidationError("An entity cannot be its own parent.")
    return {
        "id": entity_id,
        "parent_id": parent_id,
        "name": name,
        "type": entity_type,
    }


def _child_counts(entities):
    counts = {}
    for entity in entities:
        parent_id = entity["parent_id"]
        if parent_id:
            counts[parent_id] = counts.get(parent_id, 0) + 1
    return counts


def _maps_to_location(entity, counts):
    if entity["type"] in {"house", "room", "container"}:
        return True
    if entity["type"] == "item":
        return False
    return counts.get(entity["id"], 0) > 0


def _sort_entities(entities):
    by_id = {entity["id"]: entity for entity in entities}
    counts = _child_counts(entities)

    def depth(entity):
        current = entity
        seen = set()
        value = 0
        while current.get("parent_id") and value < 100:
            parent_id = current["parent_id"]
            if parent_id in seen:
                raise ValidationError("Inventify entity hierarchy contains a cycle.")
            seen.add(parent_id)
            parent = by_id.get(parent_id)
            if not parent:
                break
            value += 1
            current = parent
        return value

    return sorted(
        entities,
        key=lambda entity: (
            depth(entity),
            0 if _maps_to_location(entity, counts) else 1,
            entity["name"].casefold(),
            entity["id"],
        ),
    )


def _mapping_dict(token, entity_ids):
    rows = request.env["inventify.inventory.mapping"].sudo().search(
        [("connection_id", "=", token.id), ("entity_uuid", "in", list(entity_ids))]
    )
    return {row.entity_uuid: row for row in rows}


def _nearest_parent_location(entity, by_id, mappings, root_id):
    parent_id = entity["parent_id"]
    seen = set()
    while parent_id and len(seen) < 100:
        if parent_id in seen:
            raise ValidationError("Inventify entity hierarchy contains a cycle.")
        seen.add(parent_id)
        mapping = mappings.get(parent_id)
        if mapping and mapping.odoo_model == "stock.location":
            return mapping.odoo_record_id
        parent = by_id.get(parent_id)
        parent_id = parent["parent_id"] if parent else None
    return root_id


def _record_or_none(model_name, record_id, user):
    if not record_id:
        return request.env[model_name]
    record = request.env[model_name].with_user(user).browse(record_id).exists()
    return record


def _ensure_location(entity, parent_location_id, mapping, user):
    values = {
        "name": entity["name"],
        "usage": "internal",
        "location_id": parent_location_id,
        "company_id": user.company_id.id,
    }
    if mapping and mapping.odoo_model == "stock.location":
        record = _record_or_none("stock.location", mapping.odoo_record_id, user)
        if record:
            record.write(values)
            return record, False
    record = request.env["stock.location"].with_user(user).create(values)
    return record, True


def _ensure_product(entity, mapping, user):
    values = {
        "name": entity["name"],
        "is_storable": True,
        "default_code": "INV-%s" % entity["id"],
    }
    if mapping and mapping.odoo_model == "product.product":
        record = _record_or_none("product.product", mapping.odoo_record_id, user)
        if record:
            record.write(values)
            return record, False
    record = request.env["product.product"].with_user(user).create(values)
    return record, True


def _set_inventory_count(product_id, location_id, count, user):
    quant_model = request.env["stock.quant"].with_user(user).with_context(inventory_mode=True)
    quant = quant_model.search(
        [("product_id", "=", product_id), ("location_id", "=", location_id)],
        limit=1,
    )
    if not quant and count == 0:
        return
    if quant and float(quant.quantity) == float(count):
        return
    if quant:
        quant.write({"inventory_quantity": count})
    else:
        quant = quant_model.create(
            {
                "product_id": product_id,
                "location_id": location_id,
                "inventory_quantity": count,
            }
        )
    quant.with_context(inventory_mode=True).action_apply_inventory()


def _write_mapping(token, entity, model_name, record_id, location_id=None):
    mapping_model = request.env["inventify.inventory.mapping"].sudo()
    mapping = mapping_model.search(
        [("connection_id", "=", token.id), ("entity_uuid", "=", entity["id"])],
        limit=1,
    )
    values = {
        "connection_id": token.id,
        "entity_uuid": entity["id"],
        "entity_type": entity["type"],
        "odoo_model": model_name,
        "odoo_record_id": record_id,
        "odoo_location_id": location_id or False,
        "last_synced_at": fields.Datetime.now(),
    }
    if mapping:
        mapping.write(values)
        return mapping
    return mapping_model.create(values)


class InventifyInventoryConnectController(http.Controller):
    @http.route(
        "/inventify-connect/api/v1/connection",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def connection(self, **_kwargs):
        try:
            token = _authenticate({READ_SCOPE})
        except AccessDenied:
            return _json_response({"error": "invalid_token"}, status=401)

        user = token.user_id
        root = token.inventify_root_location_id
        return _json_response(
            {
                "connected": True,
                "user": {"id": user.id, "name": user.name},
                "company": {"id": user.company_id.id, "name": user.company_id.name},
                "client_id": token.client_id.client_id,
                "scope": token.scope.split(),
                "root_location": _location_payload(root) if root else None,
            }
        )

    @http.route(
        "/inventify-connect/api/v1/locations",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def locations(self, **_kwargs):
        try:
            token = _authenticate({READ_SCOPE})
            user = token.user_id
            warehouse_model = request.env["stock.warehouse"].with_user(user)
            location_model = request.env["stock.location"].with_user(user)

            warehouses = warehouse_model.search(
                [("company_id", "=", user.company_id.id)], order="name, id", limit=100
            )
            locations = location_model.search(
                [
                    ("company_id", "in", [False, user.company_id.id]),
                    ("usage", "in", ["view", "internal"]),
                ],
                order="complete_name, id",
                limit=500,
            )
        except AccessDenied:
            return _json_response({"error": "invalid_token"}, status=401)
        except AccessError:
            return _json_response(
                {
                    "error": "inventory_permission_required",
                    "message": "The connected Odoo user needs Inventory access.",
                },
                status=403,
            )

        return _json_response(
            {
                "warehouses": [
                    {
                        "id": warehouse.id,
                        "name": warehouse.name,
                        "code": warehouse.code,
                        "view_location_id": warehouse.view_location_id.id,
                        "stock_location_id": warehouse.lot_stock_id.id,
                    }
                    for warehouse in warehouses
                ],
                "locations": [_location_payload(location) for location in locations],
                "selected_root_location_id": token.inventify_root_location_id.id
                if token.inventify_root_location_id
                else None,
            }
        )

    @http.route(
        "/inventify-connect/api/v1/settings",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def settings(self, **_kwargs):
        try:
            token = _authenticate({WRITE_SCOPE})
        except AccessDenied:
            return _json_response({"error": "invalid_token"}, status=401)

        body = _payload()
        try:
            root_location_id = int(body.get("root_location_id"))
        except (TypeError, ValueError):
            return _json_response({"error": "invalid_root_location"}, status=400)

        user = token.user_id
        try:
            root = request.env["stock.location"].with_user(user).search(
                [
                    ("id", "=", root_location_id),
                    ("company_id", "in", [False, user.company_id.id]),
                    ("usage", "in", ["view", "internal"]),
                ],
                limit=1,
            )
        except AccessError:
            return _json_response(
                {
                    "error": "inventory_permission_required",
                    "message": "The connected Odoo user needs Inventory access.",
                },
                status=403,
            )

        if not root:
            return _json_response({"error": "invalid_root_location"}, status=400)

        token.sudo().write({"inventify_root_location_id": root.id})
        return _json_response(
            {
                "configured": True,
                "root_location": _location_payload(root),
            }
        )

    @http.route(
        "/inventify-connect/api/v1/sync",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def sync(self, **_kwargs):
        try:
            token = _authenticate({WRITE_SCOPE})
        except AccessDenied:
            return _json_response({"error": "invalid_token"}, status=401)

        if not token.inventify_root_location_id:
            return _json_response(
                {
                    "error": "root_location_required",
                    "message": "Choose an Odoo Inventory root location before syncing.",
                },
                status=409,
            )

        raw_entities = _payload().get("entities")
        if not isinstance(raw_entities, list) or not raw_entities:
            return _json_response({"error": "entities_required"}, status=400)
        if len(raw_entities) > MAX_SYNC_ENTITIES:
            return _json_response({"error": "too_many_entities", "max": MAX_SYNC_ENTITIES}, status=400)

        try:
            entities = [_normalize_entity(raw) for raw in raw_entities]
            if len({entity["id"] for entity in entities}) != len(entities):
                raise ValidationError("Duplicate Inventify entity ids are not allowed.")
            ordered = _sort_entities(entities)
        except ValidationError as error:
            return _json_response({"error": "invalid_entities", "message": str(error)}, status=400)

        user = token.user_id
        by_id = {entity["id"]: entity for entity in entities}
        counts = _child_counts(entities)
        mappings = _mapping_dict(token, by_id.keys())
        root_id = token.inventify_root_location_id.id
        result = {
            "total": len(entities),
            "synced": 0,
            "created": 0,
            "updated": 0,
            "failed": 0,
            "failures": [],
        }

        for entity in ordered:
            try:
                mapping = mappings.get(entity["id"])
                parent_location_id = _nearest_parent_location(entity, by_id, mappings, root_id)
                if _maps_to_location(entity, counts):
                    if mapping and mapping.odoo_model != "stock.location":
                        raise ValidationError("Entity changed between item and location; reconnect or remove its old mapping first.")
                    record, created = _ensure_location(entity, parent_location_id, mapping, user)
                    new_mapping = _write_mapping(
                        token,
                        entity,
                        "stock.location",
                        record.id,
                    )
                else:
                    if mapping and mapping.odoo_model != "product.product":
                        raise ValidationError("Entity changed between location and item; reconnect or remove its old mapping first.")
                    record, created = _ensure_product(entity, mapping, user)
                    old_location_id = mapping.odoo_location_id if mapping else None
                    if old_location_id and old_location_id != parent_location_id:
                        _set_inventory_count(record.id, old_location_id, 0, user)
                    _set_inventory_count(record.id, parent_location_id, 1, user)
                    new_mapping = _write_mapping(
                        token,
                        entity,
                        "product.product",
                        record.id,
                        parent_location_id,
                    )
                mappings[entity["id"]] = new_mapping
                result["synced"] += 1
                result["created" if created else "updated"] += 1
            except (AccessError, UserError, ValidationError) as error:
                request.env.cr.rollback()
                result["failed"] += 1
                result["failures"].append(
                    {"entityId": entity["id"], "message": str(error)[:300]}
                )
                mappings = _mapping_dict(token, by_id.keys())
            except Exception:
                request.env.cr.rollback()
                result["failed"] += 1
                result["failures"].append(
                    {"entityId": entity["id"], "message": "Unexpected Odoo Inventory error."}
                )
                mappings = _mapping_dict(token, by_id.keys())

        return _json_response(result)
