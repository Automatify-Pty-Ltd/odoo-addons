from odoo import _, fields, models
from odoo.exceptions import UserError


class AutomatifySocialAccount(models.Model):
    _name = "automatify.social.account"
    _description = "Social Account"
    _order = "platform, name"

    name = fields.Char(required=True, index=True)
    platform = fields.Selection(
        selection=lambda self: self._social_platform_selection(),
        required=True,
        index=True,
        help="Social network provider registered by an installed connector addon.",
    )
    handle = fields.Char(help="Human-readable page, profile, or account handle.")
    external_account_id = fields.Char(
        string="External Account ID",
        help="Provider-side account/page identifier. Credentials live in connector addons.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
    )
    connection_state = fields.Selection(
        selection=[
            ("disconnected", "Disconnected"),
            ("configured", "Configured"),
            ("connected", "Connected"),
            ("error", "Error"),
        ],
        default="disconnected",
        required=True,
        readonly=True,
    )
    last_sync_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    def _social_platform_selection(self):
        """Connector addons extend this selection through normal Odoo inheritance."""
        return []

    def _get_social_provider(self):
        """Return the provider service for this account in the current DB registry."""
        self.ensure_one()
        raise UserError(
            _("No social provider connector is installed for '%(platform)s'.")
            % {"platform": self.platform or "unknown"}
        )
