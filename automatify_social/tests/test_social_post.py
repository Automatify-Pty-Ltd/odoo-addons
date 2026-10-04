import base64
from datetime import timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.automatify_social.providers.base import (
    AmbiguousPublishError,
    ProviderPublishResult,
)


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

    def test_schedule_rechecks_locked_state_before_targets(self):
        post = self._make_post()
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.flush_recordset(["state"])
        self.env.cr.execute(
            "UPDATE automatify_social_post SET state = %s WHERE id = %s",
            ["processing", post.id],
        )

        with self.assertRaises(UserError):
            post.action_schedule()

        self.assertEqual(post.state, "processing")
        self.assertEqual(post.target_ids.state, "pending")

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

    def test_ambiguous_publish_outcome_is_not_retryable(self):
        post = self._make_post()
        provider = Mock()
        provider.publish.side_effect = AmbiguousPublishError(
            "Provider response was lost after the publish request."
        )

        with patch.object(
            type(self.account), "_get_social_provider", return_value=provider
        ):
            post.action_publish_now()

        self.assertEqual(post.state, "failed")
        self.assertEqual(post.target_ids.state, "unknown")
        self.assertIn("unknown publication outcome", post.failure_reason.lower())
        with self.assertRaises(UserError):
            post.action_retry_failed()
        with self.assertRaises(UserError):
            post.action_publish_now()
        with self.assertRaises(UserError):
            post.action_reset_to_draft()
        self.assertEqual(provider.publish.call_count, 1)

    def test_social_user_publish_elevates_only_provider_account(self):
        social_user = new_test_user(
            self.env,
            login="social-publisher-user",
            groups="automatify_social.group_automatify_social_user",
        )
        provider = Mock()
        provider.publish.return_value = ProviderPublishResult(
            external_post_id="remote-123",
            external_url="https://example.test/status/remote-123",
            published_at=fields.Datetime.now(),
        )
        post = self._make_post().with_user(social_user)

        with patch.object(
            type(self.account), "_get_social_provider", return_value=provider
        ):
            post.action_publish_now()

        published_account, published_post = provider.publish.call_args.args
        self.assertTrue(published_account.env.su)
        self.assertFalse(published_post.env.su)
        self.assertEqual(post.state, "published")

    def test_social_user_cannot_rewrite_target_workflow_fields(self):
        social_user = new_test_user(
            self.env,
            login="social-target-guard-user",
            groups="automatify_social.group_automatify_social_user",
        )
        post = self._make_post()
        target = post.target_ids
        target.sudo().write(
            {
                "state": "unknown",
                "error_message": "Remote publication outcome is unknown",
            }
        )

        with self.assertRaises(AccessError):
            target.with_user(social_user).write({"state": "pending"})
        with self.assertRaises(AccessError):
            target.with_user(social_user).write({"external_post_id": "fake-id"})

        other_post = self.env["automatify.social.post"].create(
            {"message": "Another post", "company_id": self.env.company.id}
        )
        with self.assertRaises(AccessError):
            target.with_user(social_user).write({"post_id": other_post.id})

        with self.assertRaises(AccessError):
            target.with_user(social_user).write({"account_id": self.account.id})
        self.assertEqual(target.state, "unknown")

    def test_cancel_and_reset(self):
        post = self._make_post()
        post.action_cancel()
        self.assertEqual(post.state, "cancelled")
        post.action_reset_to_draft()
        self.assertEqual(post.state, "draft")

    def test_cancel_rechecks_locked_state(self):
        post = self._make_post()
        post.flush_recordset(["state"])
        self.env.cr.execute(
            "UPDATE automatify_social_post SET state = %s WHERE id = %s",
            ["processing", post.id],
        )

        with self.assertRaises(UserError):
            post.action_cancel()

        self.assertEqual(post.state, "processing")

    def test_reset_to_draft_rechecks_locked_state(self):
        post = self._make_post()
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()
        self.assertEqual(post.state, "scheduled")
        post.flush_recordset(["state"])

        self.env.cr.execute(
            "UPDATE automatify_social_post SET state = %s WHERE id = %s",
            ["processing", post.id],
        )

        with self.assertRaises(UserError):
            post.action_reset_to_draft()

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

    def test_retry_rechecks_target_state_after_parent_lock(self):
        post = self._make_post()
        target = post.target_ids
        target.sudo().write({"state": "failed", "error_message": "provider failure"})
        post.sudo().write(
            {
                "state": "failed",
                "failure_reason": "One or more channels failed to publish.",
            }
        )
        self.assertEqual(target.state, "failed")
        target.flush_recordset(["state"])
        self.env.cr.execute(
            "UPDATE automatify_social_post_target SET state = %s WHERE id = %s",
            ["unknown", target.id],
        )

        with self.assertRaises(UserError):
            post.action_retry_failed()

        target.invalidate_recordset(["state"])
        self.assertEqual(target.state, "unknown")

    def test_retry_recovers_remote_success_without_republishing(self):
        post = self._make_post()
        target = post.target_ids
        target.sudo().write(
            {
                "state": "failed",
                "external_post_id": "remote-123",
                "external_url": "https://example.test/status/remote-123",
                "error_message": "Local bookkeeping failed after remote publish",
            }
        )
        post.write(
            {
                "state": "failed",
                "failure_reason": "One or more channels failed to publish.",
            }
        )

        post.action_retry_failed()

        self.assertEqual(post.state, "published")
        self.assertEqual(target.state, "published")
        self.assertEqual(target.external_post_id, "remote-123")
        self.assertEqual(target.external_url, "https://example.test/status/remote-123")
        self.assertTrue(target.published_at)
        self.assertFalse(target.error_message)

    def test_display_name_uses_message_excerpt(self):
        post = self._make_post()
        self.assertTrue(post.name.startswith("Hello from Social Publisher"))
