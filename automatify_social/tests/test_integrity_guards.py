import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSocialIntegrityGuards(TransactionCase):
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
                    "name": "Integrity Guard Account",
                    "platform": "test",
                    "company_id": self.env.company.id,
                }
            )

    def _make_attachment(self, payload=b"original-image"):
        return self.env["ir.attachment"].create(
            {
                "name": "social-image.png",
                "datas": base64.b64encode(payload),
                "mimetype": "image/png",
            }
        )

    def _make_post(self, attachment=None):
        values = {
            "message": "Integrity guard test",
            "target_ids": [(0, 0, {"account_id": self.account.id})],
        }
        if attachment:
            values["image_ids"] = [(6, 0, [attachment.id])]
        return self.env["automatify.social.post"].create(values)

    def test_only_draft_posts_can_be_deleted(self):
        draft = self._make_post()
        draft_id = draft.id
        draft.unlink()
        self.assertFalse(self.env["automatify.social.post"].browse(draft_id).exists())

        scheduled = self._make_post()
        scheduled.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        scheduled.action_schedule()

        with self.assertRaises(UserError):
            scheduled.unlink()

        self.assertTrue(scheduled.exists())
        self.assertEqual(scheduled.state, "scheduled")

    def test_delete_rechecks_persisted_state_after_lock(self):
        post = self._make_post()
        post.flush_recordset(["state"])
        self.env.cr.execute(
            "UPDATE automatify_social_post SET state = %s WHERE id = %s",
            ["processing", post.id],
        )

        with self.assertRaises(UserError):
            post.unlink()

        post.invalidate_recordset(["state"])
        self.assertTrue(post.exists())
        self.assertEqual(post.state, "processing")

    def test_social_image_bytes_and_delete_are_frozen_outside_draft(self):
        attachment = self._make_attachment()
        post = self._make_post(attachment)

        attachment.write({"datas": base64.b64encode(b"draft-update")})
        post.scheduled_at = fields.Datetime.now() + timedelta(hours=1)
        post.action_schedule()

        with self.assertRaises(UserError):
            attachment.write({"datas": base64.b64encode(b"late-update")})
        with self.assertRaises(UserError):
            attachment.unlink()

        self.assertTrue(attachment.exists())
        self.assertEqual(post.state, "scheduled")

    def test_social_image_guard_rechecks_persisted_parent_state(self):
        attachment = self._make_attachment()
        post = self._make_post(attachment)
        post.flush_recordset(["state"])
        self.env.cr.execute(
            "UPDATE automatify_social_post SET state = %s WHERE id = %s",
            ["processing", post.id],
        )

        with self.assertRaises(UserError):
            attachment.write({"datas": base64.b64encode(b"racing-update")})

        post.invalidate_recordset(["state"])
        self.assertEqual(post.state, "processing")
