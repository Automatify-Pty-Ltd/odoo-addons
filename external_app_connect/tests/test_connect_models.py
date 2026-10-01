import base64
import hashlib

from odoo.exceptions import AccessDenied, ValidationError
from odoo.tests.common import TransactionCase


class TestExternalAppConnect(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile_scope = cls.env.ref("external_app_connect.scope_profile_read")
        cls.client = cls.env["external.app.client"].create(
            {
                "name": "Inventify",
                "website": "https://automatify.com.au",
                "redirect_uris": "inventify://odoo-connected\nhttps://example.test/odoo/callback",
                "scope_ids": [(6, 0, [cls.profile_scope.id])],
                "token_lifetime_days": 30,
            }
        )
        cls.verifier = "v" * 64
        digest = hashlib.sha256(cls.verifier.encode("ascii")).digest()
        cls.challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def test_authorization_code_is_one_time_and_secret_is_not_stored(self):
        code_record, raw_code = self.env[
            "external.app.authorization.code"
        ].create_authorization_code(
            self.client,
            self.env.user,
            "inventify://odoo-connected",
            ("profile:read",),
            self.challenge,
        )
        self.assertNotEqual(code_record.code_hash, raw_code)

        consumed = self.env[
            "external.app.authorization.code"
        ].consume_authorization_code(
            raw_code,
            self.client,
            "inventify://odoo-connected",
            self.verifier,
        )
        self.assertEqual(consumed.id, code_record.id)

        with self.assertRaises(ValidationError):
            self.env["external.app.authorization.code"].consume_authorization_code(
                raw_code,
                self.client,
                "inventify://odoo-connected",
                self.verifier,
            )

    def test_pkce_verifier_must_match(self):
        _record, raw_code = self.env[
            "external.app.authorization.code"
        ].create_authorization_code(
            self.client,
            self.env.user,
            "inventify://odoo-connected",
            ("profile:read",),
            self.challenge,
        )
        with self.assertRaises(ValidationError):
            self.env["external.app.authorization.code"].consume_authorization_code(
                raw_code,
                self.client,
                "inventify://odoo-connected",
                "x" * 64,
            )

    def test_token_is_hashed_and_scope_checked(self):
        code_record, raw_code = self.env[
            "external.app.authorization.code"
        ].create_authorization_code(
            self.client,
            self.env.user,
            "inventify://odoo-connected",
            ("profile:read",),
            self.challenge,
        )
        consumed = self.env[
            "external.app.authorization.code"
        ].consume_authorization_code(
            raw_code,
            self.client,
            "inventify://odoo-connected",
            self.verifier,
        )
        token_record, raw_token = self.env["external.app.access.token"].issue_for_code(consumed)
        self.assertNotEqual(token_record.token_hash, raw_token)

        authenticated = self.env["external.app.access.token"].authenticate_raw(
            raw_token, required_scopes={"profile:read"}
        )
        self.assertEqual(authenticated.id, token_record.id)

        with self.assertRaises(AccessDenied):
            self.env["external.app.access.token"].authenticate_raw(
                raw_token, required_scopes={"inventory:write"}
            )

    def test_redirect_uri_is_exact_match(self):
        with self.assertRaises(ValidationError):
            self.env["external.app.client"].validate_authorization_request(
                self.client.client_id,
                "inventify://odoo-connected/attacker",
                "profile:read",
            )

    def test_unregistered_scope_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["external.app.client"].validate_authorization_request(
                self.client.client_id,
                "inventify://odoo-connected",
                "profile:read inventory:write",
            )
