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
    handle = fields.Char(
        copy=False,
        help="Human-readable page, profile, or account handle.",
    )
    external_account_id = fields.Char(
        string="External Account ID",
        copy=False,
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
        copy=False,
    )
    last_sync_at = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    def _ensure_remote_identity_matches(self, remote_identity):
        self.ensure_one()
        remote_identity = remote_identity or False
        if self.external_account_id and self.external_account_id != remote_identity:
            raise UserError(
                _(
                    "This social account is already bound to a different remote identity. "
                    "Create a separate social account instead of reconnecting it to another "
                    "public profile or page."
                )
            )
        return True

    def write(self, vals):
        if "company_id" in vals:
            new_company_id = vals.get("company_id")
            if any(account.company_id.id != new_company_id for account in self):
                raise UserError(
                    _(
                        "A social account cannot be moved to another company. "
                        "Create a separate social account for the other company so queued and "
                        "historical publications remain bound to their original company."
                    )
                )
        if "platform" in vals:
            new_platform = vals.get("platform")
            if any(account.platform != new_platform for account in self):
                raise UserError(
                    _(
                        "A social account's platform cannot be changed after creation. "
                        "Create a separate social account for the other network so queued and "
                        "historical publications remain bound to their original provider."
                    )
                )
        if "external_account_id" in vals:
            new_external_id = vals.get("external_account_id") or False
            for account in self:
                account._ensure_remote_identity_matches(new_external_id)
        return super().write(vals)

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
