import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from odoo import http
from odoo.exceptions import AccessDenied, ValidationError
from odoo.http import request


_PKCE_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


def _redirect_with_params(uri, params):
    parts = urlsplit(uri)
    query = list(parse_qsl(parts.query, keep_blank_values=True))
    query.extend((key, value) for key, value in params.items() if value is not None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _request_payload():
    payload = request.httprequest.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.httprequest.form.to_dict(flat=True)


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")],
        status=status,
    )


class ExternalAppConnectController(http.Controller):
    @http.route("/.well-known/odoo-app-connect", type="http", auth="public", methods=["GET"], sitemap=False)
    def metadata(self, **_kwargs):
        base_url = request.httprequest.host_url.rstrip("/")
        return _json_response(
            {
                "issuer": base_url,
                "authorization_endpoint": f"{base_url}/external-app/connect/authorize",
                "token_endpoint": f"{base_url}/external-app/connect/token",
                "revocation_endpoint": f"{base_url}/external-app/connect/revoke",
                "code_challenge_methods_supported": ["S256"],
            }
        )

    @http.route("/external-app/connect/authorize", type="http", auth="user", methods=["GET"], sitemap=False)
    def authorize(
        self,
        response_type=None,
        client_id=None,
        redirect_uri=None,
        scope=None,
        state=None,
        code_challenge=None,
        code_challenge_method=None,
        **_kwargs,
    ):
        try:
            if response_type != "code":
                raise ValidationError("Only response_type=code is supported.")
            if not state or len(state) > 1024:
                raise ValidationError("A valid state value is required.")
            if code_challenge_method != "S256" or not _PKCE_RE.fullmatch(code_challenge or ""):
                raise ValidationError("PKCE with code_challenge_method=S256 is required.")
            client, scopes = request.env["external.app.client"].validate_authorization_request(
                client_id, redirect_uri, scope
            )
        except ValidationError as error:
            return request.render(
                "external_app_connect.authorization_error_page",
                {"error_message": str(error)},
                status=400,
            )

        requested = client.scope_ids.filtered(lambda record: record.code in scopes)
        return request.render(
            "external_app_connect.consent_page",
            {
                "client": client,
                "requested_scopes": requested,
                "response_type": response_type,
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            },
        )

    @http.route(
        "/external-app/connect/authorize/decision",
        type="http",
        auth="user",
        methods=["POST"],
        sitemap=False,
    )
    def authorize_decision(
        self,
        action=None,
        response_type=None,
        client_id=None,
        redirect_uri=None,
        scope=None,
        state=None,
        code_challenge=None,
        code_challenge_method=None,
        **_kwargs,
    ):
        try:
            if response_type != "code":
                raise ValidationError("Unsupported authorization response type.")
            if not state or len(state) > 1024:
                raise ValidationError("A valid state value is required.")
            if code_challenge_method != "S256" or not _PKCE_RE.fullmatch(code_challenge or ""):
                raise ValidationError("PKCE with S256 is required.")
            client, scopes = request.env["external.app.client"].validate_authorization_request(
                client_id, redirect_uri, scope
            )
        except ValidationError as error:
            return request.render(
                "external_app_connect.authorization_error_page",
                {"error_message": str(error)},
                status=400,
            )

        if action != "allow":
            return request.redirect(
                _redirect_with_params(
                    redirect_uri,
                    {"error": "access_denied", "state": state},
                ),
                code=303,
                local=False,
            )

        _record, raw_code = request.env[
            "external.app.authorization.code"
        ].create_authorization_code(
            client,
            request.env.user,
            redirect_uri,
            scopes,
            code_challenge,
        )
        return request.redirect(
            _redirect_with_params(redirect_uri, {"code": raw_code, "state": state}),
            code=303,
            local=False,
        )

    @http.route(
        "/external-app/connect/token",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def token(self, **_kwargs):
        payload = _request_payload()
        if payload.get("grant_type") != "authorization_code":
            return _json_response({"error": "unsupported_grant_type"}, status=400)

        client_id = str(payload.get("client_id") or "")
        redirect_uri = str(payload.get("redirect_uri") or "")
        raw_code = str(payload.get("code") or "")
        code_verifier = str(payload.get("code_verifier") or "")

        client = request.env["external.app.client"].sudo().search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client or redirect_uri not in client._redirect_uri_set():
            return _json_response({"error": "invalid_grant"}, status=400)

        try:
            code_record = request.env[
                "external.app.authorization.code"
            ].consume_authorization_code(raw_code, client, redirect_uri, code_verifier)
            token_record, raw_token = request.env["external.app.access.token"].issue_for_code(code_record)
        except ValidationError:
            return _json_response({"error": "invalid_grant"}, status=400)

        expires_in = max(
            0,
            int((token_record.expires_at - token_record.create_date).total_seconds()),
        )
        return _json_response(
            {
                "access_token": raw_token,
                "token_type": "Bearer",
                "expires_in": expires_in,
                "scope": token_record.scope,
            }
        )

    @http.route(
        "/external-app/connect/revoke",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        sitemap=False,
    )
    def revoke(self, **_kwargs):
        payload = _request_payload()
        raw_token = str(payload.get("token") or "")
        if not raw_token:
            authorization = request.httprequest.headers.get("Authorization", "")
            scheme, separator, value = authorization.partition(" ")
            if separator and scheme.lower() == "bearer":
                raw_token = value.strip()
        request.env["external.app.access.token"].revoke_raw(raw_token)
        return _json_response({"revoked": True})

    @http.route(
        "/external-app/connect/api/v1/me",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def me(self, **_kwargs):
        try:
            token = request.env["external.app.access.token"].authenticate_bearer(
                request.httprequest.headers.get("Authorization"),
                required_scopes={"profile:read"},
            )
        except AccessDenied:
            return _json_response({"error": "invalid_token"}, status=401)

        user = token.user_id
        return _json_response(
            {
                "sub": str(user.id),
                "name": user.name,
                "company": {"id": user.company_id.id, "name": user.company_id.name},
                "client_id": token.client_id.client_id,
                "scope": token.scope,
            }
        )
