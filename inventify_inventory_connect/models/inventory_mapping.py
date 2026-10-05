from odoo import fields, models


class InventifyInventoryMapping(models.Model):
    _name = "inventify.inventory.mapping"
    _description = "Inventify Inventory Mapping"
    _order = "create_date, id"

    connection_id = fields.Many2one(
        "external.app.access.token",
        required=True,
        ondelete="cascade",
        index=True,
    )
    entity_uuid = fields.Char(required=True, index=True)
    entity_type = fields.Char(required=True)
    odoo_model = fields.Selection(
        [("stock.location", "Stock Location"), ("product.product", "Product")],
        required=True,
        index=True,
    )
    odoo_record_id = fields.Integer(required=True, index=True)
    odoo_location_id = fields.Integer(index=True)
    last_synced_at = fields.Datetime()

    _connection_entity_unique = models.Constraint(
        "UNIQUE(connection_id, entity_uuid)",
        "An Inventify entity can have only one mapping per connection.",
    )
