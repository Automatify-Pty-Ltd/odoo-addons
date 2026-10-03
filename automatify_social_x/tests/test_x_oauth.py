from datetime import timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestXOAuth(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {"name": "X Test Account", "platform": "x"}
        )

    def test_scopes_include_write_media_and_refresh(self):
        self.assertEqual(
            self.account._x_oauth_scopes(),
            [
                "tweet.read",
                "tweet.write",
                "users.read",
                "media.write",
                "offline.access",
            ],
        )

    def test_redirect_uri_uses_odoo_base_url(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://odoo.example.com/"
        )
        self.assertEqual(
            self.account._x_redirect_uri(),
            "https://odoo.example.com/automatify-social/x/oauth/callback",
        )

    @patch("odoo.addons.automatify_social_x.models.social_account.requests.post")
    def test_expired_access_token_is_refreshed(self, post_request):
        self.env["ir.config_parameter"].sudo().set_param(
            "automatify_social_x.client_id", "client-id"
        )
        self.account.write(
            {
                "x_access_token": "expired",
                "x_refresh_token": "refresh-token",
                "x_token_expires_at": fields.Datetime.now() - timedelta(minutes=5),
            }
        )
        response = Mock(status_code=200, text="")
        response.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 7200,
        }
        post_request.return_value = response

        token = self.account._x_get_access_token()

        self.assertEqual(token, "new-token")
        self.assertEqual(self.account.x_access_token, "new-token")
        self.assertEqual(self.account.x_refresh_token, "new-refresh-token")
        self.assertEqual(self.account.connection_state, "connected")
