from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase


class TestXProvider(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {"name": "X Test Account", "platform": "x", "handle": "@example"}
        )
        self.post = self.env["automatify.social.post"].create(
            {"message": "Hello from Odoo", "company_id": self.env.company.id}
        )

    def test_connector_registers_x_platform(self):
        self.assertIn(("x", "X"), self.account._social_platform_selection())

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_publish_text_post(self, post_request):
        response = Mock(status_code=201, text="")
        response.json.return_value = {
            "data": {"id": "12345", "text": "Hello from Odoo"}
        }
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            result = self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(result.external_post_id, "12345")
        self.assertEqual(result.external_url, "https://x.com/example/status/12345")
        _, kwargs = post_request.call_args
        self.assertEqual(kwargs["json"], {"text": "Hello from Odoo"})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token")

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_publish_auth_rejection_marks_account_error(self, post_request):
        response = Mock(status_code=403, text="forbidden")
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            with self.assertRaises(Exception):
                self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(self.account.connection_state, "error")
        self.assertIn("403", self.account.last_error)
