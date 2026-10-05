from datetime import timedelta

import requests

from odoo import fields, http
from odoo.http import request


class AutomatifySocialXOAuthController(http.Controller):
    token_endpoint = "https://api.x.com/2/oauth2/token"
    me_endpoint = "https://api.x.com/2/users/me"
    timeout = 20

    @staticmethod
    def _account_url(account):
        return (
            f"/web#id={account.id}&model=automatify.social.account&view_type=form"
        )

    @staticmethod
    def _detail(response):
        return (response.text or "")[:800]

    def _fail(self, account, message):
        account.write({"connection_state": "error", "last_error": message})
        return request.redirect(self._account_url(account))

    def _exchange_code(self, account, code, code_verifier):
        params = request.env["ir.config_parameter"].sudo()
        client_id = params.get_param("automatify_social_x.client_id")
        client_secret = params.get_param("automatify_social_x.client_secret")
        response = requests.post(
            self.token_endpoint,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": account._x_redirect_uri(),
                "code_verifier": code_verifier,
            },
            auth=(client_id, client_secret) if client_secret else None,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ValueError(
                f"X token exchange failed ({response.status_code}): {self._detail(response)}"
            )
        payload = response.json()
        if not payload.get("access_token"):
            raise ValueError("X token response did not contain access_token.")
        return payload

    def _resolve_user(self, token):
        response = requests.get(
            self.me_endpoint,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ValueError(
                f"X user lookup failed ({response.status_code}): {self._detail(response)}"
            )
        user = response.json().get("data") or {}
        if not user.get("id") or not user.get("username"):
            raise ValueError("X /2/users/me response did not contain id and username.")
        return user

    @http.route(
        "/automatify-social/x/oauth/callback",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def callback(
        self,
        code=None,
        state=None,
        error=None,
        error_description=None,
        **kwargs,
    ):
        if not state:
            return request.make_response("Missing X OAuth state.", status=400)

        state_model = request.env["automatify.social.x.oauth.state"].sudo()
        state_record = state_model._lock_for_consume(state)
        if not state_record:
            return request.make_response("Invalid X OAuth state.", status=400)
        if state_record.user_id.id != request.env.user.id:
            return request.make_response("X OAuth user mismatch.", status=403)
        if state_record.expires_at < fields.Datetime.now():
            state_record.unlink()
            return request.make_response("X OAuth state expired.", status=400)

        account = state_record.account_id.with_user(request.env.user)
        code_verifier = state_record.code_verifier
        state_record.unlink()

        if error:
            return self._fail(
                account,
                error_description or f"X authorization failed: {error}",
            )
        if not code:
            return self._fail(account, "X did not return an authorization code.")

        try:
            token_payload = self._exchange_code(account, code, code_verifier)
            token = token_payload["access_token"]
            user = self._resolve_user(token)
            expires_in = int(token_payload.get("expires_in") or 0)
            account.write(
                {
                    "x_access_token": token,
                    "x_refresh_token": token_payload.get("refresh_token") or False,
                    "x_token_expires_at": (
                        fields.Datetime.now() + timedelta(seconds=expires_in)
                        if expires_in
                        else False
                    ),
                    "external_account_id": user["id"],
                    "handle": f"@{user['username']}",
                    "connection_state": "connected",
                    "last_error": False,
                    "last_sync_at": fields.Datetime.now(),
                }
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            return self._fail(account, str(exc))

        return request.redirect(self._account_url(account))
