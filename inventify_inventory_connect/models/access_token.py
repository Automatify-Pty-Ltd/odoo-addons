from odoo import fields, models


class ExternalAppAccessToken(models.Model):
    _inherit = "external.app.access.token"

    inventify_root_location_id = fields.Many2one(
        "stock.location",
        string="Inventify root location",
        ondelete="set null",
        copy=False,
        help="Inventory location selected for this Inventify connection. Inventify sync is constrained to this subtree.",
    )
