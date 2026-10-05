from datetime import timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


class TestXOAuth(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {"name": "X Test Account", "platform": "x"}
        )
        self.regular_user = new_test_user(
            self.env,
            login="x-settings-user",
            email="x-settings-user@example.com",
            groups="base.group_user",
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

    def test_settings_secrets_and_writes_are_manager_only(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("automatify_social_x.client_id", "original-id")
        params.set_param("automatify_social_x.client_secret", "original-secret")
        settings_model = self.env["automatify.social.x.settings"].with_user(
            self.regular_user
        )

        with self.assertRaises(AccessError):
            settings_model.default_get(["client_id", "client_secret", "callback_url"])

        manager_user = new_test_user(
            self.env,
            login="x-settings-manager",
            email="x-settings-manager@example.com",
            groups="automatify_social.group_automatify_social_manager",
        )
        settings = (
            self.env["automatify.social.x.settings"]
            .with_user(manager_user)
            .create({"client_id": "attacker-id", "client_secret": "attacker-secret"})
            .with_user(self.regular_user)
        )
        with self.assertRaises(AccessError):
            settings.action_save()

        self.assertEqual(
            params.get_param("automatify_social_x.client_id"), "original-id"
        )
        self.assertEqual(
            params.get_param("automatify_social_x.client_secret"), "original-secret"
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

    def test_oauth_state_is_locked_before_one_time_consumption(self):
        state_model = self.env["automatify.social.x.oauth.state"].sudo()
        state_record = state_model.create(
            {
                "token": "x-one-time-state",
                "code_verifier": "verifier",
                "account_id": self.account.id,
                "user_id": self.env.user.id,
                "expires_at": fields.Datetime.now() + timedelta(minutes=10),
            }
        )

        locked = state_model._lock_for_consume("x-one-time-state")
        self.assertEqual(locked, state_record)
        locked.unlink()
        self.assertFalse(state_model._lock_for_consume("x-one-time-state"))
