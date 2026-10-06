import base64

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSocialMarkdownImport(TransactionCase):
    def _wizard(self, source, *, post=None, filename="post.md"):
        return self.env["automatify.social.markdown.import.wizard"].create(
            {
                "post_id": post.id if post else False,
                "markdown_file": base64.b64encode(source.encode("utf-8")),
                "filename": filename,
            }
        )

    def test_create_draft_from_markdown(self):
        action = self._wizard("# Launch\n\nHello **Odoo**.").action_import()
        post = self.env["automatify.social.post"].browse(action["res_id"])

        self.assertTrue(post.exists())
        self.assertEqual(post.state, "draft")
        self.assertIn("<h1>Launch</h1>", post.message)
        self.assertIn("Hello *Odoo*.", post.message_text)
        self.assertEqual(action["res_model"], "automatify.social.post")

    def test_import_markdown_into_existing_draft(self):
        post = self.env["automatify.social.post"].create(
            {"message": "<p>Before</p>", "company_id": self.env.company.id}
        )

        action = self._wizard("# Updated\n\nNew content.", post=post).action_import()

        self.assertEqual(action, {"type": "ir.actions.client", "tag": "reload"})
        self.assertIn("<h1>Updated</h1>", post.message)
        self.assertIn("New content.", post.message_text)

    def test_import_rejects_published_post(self):
        post = self.env["automatify.social.post"].create(
            {"message": "<p>Before</p>", "company_id": self.env.company.id}
        )
        post.sudo().write({"state": "published"})

        with self.assertRaises(UserError):
            self._wizard("# Updated", post=post).action_import()

    def test_import_rejects_non_markdown_file(self):
        with self.assertRaises(UserError):
            self._wizard("plain text", filename="post.txt").action_import()
