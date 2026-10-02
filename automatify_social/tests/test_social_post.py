from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSocialPost(TransactionCase):
    def setUp(self):
        super().setUp()
        account_model = self.env["automatify.social.account"]
        with patch.object(
            type(account_model),
            "_social_platform_selection",
            return_value=[("test", "Test Provider")],
        ):
            self.account = account_model.create(
                {
                    "name": "Test Social Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )

    def _make_post(self):
        return self.env["automatify.social.post"].create(
            {
                "message": "Hello from Social Publisher",
                "target_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.account.id,
                        },
                    )
                ],
            }
        )

    def test_schedule_requires_future_datetime(self):
        post = self._make_post()
        with self.assertRaises(UserError):
            post.action_schedule()

        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()
        self.assertEqual(post.state, "scheduled")

    def test_missing_connector_becomes_actionable_failure(self):
        post = self._make_post()
        post.action_publish_now()
        self.assertEqual(post.state, "failed")
        self.assertEqual(post.target_ids.state, "failed")
        self.assertIn("No social provider connector", post.target_ids.error_message)

    def test_cancel_and_reset(self):
        post = self._make_post()
        post.action_cancel()
        self.assertEqual(post.state, "cancelled")
        post.action_reset_to_draft()
        self.assertEqual(post.state, "draft")

    def test_target_must_use_account_from_post_company(self):
        other_company = self.env["res.company"].create({"name": "Other Company"})
        account_model = self.env["automatify.social.account"]
        with patch.object(
            type(account_model),
            "_social_platform_selection",
            return_value=[("test", "Test Provider")],
        ):
            other_account = account_model.create(
                {
                    "name": "Other Company Social Account",
                    "platform": "test",
                    "company_id": other_company.id,
                }
            )
        post = self.env["automatify.social.post"].create(
            {"message": "Company-isolated post", "company_id": self.env.company.id}
        )

        with self.assertRaises(ValidationError):
            self.env["automatify.social.post.target"].create(
                {"post_id": post.id, "account_id": other_account.id}
            )

    def test_failed_post_requires_retry_action(self):
        post = self._make_post()
        post.action_publish_now()
        with self.assertRaises(UserError):
            post.action_publish_now()

    def test_display_name_uses_message_excerpt(self):
        post = self._make_post()
        self.assertTrue(post.name.startswith("Hello from Social Publisher"))
