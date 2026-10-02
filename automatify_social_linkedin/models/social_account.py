from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from ..providers.linkedin import LinkedInProvider


class AutomatifySocialAccount(models.Model):
    _inherit = "automatify.social.account"

    linkedin_author_type = fields.Selection(
        selection=[("member", "Personal Profile"), ("organization", "Company Page")],
        string="LinkedIn Author Type",
        default="organization",
    )
    linkedin_access_token = fields.Char(
        string="LinkedIn Access Token",
        groups="automatify_social.group_automatify_social_manager",
        copy=False,
        help="OAuth bearer token. Stored in the trusted self-hosted Odoo database.",
    )
    linkedin_refresh_token = fields.Char(
        string="LinkedIn Refresh Token",
        groups="automatify_social.group_automatify_social_manager",
        copy=False,
        readonly=True,
    )
    linkedin_token_expires_at = fields.Datetime(
        string="LinkedIn Token Expires",
        readonly=True,
        copy=False,
    )
    linkedin_author_urn = fields.Char(
        string="LinkedIn Author URN",
        help="Resolved person or organization URN used as the post author.",
    )
    linkedin_api_version = fields.Char(
        string="LinkedIn API Version",
        default="202609",
        help="LinkedIn Marketing API version header in YYYYMM format.",
    )

    def _social_platform_selection(self):
        values = list(super()._social_platform_selection())
        if ("linkedin", "LinkedIn") not in values:
            values.append(("linkedin", "LinkedIn"))
        return values

    def _get_social_provider(self):
        self.ensure_one()
        if self.platform == "linkedin":
            return LinkedInProvider()
        return super()._get_social_provider()

    def _linkedin_redirect_uri(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if not base_url:
            raise UserError(_("Odoo web.base.url is not configured."))
        return f"{base_url.rstrip('/')}/automatify-social/linkedin/oauth/callback"

    def _linkedin_oauth_scopes(self):
        self.ensure_one()
        if self.linkedin_author_type == "member":
            return ["r_basicprofile", "w_member_social"]
        return ["rw_organization_admin", "w_organization_social"]

    def action_linkedin_connect(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            raise AccessError(_("Only Social Marketing Managers can connect LinkedIn."))
        if self.platform != "linkedin":
            raise UserError(_("This action is only available for LinkedIn accounts."))

        params = self.env["ir.config_parameter"].sudo()
        client_id = params.get_param("automatify_social_linkedin.client_id")
        client_secret = params.get_param("automatify_social_linkedin.client_secret")
        if not client_id or not client_secret:
            raise UserError(
                _("Configure the LinkedIn Client ID and Client Secret first.")
            )

        state_model = self.env["automatify.social.linkedin.oauth.state"].sudo()
        state_model.search([("expires_at", "<", fields.Datetime.now())]).unlink()
        state = token_urlsafe(32)
        state_model.create(
            {
                "token": state,
                "account_id": self.id,
                "user_id": self.env.user.id,
                "expires_at": fields.Datetime.now() + timedelta(minutes=10),
            }
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": self._linkedin_redirect_uri(),
                "state": state,
                "scope": " ".join(self._linkedin_oauth_scopes()),
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"https://www.linkedin.com/oauth/v2/authorization?{query}",
            "target": "self",
        }

    def action_linkedin_disconnect(self):
        if not self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            raise AccessError(_("Only Social Marketing Managers can disconnect LinkedIn."))
        self.filtered(lambda account: account.platform == "linkedin").write(
            {
                "linkedin_access_token": False,
                "linkedin_refresh_token": False,
                "linkedin_token_expires_at": False,
                "connection_state": "disconnected",
                "last_error": False,
            }
        )
        return True
