import base64
import hashlib

from odoo.tests.common import TransactionCase


class TestInventifyInventoryConnect(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env.ref("inventify_inventory_connect.external_app_client_inventify")
        cls.user = cls.env.ref("base.user_admin")

    def test_inventify_client_is_registered_with_scoped_permissions(self):
        self.assertEqual(self.client.client_id, "inventify.mobile.v1")
        self.assertIn(
            "https://xrikoshdvntnuypticgc.supabase.co/functions/v1/odoo-connect-callback",
            self.client._redirect_uri_set(),
        )
        self.assertIn("inventify://odoo-connected", self.client._redirect_uri_set())
        self.assertEqual(
            set(self.client.scope_ids.mapped("code")),
            {
                "profile:read",
                "inventify:inventory:read",
                "inventify:inventory:write",
            },
        )

    def test_inventify_root_location_is_stored_per_connection(self):
        verifier = "v" * 64
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        code_record, raw_code = self.env[
            "external.app.authorization.code"
        ].create_authorization_code(
            self.client,
            self.user,
            "inventify://odoo-connected",
            ("inventify:inventory:read", "inventify:inventory:write"),
            challenge,
        )
        consumed = self.env[
            "external.app.authorization.code"
        ].consume_authorization_code(
            raw_code,
            self.client,
            "inventify://odoo-connected",
            verifier,
        )
        token_record, _raw_token = self.env["external.app.access.token"].issue_for_code(consumed)

        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.user.company_id.id)], limit=1
        )
        self.assertTrue(warehouse)
        token_record.write({"inventify_root_location_id": warehouse.lot_stock_id.id})
        self.assertEqual(token_record.inventify_root_location_id, warehouse.lot_stock_id)
