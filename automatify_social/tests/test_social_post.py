import base64
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

    def _make_image(self, name="social.png"):
        return self.env["ir.attachment"].create(
            {
                "name": name,
                "type": "binary",
                "mimetype": "image/png",
                "datas": base64.b64encode(b"fake-png-data"),
            }
        )

    def test_access_groups_use_odoo19_privilege(self):
        privilege = self.env.ref("automatify_social.privilege_automatify_social_marketing")
        user_group = self.env.ref("automatify_social.group_automatify_social_user")
        manager_group = self.env.ref("automatify_social.group_automatify_social_manager")

        self.assertEqual(privilege.name, "Social Marketing")
        self.assertEqual(privilege.category_id, self.env.ref("base.module_category_marketing"))
        self.assertEqual(user_group.privilege_id, privilege)
        self.assertEqual(manager_group.privilege_id, privilege)
        self.assertIn(user_group, manager_group.implied_ids)

    def test_rich_content_renders_provider_safe_text(self):
        post = self.env["automatify.social.post"].create(
            {
                "message": (
                    "<p>Hello <strong>Odoo</strong></p>"
                    "<p><a href='https://automatify.com.au'>Automatify</a></p>"
                )
            }
        )
        self.assertIn("Hello *Odoo*", post.message_text)
        self.assertIn("Automatify [1]", post.message_text)
        self.assertIn("[1] https://automatify.com.au", post.message_text)

    def test_empty_html_content_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["automatify.social.post"].create({"message": "<p><br></p>"})

    def test_single_image_attachment_is_supported(self):
        post = self._make_post()
        image = self._make_image()
        post.image_ids = image
        self.assertEqual(post.image_ids, image)

    def test_more_than_one_image_is_rejected_for_stage_1_1(self):
        post = self._make_post()
        first = self._make_image("first.png")
        second = self._make_image("second.png")
        with self.assertRaises(ValidationError):
            post.image_ids = first | second

    def test_schedule_requires_future_datetime(self):
        post = self._make_post()
        with self.assertRaises(UserError):
            post.action_schedule()

        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()
        self.assertEqual(post.state, "scheduled")

    def test_post_now_from_draft_clears_incidental_scheduled_at(self):
        post = self._make_post()
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_publish_now()
        self.assertFalse(post.scheduled_at)

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
