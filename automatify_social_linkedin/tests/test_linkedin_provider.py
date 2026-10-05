import base64
from unittest.mock import Mock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.automatify_social.providers.base import AmbiguousPublishError


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

    def _make_image(self):
        return self.env["ir.attachment"].create(
            {
                "name": "launch.png",
                "type": "binary",
                "mimetype": "image/png",
                "datas": base64.b64encode(b"fake-image-bytes"),
            }
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
        self.assertEqual(
            result.external_url,
            "https://www.linkedin.com/feed/update/urn:li:share:42/",
        )
        _, kwargs = post_request.call_args
        self.assertEqual(kwargs["json"]["author"], "urn:li:organization:123456")
        self.assertEqual(kwargs["json"]["commentary"], "Hello from Odoo")
        self.assertEqual(kwargs["headers"]["Linkedin-Version"], "202609")
        self.assertEqual(kwargs["headers"]["X-Restli-Protocol-Version"], "2.0.0")

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_uses_provider_safe_rich_text_rendering(self, post_request):
        self.post.message = "<p>Hello <strong>Odoo</strong></p>"
        response = Mock(status_code=201, text="")
        response.headers = {"x-restli-id": "urn:li:share:43"}
        post_request.return_value = response

        self.account._get_social_provider().publish(self.account, self.post)

        _, kwargs = post_request.call_args
        self.assertEqual(kwargs["json"]["commentary"], "Hello *Odoo*")

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.time.sleep")
    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.get")
    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.put")
    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_single_image_waits_until_available(
        self, post_request, put_request, get_request, sleep
    ):
        self.post.image_ids = self._make_image()

        initialize = Mock(status_code=200, text="")
        initialize.json.return_value = {
            "value": {
                "uploadUrl": "https://linkedin.example/upload/image",
                "image": "urn:li:image:abc123",
            }
        }
        publish = Mock(status_code=201, text="")
        publish.headers = {"x-restli-id": "urn:li:share:44"}
        post_request.side_effect = [initialize, publish]
        put_request.return_value = Mock(status_code=201, text="")

        processing = Mock(status_code=200, text="")
        processing.json.return_value = {"status": "PROCESSING"}
        available = Mock(status_code=200, text="")
        available.json.return_value = {"status": "AVAILABLE"}
        get_request.side_effect = [processing, available]

        result = self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(result.external_post_id, "urn:li:share:44")
        self.assertEqual(post_request.call_count, 2)
        initialize_call, publish_call = post_request.call_args_list
        self.assertEqual(
            initialize_call.args[0],
            "https://api.linkedin.com/rest/images?action=initializeUpload",
        )
        self.assertEqual(
            initialize_call.kwargs["json"],
            {"initializeUploadRequest": {"owner": "urn:li:organization:123456"}},
        )
        self.assertEqual(get_request.call_count, 2)
        self.assertEqual(
            get_request.call_args_list[0].args[0],
            "https://api.linkedin.com/rest/images/urn:li:image:abc123",
        )
        sleep.assert_called_once_with(1)
        self.assertEqual(
            publish_call.kwargs["json"]["content"]["media"]["id"],
            "urn:li:image:abc123",
        )
        put_request.assert_called_once()
        self.assertEqual(
            put_request.call_args.args[0],
            "https://linkedin.example/upload/image",
        )
        self.assertEqual(put_request.call_args.kwargs["data"], b"fake-image-bytes")

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.get")
    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.put")
    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_image_processing_failure_prevents_post_creation(
        self, post_request, put_request, get_request
    ):
        self.post.image_ids = self._make_image()

        initialize = Mock(status_code=200, text="")
        initialize.json.return_value = {
            "value": {
                "uploadUrl": "https://linkedin.example/upload/image",
                "image": "urn:li:image:failed123",
            }
        }
        post_request.return_value = initialize
        put_request.return_value = Mock(status_code=201, text="")
        failed = Mock(status_code=200, text="")
        failed.json.return_value = {"status": "PROCESSING_FAILED"}
        get_request.return_value = failed

        with self.assertRaises(UserError):
            self.account._get_social_provider().publish(self.account, self.post)

        self.assertEqual(post_request.call_count, 1)
        get_request.assert_called_once()

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_timeout_is_ambiguous_and_not_plain_failure(self, post_request):
        post_request.side_effect = requests.Timeout("response lost")

        with self.assertRaises(AmbiguousPublishError):
            self.account._get_social_provider().publish(self.account, self.post)

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_5xx_is_ambiguous_and_not_plain_failure(self, post_request):
        response = Mock(status_code=503, text="service unavailable")
        response.headers = {}
        post_request.return_value = response

        with self.assertRaises(AmbiguousPublishError):
            self.account._get_social_provider().publish(self.account, self.post)

    @patch("odoo.addons.automatify_social_linkedin.providers.linkedin.requests.post")
    def test_publish_auth_rejection_marks_account_error(self, post_request):
        response = Mock(status_code=403, text="forbidden")
        response.headers = {}
        post_request.return_value = response

        try:
            self.account._get_social_provider().publish(self.account, self.post)
        except UserError:
            pass
        else:
            self.fail("Expected LinkedIn 403 to raise UserError")

        self.assertEqual(self.account.connection_state, "error")
        self.assertIn("403", self.account.last_error)
