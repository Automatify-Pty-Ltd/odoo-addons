from datetime import timedelta

import requests

from odoo import fields, http
from odoo.http import request


class AutomatifySocialLinkedInOAuthController(http.Controller):
    token_endpoint = "https://www.linkedin.com/oauth/v2/accessToken"
    member_endpoint = "https://api.linkedin.com/v2/me"
    organization_acl_endpoint = "https://api.linkedin.com/rest/organizationAcls"
    timeout = 20

    @staticmethod
    def _account_url(account):
        return (
            f"/web#id={account.id}&model=automatify.social.account&view_type=form"
        )

    @staticmethod
    def _response_detail(response):
        return (response.text or "")[:800]

    def _fail(self, account, message):
        account.write({"connection_state": "error", "last_error": message})
        return request.redirect(self._account_url(account))

    def _exchange_code(self, account, code):
        params = request.env["ir.config_parameter"].sudo()
        client_id = params.get_param("automatify_social_linkedin.client_id")
        client_secret = params.get_param("automatify_social_linkedin.client_secret")
        response = requests.post(
            self.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": account._linkedin_redirect_uri(),
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ValueError(
                f"LinkedIn token exchange failed ({response.status_code}): "
                f"{self._response_detail(response)}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ValueError("LinkedIn token response did not contain access_token.")
        return payload

    def _resolve_member(self, token):
        response = requests.get(
            self.member_endpoint,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ValueError(
                f"LinkedIn member lookup failed ({response.status_code}): "
                f"{self._response_detail(response)}"
            )
        profile = response.json()
        member_id = profile.get("id")
        if not member_id:
            raise ValueError("LinkedIn member profile did not contain an id.")
        name = " ".join(
            part
            for part in (
                profile.get("localizedFirstName"),
                profile.get("localizedLastName"),
            )
            if part
        )
        return f"urn:li:person:{member_id}", name or None

    def _resolve_organization(self, account, token):
        response = requests.get(
            self.organization_acl_endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Linkedin-Version": account.linkedin_api_version or "202609",
            },
            params={"q": "roleAssignee", "state": "APPROVED"},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ValueError(
                f"LinkedIn organization lookup failed ({response.status_code}): "
                f"{self._response_detail(response)}"
            )

        eligible_roles = {
            "ADMINISTRATOR",
            "DIRECT_SPONSORED_CONTENT_POSTER",
            "CONTENT_ADMIN",
            "CONTENT_ADMINISTRATOR",
        }
        organization_urns = sorted(
            {
                element.get("organization") or element.get("organizationTarget")
                for element in response.json().get("elements", [])
                if element.get("state") == "APPROVED"
                and element.get("role") in eligible_roles
                and (element.get("organization") or element.get("organizationTarget"))
            }
        )

        configured = account.linkedin_author_urn
        if configured:
            if configured not in organization_urns:
                raise ValueError(
                    "The configured LinkedIn Company Page is not among the pages "
                    "this member can publish for."
                )
            return configured, None
        if len(organization_urns) == 1:
            return organization_urns[0], None
        if not organization_urns:
            raise ValueError(
                "LinkedIn returned no Company Pages this member can publish for."
            )
        raise ValueError(
            "This LinkedIn member can publish for multiple Company Pages. "
            "Enter the desired LinkedIn Author URN on the Social Account and connect again."
        )

    @http.route(
        "/automatify-social/linkedin/oauth/callback",
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
            return request.make_response("Missing LinkedIn OAuth state.", status=400)

        state_record = (
            request.env["automatify.social.linkedin.oauth.state"]
            .sudo()
            .search([("token", "=", state)], limit=1)
        )
        if not state_record:
            return request.make_response("Invalid LinkedIn OAuth state.", status=400)
        if state_record.user_id.id != request.env.user.id:
            return request.make_response("LinkedIn OAuth user mismatch.", status=403)
        if state_record.expires_at < fields.Datetime.now():
            state_record.unlink()
            return request.make_response("LinkedIn OAuth state expired.", status=400)

        account = state_record.account_id.with_user(request.env.user)
        state_record.unlink()  # one-time state: consume before any external request

        if error:
            return self._fail(
                account,
                error_description or f"LinkedIn authorization failed: {error}",
            )
        if not code:
            return self._fail(account, "LinkedIn did not return an authorization code.")

        try:
            token_payload = self._exchange_code(account, code)
            token = token_payload["access_token"]
            if account.linkedin_author_type == "member":
                author_urn, display_name = self._resolve_member(token)
            else:
                author_urn, display_name = self._resolve_organization(account, token)

            expires_in = int(token_payload.get("expires_in") or 0)
            expires_at = (
                fields.Datetime.now() + timedelta(seconds=expires_in)
                if expires_in
                else False
            )
            values = {
                "linkedin_access_token": token,
                "linkedin_refresh_token": token_payload.get("refresh_token") or False,
                "linkedin_token_expires_at": expires_at,
                "linkedin_author_urn": author_urn,
                "external_account_id": author_urn,
                "connection_state": "connected",
                "last_error": False,
                "last_sync_at": fields.Datetime.now(),
            }
            if display_name:
                values["handle"] = display_name
            account.write(values)
        except (requests.RequestException, ValueError, TypeError) as exc:
            return self._fail(account, str(exc))

        return request.redirect(self._account_url(account))
