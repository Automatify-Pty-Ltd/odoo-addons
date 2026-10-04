from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.automatify_social.providers.base import AmbiguousPublishError


class TestXAmbiguousAcceptedResponse(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {"name": "X Ambiguous Test", "platform": "x", "handle": "@example"}
        )
        self.post = self.env["automatify.social.post"].create(
            {"message": "Hello from Odoo", "company_id": self.env.company.id}
        )

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_201_with_unreadable_json_is_ambiguous(self, post_request):
        response = Mock(status_code=201, text="{truncated")
        response.json.side_effect = ValueError("truncated JSON")
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            with self.assertRaises(AmbiguousPublishError):
                self.account._get_social_provider().publish(self.account, self.post)

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_201_with_non_object_json_is_ambiguous(self, post_request):
        response = Mock(status_code=201, text="[]")
        response.json.return_value = []
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            with self.assertRaises(AmbiguousPublishError):
                self.account._get_social_provider().publish(self.account, self.post)

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_5xx_publish_response_is_ambiguous(self, post_request):
        post_request.return_value = Mock(status_code=503, text="service unavailable")

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            with self.assertRaises(AmbiguousPublishError):
                self.account._get_social_provider().publish(self.account, self.post)
