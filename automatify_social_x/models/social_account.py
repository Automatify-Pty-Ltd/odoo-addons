import base64
import hashlib
from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode

import requests

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from ..providers.x import XProvider


class AutomatifySocialAccount(models.Model):
    _inherit = "automatify.social.account"

    x_access_token = fields.Char(
        string="X Access Token",
        groups="automatify_social.group_automatify_social_manager",
        copy=False,
    )
    x_refresh_token = fields.Char(
        string="X Refresh Token",
        groups="automatify_social.group_automatify_social_manager",
        copy=False,
        readonly=True,
    )
    x_token_expires_at = fields.Datetime(
        string="X Token Expires", readonly=True, copy=False
    )

    def _social_platform_selection(self):
        values = list(super()._social_platform_selection())
        if ("x", "X") not in values:
            values.append(("x", "X"))
        return values

    def _get_social_provider(self):
        self.ensure_one()
        if self.platform == "x":
            return XProvider()
        return super()._get_social_provider()

    def _x_redirect_uri(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        if not base_url:
            raise UserError(_("Odoo web.base.url is not configured."))
        return f"{base_url.rstrip('/')}/automatify-social/x/oauth/callback"

    def _x_oauth_scopes(self):
        return [
            "tweet.read",
            "tweet.write",
            "users.read",
            "media.write",
            "offline.access",
        ]

    def action_x_connect(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            raise AccessError(_("Only Social Marketing Managers can connect X."))
        if self.platform != "x":
            raise UserError(_("This action is only available for X accounts."))

        client_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("automatify_social_x.client_id")
        )
        if not client_id:
            raise UserError(_("Configure the X Client ID first."))

        state_model = self.env["automatify.social.x.oauth.state"].sudo()
        state_model.search([("expires_at", "<", fields.Datetime.now())]).unlink()
        state = token_urlsafe(32)
        code_verifier = token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        state_model.create(
            {
                "token": state,
                "code_verifier": code_verifier,
                "account_id": self.id,
                "user_id": self.env.user.id,
                "expires_at": fields.Datetime.now() + timedelta(minutes=10),
            }
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": self._x_redirect_uri(),
                "scope": " ".join(self._x_oauth_scopes()),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"https://x.com/i/oauth2/authorize?{query}",
            "target": "self",
        }

    def _x_refresh_access_token(self):
        self.ensure_one()
        if not self.x_refresh_token:
            raise UserError(_("X refresh token is not available; reconnect the account."))
        params = self.env["ir.config_parameter"].sudo()
        client_id = params.get_param("automatify_social_x.client_id")
        client_secret = params.get_param("automatify_social_x.client_secret")
        if not client_id:
            raise UserError(_("X Client ID is not configured."))

        response = requests.post(
            "https://api.x.com/2/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.x_refresh_token,
                "client_id": client_id,
            },
            auth=(client_id, client_secret) if client_secret else None,
            timeout=20,
        )
        if response.status_code != 200:
            detail = (response.text or "")[:800]
            self.write({"connection_state": "error", "last_error": detail})
            raise UserError(
                _("X token refresh failed (%(status)s): %(detail)s")
                % {"status": response.status_code, "detail": detail}
            )
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise UserError(_("X token refresh did not return an access token."))
        expires_in = int(payload.get("expires_in") or 0)
        self.write(
            {
                "x_access_token": access_token,
                "x_refresh_token": payload.get("refresh_token") or self.x_refresh_token,
                "x_token_expires_at": (
                    fields.Datetime.now() + timedelta(seconds=expires_in)
                    if expires_in
                    else False
                ),
                "connection_state": "connected",
                "last_error": False,
            }
        )
        return access_token

    def _x_get_access_token(self):
        self.ensure_one()
        if self.x_access_token and (
            not self.x_token_expires_at
            or self.x_token_expires_at > fields.Datetime.now() + timedelta(minutes=1)
        ):
            return self.x_access_token
        return self._x_refresh_access_token()

    def action_x_disconnect(self):
        if not self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            raise AccessError(_("Only Social Marketing Managers can disconnect X."))
        self.filtered(lambda account: account.platform == "x").write(
            {
                "x_access_token": False,
                "x_refresh_token": False,
                "x_token_expires_at": False,
                "connection_state": "disconnected",
                "last_error": False,
            }
        )
        return True
