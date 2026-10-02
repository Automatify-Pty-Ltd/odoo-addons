from odoo import _, api, fields, models


class AutomatifySocialXSettings(models.TransientModel):
    _name = "automatify.social.x.settings"
    _description = "X Social Settings"

    client_id = fields.Char(string="Client ID", required=True)
    client_secret = fields.Char(
        string="Client Secret",
        help="Optional for public OAuth clients; used for confidential clients when configured.",
    )
    callback_url = fields.Char(string="OAuth Redirect URL", readonly=True)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        params = self.env["ir.config_parameter"].sudo()
        base_url = params.get_param("web.base.url", "").rstrip("/")
        values.update(
            {
                "client_id": params.get_param("automatify_social_x.client_id", ""),
                "client_secret": params.get_param(
                    "automatify_social_x.client_secret", ""
                ),
                "callback_url": (
                    f"{base_url}/automatify-social/x/oauth/callback" if base_url else ""
                ),
            }
        )
        return values

    def action_save(self):
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("automatify_social_x.client_id", self.client_id)
        params.set_param("automatify_social_x.client_secret", self.client_secret or "")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("X settings saved"),
                "message": _(
                    "Add the displayed OAuth Redirect URL to the X Developer App."
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
