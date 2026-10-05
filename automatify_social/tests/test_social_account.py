from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSocialAccount(TransactionCase):
    def setUp(self):
        super().setUp()
        account_model = self.env["automatify.social.account"]
        with patch.object(
            type(account_model),
            "_social_platform_selection",
            return_value=[("test", "Test Provider"), ("other", "Other Provider")],
        ):
            self.account = account_model.create(
                {
                    "name": "Company-bound Social Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )

    def test_company_ownership_is_immutable(self):
        other_company = self.env["res.company"].create({"name": "Other Social Company"})

        with self.assertRaises(UserError):
            self.account.write({"company_id": other_company.id})

        self.assertEqual(self.account.company_id, self.env.company)

    def test_platform_is_immutable(self):
        with self.assertRaises(UserError):
            self.account.write({"platform": "other"})

        self.assertEqual(self.account.platform, "test")

    def test_queued_post_cannot_be_rebound_by_moving_account(self):
        post = self.env["automatify.social.post"].create(
            {
                "message": "Queued company-isolated post",
                "target_ids": [(0, 0, {"account_id": self.account.id})],
            }
        )
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()
        other_company = self.env["res.company"].create({"name": "Queued Other Company"})

        with self.assertRaises(UserError):
            self.account.write({"company_id": other_company.id})

        self.assertEqual(post.state, "scheduled")
        self.assertEqual(post.target_ids.account_id, self.account)
        self.assertEqual(self.account.company_id, post.company_id)

    def test_duplicate_resets_connection_metadata(self):
        now = fields.Datetime.now()
        self.account.write(
            {
                "handle": "@original",
                "external_account_id": "remote-account-123",
                "connection_state": "connected",
                "last_sync_at": now,
                "last_error": "stale error",
            }
        )

        duplicate = self.account.copy({"name": "Duplicated Social Account"})

        self.assertEqual(duplicate.platform, self.account.platform)
        self.assertEqual(duplicate.company_id, self.account.company_id)
        self.assertEqual(duplicate.connection_state, "disconnected")
        self.assertFalse(duplicate.handle)
        self.assertFalse(duplicate.external_account_id)
        self.assertFalse(duplicate.last_sync_at)
        self.assertFalse(duplicate.last_error)

    def test_same_identity_write_remains_allowed(self):
        self.account.write(
            {
                "company_id": self.env.company.id,
                "platform": self.account.platform,
                "name": "Renamed Social Account",
            }
        )

        self.assertEqual(self.account.name, "Renamed Social Account")
