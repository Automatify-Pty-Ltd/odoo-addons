from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.automatify_social.models.social_post import AutomatifySocialPost
from odoo.addons.automatify_social.providers.base import ProviderPublishResult


class TestPublishBookkeeping(TransactionCase):
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
                    "name": "Bookkeeping Test Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )
        self.post = self.env["automatify.social.post"].create(
            {
                "message": "Remote success bookkeeping failure",
                "target_ids": [(0, 0, {"account_id": self.account.id})],
            }
        )

    def test_remote_success_bookkeeping_failure_becomes_unknown(self):
        provider = Mock()
        provider.publish.return_value = ProviderPublishResult(
            external_post_id="remote-456",
            external_url="https://example.test/status/remote-456",
            published_at=fields.Datetime.now(),
        )
        target = self.post.target_ids
        target_model = type(target)
        original_write = target_model.write

        def reject_published_result(recordset, vals):
            if vals.get("state") == "published":
                raise ValidationError("Installed extension rejected the result value")
            return original_write(recordset, vals)

        with patch.object(
            type(self.account), "_get_social_provider", return_value=provider
        ), patch.object(target_model, "write", reject_published_result):
            self.post.action_publish_now()

        self.assertEqual(provider.publish.call_count, 1)
        self.assertEqual(self.post.state, "failed")
        self.assertEqual(target.state, "unknown")
        self.assertIn("Remote publication succeeded", target.error_message)
        self.assertIn("remote-456", target.error_message)

        with self.assertRaises(UserError):
            self.post.action_retry_failed()
        self.assertEqual(provider.publish.call_count, 1)

    def test_parent_finalization_failure_preserves_remote_success(self):
        provider = Mock()
        provider.publish.return_value = ProviderPublishResult(
            external_post_id="remote-789",
            external_url="https://example.test/status/remote-789",
            published_at=fields.Datetime.now(),
        )
        target = self.post.target_ids
        original_workflow_write = AutomatifySocialPost._write_workflow_values

        def reject_parent_published(recordset, vals):
            if vals.get("state") == "published":
                raise ValidationError("Installed extension rejected parent publication")
            return original_workflow_write(recordset, vals)

        with patch.object(
            type(self.account), "_get_social_provider", return_value=provider
        ), patch.object(
            AutomatifySocialPost,
            "_write_workflow_values",
            reject_parent_published,
        ):
            self.post.action_publish_now()

        self.assertEqual(provider.publish.call_count, 1)
        self.assertEqual(target.state, "published")
        self.assertEqual(target.external_post_id, "remote-789")
        self.assertEqual(self.post.state, "failed")
        self.assertIn("could not finalize", self.post.failure_reason)

        with self.assertRaises(UserError):
            self.post.action_retry_failed()
        self.assertEqual(provider.publish.call_count, 1)
