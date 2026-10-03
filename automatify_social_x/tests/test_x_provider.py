import base64
from unittest.mock import Mock, patch

from odoo.exceptions import UserError
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

    def _make_image(self):
        return self.env["ir.attachment"].create(
            {
                "name": "launch.png",
                "type": "binary",
                "mimetype": "image/png",
                "datas": base64.b64encode(b"fake-image-bytes"),
            }
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
    def test_publish_uses_provider_safe_rich_text_rendering(self, post_request):
        self.post.message = "<p>Hello <strong>Odoo</strong></p>"
        response = Mock(status_code=201, text="")
        response.json.return_value = {"data": {"id": "12346"}}
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            self.account._get_social_provider().publish(self.account, self.post)

        _, kwargs = post_request.call_args
        self.assertEqual(kwargs["json"], {"text": "Hello *Odoo*"})

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_publish_single_image_post(self, post_request):
        self.post.image_ids = self._make_image()

        initialize = Mock(status_code=202, text="")
        initialize.json.return_value = {"data": {"id": "media-123"}}
        append = Mock(status_code=204, text="")
        finalize = Mock(status_code=200, text="")
        finalize.json.return_value = {"data": {"id": "media-123"}}
        publish = Mock(status_code=201, text="")
        publish.json.return_value = {"data": {"id": "12347"}}
        post_request.side_effect = [initialize, append, finalize, publish]

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            result = self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(result.external_post_id, "12347")
        self.assertEqual(post_request.call_count, 4)
        initialize_call, append_call, finalize_call, publish_call = post_request.call_args_list
        self.assertEqual(
            initialize_call.args[0],
            "https://api.x.com/2/media/upload/initialize",
        )
        self.assertEqual(
            initialize_call.kwargs["json"],
            {
                "total_bytes": len(b"fake-image-bytes"),
                "media_type": "image/png",
                "media_category": "tweet_image",
            },
        )
        self.assertEqual(
            append_call.args[0],
            "https://api.x.com/2/media/upload/media-123/append",
        )
        self.assertEqual(append_call.kwargs["data"], {"segment_index": "0"})
        self.assertEqual(
            append_call.kwargs["files"]["media"],
            ("launch.png", b"fake-image-bytes", "image/png"),
        )
        self.assertEqual(
            finalize_call.args[0],
            "https://api.x.com/2/media/upload/media-123/finalize",
        )
        self.assertEqual(
            publish_call.kwargs["json"],
            {
                "text": "Hello from Odoo",
                "media": {"media_ids": ["media-123"]},
            },
        )

    @patch("odoo.addons.automatify_social_x.providers.x.requests.post")
    def test_publish_auth_rejection_marks_account_error(self, post_request):
        response = Mock(status_code=403, text="forbidden")
        post_request.return_value = response

        with patch.object(
            type(self.account), "_x_get_access_token", return_value="token"
        ):
            try:
                self.account._get_social_provider().publish(self.account, self.post)
            except UserError:
                pass
            else:
                self.fail("Expected X 403 to raise UserError")

        self.assertEqual(self.account.connection_state, "error")
        self.assertIn("403", self.account.last_error)
