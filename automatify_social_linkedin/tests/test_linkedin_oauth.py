from unittest.mock import Mock, patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.automatify_social_linkedin.controllers.oauth import (
    AutomatifySocialLinkedInOAuthController,
)


class TestLinkedInOAuth(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {
                "name": "LinkedIn Test Account",
                "platform": "linkedin",
                "linkedin_author_type": "organization",
            }
        )
        self.regular_user = new_test_user(
            self.env,
            login="linkedin-settings-user",
            groups="base.group_user",
        )

    def test_organization_scopes(self):
        self.assertEqual(
            self.account._linkedin_oauth_scopes(),
            ["rw_organization_admin", "w_organization_social"],
        )

    def test_member_scopes_use_oidc_and_share_permission(self):
        self.account.linkedin_author_type = "member"
        self.assertEqual(
            self.account._linkedin_oauth_scopes(),
            ["openid", "profile", "w_member_social"],
        )

    def test_member_identity_uses_oidc_userinfo_sub(self):
        controller = AutomatifySocialLinkedInOAuthController()
        response = Mock(status_code=200, text="")
        response.json.return_value = {
            "sub": "member-123",
            "name": "LinkedIn Test Member",
        }
        with patch(
            "odoo.addons.automatify_social_linkedin.controllers.oauth.requests.get",
            return_value=response,
        ) as get_request:
            author_urn, display_name = controller._resolve_member("test-token")

        self.assertEqual(author_urn, "urn:li:person:member-123")
        self.assertEqual(display_name, "LinkedIn Test Member")
        self.assertEqual(
            get_request.call_args.args[0], "https://api.linkedin.com/v2/userinfo"
        )

    def test_redirect_uri_uses_odoo_base_url(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://odoo.example.com/"
        )
        self.assertEqual(
            self.account._linkedin_redirect_uri(),
            "https://odoo.example.com/automatify-social/linkedin/oauth/callback",
        )

    def test_settings_secrets_and_writes_are_manager_only(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("automatify_social_linkedin.client_id", "original-id")
        params.set_param(
            "automatify_social_linkedin.client_secret", "original-secret"
        )
        settings_model = self.env[
            "automatify.social.linkedin.settings"
        ].with_user(self.regular_user)

        with self.assertRaises(AccessError):
            settings_model.default_get(["client_id", "client_secret", "callback_url"])

        settings = (
            self.env["automatify.social.linkedin.settings"]
            .sudo()
            .create({"client_id": "attacker-id", "client_secret": "attacker-secret"})
            .with_user(self.regular_user)
        )
        with self.assertRaises(AccessError):
            settings.action_save()

        self.assertEqual(
            params.get_param("automatify_social_linkedin.client_id"), "original-id"
        )
        self.assertEqual(
            params.get_param("automatify_social_linkedin.client_secret"),
            "original-secret",
        )
