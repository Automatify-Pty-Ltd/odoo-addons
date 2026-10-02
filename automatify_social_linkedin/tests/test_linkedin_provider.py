from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase


class TestLinkedInProvider(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {
                "name": "LinkedIn Test Account",
                "platform": "linkedin",
                "linkedin_access_token": "test-token",
                "linkedin_author_urn": "urn:li:organization:123456",
                "linkedin_api_version": "202609",
            }
        )
        self.post = self.env["automatify.social.post"].create(
            {"message": "Hello from Odoo", "company_id": self.env.company.id}
        )

    def test_connector_registers_linkedin_platform(self):
        self.assertIn(
            ("linkedin", "LinkedIn"),
            self.account._social_platform_selection(),
        )

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_text_post(self, post_request):
        response = Mock(status_code=201, text="")
        response.headers = {"x-restli-id": "urn:li:share:42"}
        post_request.return_value = response

        result = self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(result.external_post_id, "urn:li:share:42")
        _, kwargs = post_request.call_args
        self.assertEqual(kwargs["json"]["author"], "urn:li:organization:123456")
        self.assertEqual(kwargs["json"]["commentary"], "Hello from Odoo")
        self.assertEqual(kwargs["headers"]["Linkedin-Version"], "202609")
        self.assertEqual(kwargs["headers"]["X-Restli-Protocol-Version"], "2.0.0")

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_auth_rejection_marks_account_error(self, post_request):
        response = Mock(status_code=403, text="forbidden")
        response.headers = {}
        post_request.return_value = response

        with self.assertRaises(Exception):
            self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(self.account.connection_state, "error")
        self.assertIn("403", self.account.last_error)
