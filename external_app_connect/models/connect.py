import base64
import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,79}$")
_PKCE_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_BLOCKED_REDIRECT_SCHEMES = {"javascript", "data", "file", "vbscript"}


def _hash_secret(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scope_tokens(value):
    if not value:
        return ()
    parts = value.split() if isinstance(value, str) else value
    normalized = (str(part).strip() for part in parts)
    return tuple(dict.fromkeys(part for part in normalized if part))


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class ExternalAppScope(models.Model):
    _name = "external.app.scope"
    _description = "External App Scope"
    _order = "code"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Scope code must be unique.")

    @api.constrains("code")
    def _check_code(self):
        for record in self:
            if not _SCOPE_RE.fullmatch(record.code or ""):
                raise ValidationError(
                    "Scope codes must be 2-80 lowercase characters using letters, digits, '.', '_', ':', or '-'."
                )


class ExternalAppClient(models.Model):
    _name = "external.app.client"
    _description = "External App Client"
    _order = "name"

    name = fields.Char(required=True)
    client_id = fields.Char(
        required=True,
        index=True,
        readonly=True,
        copy=False,
        default=lambda self: secrets.token_urlsafe(18),
    )
    active = fields.Boolean(default=True)
    website = fields.Char()
    redirect_uris = fields.Text(
        required=True,
        help="One exact redirect URI per line. HTTPS and custom application schemes are supported.",
    )
    scope_ids = fields.Many2many(
        "external.app.scope",
        "external_app_client_scope_rel",
        "client_id",
        "scope_id",
        string="Allowed scopes",
    )
    token_lifetime_days = fields.Integer(
        default=90,
        required=True,
        help="Lifetime of issued connector tokens. Capped at 90 days by this module.",
    )

    _client_id_unique = models.Constraint("UNIQUE(client_id)", "Client ID must be unique.")

    @api.constrains("token_lifetime_days")
    def _check_token_lifetime_days(self):
        for record in self:
            if record.token_lifetime_days < 1 or record.token_lifetime_days > 90:
                raise ValidationError("Token lifetime must be between 1 and 90 days.")

    @api.constrains("redirect_uris")
    def _check_redirect_uris(self):
        for record in self:
            uris = record._redirect_uri_set()
            if not uris:
                raise ValidationError("At least one redirect URI is required.")
            for uri in uris:
                parts = urlsplit(uri)
                if not parts.scheme or parts.fragment:
                    raise ValidationError("Redirect URIs require a scheme and must not contain fragments.")
                if parts.scheme.lower() in _BLOCKED_REDIRECT_SCHEMES:
                    raise ValidationError("Unsafe redirect URI scheme.")
                if parts.scheme.lower() in {"http", "https"} and not parts.netloc:
                    raise ValidationError("HTTP(S) redirect URIs require a host.")
                if parts.scheme.lower() == "http" and (parts.hostname or "").lower() not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    raise ValidationError("Non-local web redirect URIs must use HTTPS.")

    def _redirect_uri_set(self):
        self.ensure_one()
        return {
            line.strip()
            for line in (self.redirect_uris or "").replace("\r", "").split("\n")
            if line.strip()
        }

    @api.model
    def validate_authorization_request(self, client_id, redirect_uri, requested_scope):
        client = self.sudo().search(
            [("client_id", "=", client_id), ("active", "=", True)], limit=1
        )
        if not client:
            raise ValidationError("Unknown or inactive application client.")
        if redirect_uri not in client._redirect_uri_set():
            raise ValidationError("Redirect URI is not registered for this application.")

        requested = _scope_tokens(requested_scope)
        if not requested:
            raise ValidationError("At least one scope is required.")
        allowed = set(client.scope_ids.filtered("active").mapped("code"))
        if not set(requested).issubset(allowed):
            raise ValidationError("Application requested a scope it is not allowed to use.")
        return client, requested


class ExternalAppAuthorizationCode(models.Model):
    _name = "external.app.authorization.code"
    _description = "External App Authorization Code"
    _order = "create_date desc"

    client_id = fields.Many2one("external.app.client", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    code_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    redirect_uri = fields.Char(required=True, readonly=True)
    scope = fields.Char(required=True, readonly=True)
    code_challenge = fields.Char(required=True, readonly=True)
    expires_at = fields.Datetime(required=True, readonly=True, index=True)
    consumed_at = fields.Datetime(readonly=True, index=True)

    _code_hash_unique = models.Constraint(
        "UNIQUE(code_hash)", "Authorization code hash must be unique."
    )

    @api.model
    def create_authorization_code(self, client, user, redirect_uri, scope, code_challenge):
        if not _PKCE_RE.fullmatch(code_challenge or ""):
            raise ValidationError("Invalid PKCE S256 challenge.")
        raw_code = secrets.token_urlsafe(32)
        record = self.sudo().create(
            {
                "client_id": client.id,
                "user_id": user.id,
                "code_hash": _hash_secret(raw_code),
                "redirect_uri": redirect_uri,
                "scope": " ".join(_scope_tokens(scope)),
                "code_challenge": code_challenge,
                "expires_at": fields.Datetime.now() + timedelta(minutes=5),
            }
        )
        return record, raw_code

    @api.model
    def consume_authorization_code(self, raw_code, client, redirect_uri, code_verifier):
        if not raw_code or not _PKCE_RE.fullmatch(code_verifier or ""):
            raise ValidationError("Invalid authorization code or PKCE verifier.")

        record = self.sudo().search(
            [
                ("code_hash", "=", _hash_secret(raw_code)),
                ("client_id", "=", client.id),
                ("redirect_uri", "=", redirect_uri),
            ],
            limit=1,
        )
        now = fields.Datetime.now()
        if not record or record.expires_at <= now or record.consumed_at:
            raise ValidationError("Authorization code is invalid, expired, or already used.")
        if not secrets.compare_digest(record.code_challenge, _pkce_challenge(code_verifier)):
            raise ValidationError("PKCE verification failed.")

        self.env.cr.execute(
            """
            UPDATE external_app_authorization_code
               SET consumed_at = %s
             WHERE id = %s
               AND consumed_at IS NULL
            RETURNING id
            """,
            [now, record.id],
        )
        if not self.env.cr.fetchone():
            raise ValidationError("Authorization code was already used.")
        record.invalidate_recordset(["consumed_at"])
        return record


class ExternalAppAccessToken(models.Model):
    _name = "external.app.access.token"
    _description = "External App Access Token"
    _order = "create_date desc"

    name = fields.Char(required=True)
    token_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    client_id = fields.Many2one("external.app.client", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    scope = fields.Char(required=True, readonly=True)
    expires_at = fields.Datetime(required=True, readonly=True, index=True)
    revoked_at = fields.Datetime(readonly=True, index=True)
    last_used_at = fields.Datetime(readonly=True)

    _token_hash_unique = models.Constraint("UNIQUE(token_hash)", "Access token hash must be unique.")

    @api.model
    def issue_for_code(self, code_record):
        raw_token = secrets.token_urlsafe(32)
        record = self.sudo().create(
            {
                "name": "%s connection" % code_record.client_id.name,
                "token_hash": _hash_secret(raw_token),
                "client_id": code_record.client_id.id,
                "user_id": code_record.user_id.id,
                "scope": code_record.scope,
                "expires_at": fields.Datetime.now()
                + timedelta(days=code_record.client_id.token_lifetime_days),
            }
        )
        return record, raw_token

    @api.model
    def authenticate_raw(self, raw_token, required_scopes=None):
        if not raw_token:
            raise AccessDenied("Missing connector token.")
        record = self.sudo().search([("token_hash", "=", _hash_secret(raw_token))], limit=1)
        now = fields.Datetime.now()
        if (
            not record
            or record.revoked_at
            or record.expires_at <= now
            or not record.client_id.active
            or not record.user_id.active
        ):
            raise AccessDenied("Invalid or expired connector token.")
        required = set(required_scopes or ())
        granted = set(_scope_tokens(record.scope))
        if not required.issubset(granted):
            raise AccessDenied("Connector token does not grant the required scope.")
        record.sudo().write({"last_used_at": now})
        return record

    @api.model
    def authenticate_bearer(self, authorization_header, required_scopes=None):
        scheme, separator, token = (authorization_header or "").partition(" ")
        if not separator or scheme.lower() != "bearer":
            raise AccessDenied("Bearer connector token required.")
        return self.authenticate_raw(token.strip(), required_scopes=required_scopes)

    @api.model
    def revoke_raw(self, raw_token):
        record = self.sudo().search([("token_hash", "=", _hash_secret(raw_token or ""))], limit=1)
        if record and not record.revoked_at:
            record.write({"revoked_at": fields.Datetime.now()})
        return True
