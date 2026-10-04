from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


class TestSocialWorkflowGuards(TransactionCase):
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
                    "name": "Primary Social Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )
            self.other_account = account_model.create(
                {
                    "name": "Other Social Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )
        self.social_user = new_test_user(
            self.env,
            login="social-workflow-guard-user",
            groups="automatify_social.group_automatify_social_user",
        )
        self.social_user.write(
            {
                "company_id": self.env.company.id,
                "company_ids": [(6, 0, [self.env.company.id])],
            }
        )

    def _make_post(self):
        return self.env["automatify.social.post"].create(
            {
                "message": "Workflow guard test",
                "target_ids": [(0, 0, {"account_id": self.account.id})],
            }
        )

    def _make_other_company_post(self):
        other_company = self.env["res.company"].create({"name": "Restricted Company"})
        account_model = self.env["automatify.social.account"]
        with patch.object(
            type(account_model),
            "_social_platform_selection",
            return_value=[("test", "Test Provider")],
        ):
            other_account = account_model.create(
                {
                    "name": "Restricted Social Account",
                    "platform": "test",
                    "company_id": other_company.id,
                }
            )
        return self.env["automatify.social.post"].create(
            {
                "message": "Restricted company post",
                "company_id": other_company.id,
                "target_ids": [(0, 0, {"account_id": other_account.id})],
            }
        )

    def test_social_user_cannot_rewrite_parent_workflow_fields(self):
        post = self._make_post().with_user(self.social_user)

        with self.assertRaises(AccessError):
            post.write({"state": "failed"})
        with self.assertRaises(AccessError):
            post.write({"published_at": fields.Datetime.now()})
        with self.assertRaises(AccessError):
            post.write({"failure_reason": "forged failure"})

    def test_social_user_actions_can_still_transition_workflow(self):
        post = self._make_post().with_user(self.social_user)
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)

        post.action_schedule()

        self.assertEqual(post.state, "scheduled")

    def test_cross_company_user_cannot_cancel_or_reset(self):
        post = self._make_other_company_post()

        with self.assertRaises(AccessError):
            post.with_user(self.social_user).action_cancel()
        self.assertEqual(post.state, "draft")

        post.sudo().write({"state": "scheduled"})
        with self.assertRaises(AccessError):
            post.with_user(self.social_user).action_reset_to_draft()
        post.invalidate_recordset(["state"])
        self.assertEqual(post.state, "scheduled")

    def test_social_user_can_duplicate_draft_as_clean_draft(self):
        post = self._make_post().with_user(self.social_user)

        duplicate = post.copy()

        self.assertEqual(duplicate.state, "draft")
        self.assertFalse(duplicate.scheduled_at)
        self.assertFalse(duplicate.published_at)
        self.assertFalse(duplicate.failure_reason)
        self.assertEqual(duplicate.target_ids.state, "pending")

    def test_duplicate_published_post_clears_workflow_and_remote_results(self):
        post = self._make_post()
        target = post.target_ids
        published_at = fields.Datetime.now()
        target.sudo().write(
            {
                "state": "published",
                "external_post_id": "remote-123",
                "external_url": "https://example.test/status/remote-123",
                "published_at": published_at,
                "error_message": "old result",
            }
        )
        post.sudo().write(
            {
                "state": "published",
                "scheduled_at": published_at - timedelta(hours=1),
                "published_at": published_at,
                "failure_reason": "old failure",
            }
        )

        duplicate = post.copy()
        duplicate_target = duplicate.target_ids

        self.assertEqual(duplicate.state, "draft")
        self.assertFalse(duplicate.scheduled_at)
        self.assertFalse(duplicate.published_at)
        self.assertFalse(duplicate.failure_reason)
        self.assertEqual(duplicate_target.state, "pending")
        self.assertFalse(duplicate_target.external_post_id)
        self.assertFalse(duplicate_target.external_url)
        self.assertFalse(duplicate_target.published_at)
        self.assertFalse(duplicate_target.error_message)

    def test_target_account_is_frozen_after_post_leaves_draft(self):
        post = self._make_post()
        target = post.target_ids.with_user(self.social_user)

        target.write({"account_id": self.other_account.id})
        self.assertEqual(target.account_id.id, self.other_account.id)

        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.with_user(self.social_user).action_schedule()

        with self.assertRaises(AccessError):
            target.write({"account_id": self.account.id})

    def test_target_account_is_frozen_after_target_leaves_pending(self):
        post = self._make_post()
        target = post.target_ids
        target.sudo().write({"state": "failed", "error_message": "provider failure"})

        with self.assertRaises(AccessError):
            target.with_user(self.social_user).write({"account_id": self.other_account.id})
