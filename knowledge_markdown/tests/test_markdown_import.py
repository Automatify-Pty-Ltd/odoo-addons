import base64

from odoo.tests.common import TransactionCase


class TestMarkdownImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.page = cls.env["document.page"].create(
            {
                "name": "Markdown Test",
                "type": "content",
            }
        )
        cls.page._create_history(
            {
                "page_id": cls.page.id,
                "name": "Initial",
                "summary": "Initial content",
                "content": "<p>Before</p>",
            }
        )

    def test_import_creates_new_history_revision(self):
        before_count = self.env["document.page.history"].search_count(
            [("page_id", "=", self.page.id)]
        )
        wizard = self.env["knowledge.markdown.import.wizard"].create(
            {
                "page_id": self.page.id,
                "markdown_file": base64.b64encode(
                    b"# Imported\n\n```mermaid\nflowchart LR\nA --> B\n```\n"
                ),
                "filename": "architecture.md",
                "revision_name": "Markdown import",
            }
        )

        action = wizard.action_import()
        after_count = self.env["document.page.history"].search_count(
            [("page_id", "=", self.page.id)]
        )
        latest = self.env["document.page.history"].search(
            [("page_id", "=", self.page.id)], order="id DESC", limit=1
        )

        self.assertEqual(after_count, before_count + 1)
        self.assertEqual(latest.name, "Markdown import")
        self.assertEqual(latest.summary, "Imported from architecture.md")
        self.assertIn("<h1>Imported</h1>", latest.content)
        self.assertIn('data-language-id="mermaid"', latest.content)
        self.assertEqual(action, {"type": "ir.actions.client", "tag": "reload"})
