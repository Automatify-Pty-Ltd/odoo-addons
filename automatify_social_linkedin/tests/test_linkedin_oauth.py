from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


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

    def test_member_scopes(self):
        self.account.linkedin_author_type = "member"
        self.assertEqual(
            self.account._linkedin_oauth_scopes(),
            ["r_basicprofile", "w_member_social"],
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
