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

    def _make_post(self):
        return self.env["automatify.social.post"].create(
            {
                "message": "Workflow guard test",
                "target_ids": [(0, 0, {"account_id": self.account.id})],
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

    def test_target_account_is_frozen_after_post_leaves_draft(self):
        post = self._make_post()
        target = post.target_ids.with_user(self.social_user)

        target.write({"account_id": self.other_account.id})
        self.assertEqual(target.account_id, self.other_account)

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
