from odoo.tests.common import TransactionCase


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
