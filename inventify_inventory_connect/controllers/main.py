import json

from odoo import http
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import request


READ_SCOPE = "inventify:inventory:read"
WRITE_SCOPE = "inventify:inventory:write"


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
