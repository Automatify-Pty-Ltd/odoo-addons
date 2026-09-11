import base64

from odoo.tests.common import TransactionCase


class TestMarkdownImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["document.page"].create(
            {
                "name": "Markdown Category",
                "type": "category",
            }
        )
        cls.page = cls.env["document.page"].create(
            {
                "name": "Markdown Test",
                "type": "content",
                "parent_id": cls.category.id,
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
                "target_mode": "existing",
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

    def test_import_can_create_new_page_from_file(self):
        wizard = self.env["knowledge.markdown.import.wizard"].create(
            {
                "target_mode": "new",
                "parent_id": self.category.id,
                "markdown_file": base64.b64encode(
                    b"# Architecture Notes\n\nSome text.\n\n```mermaid\nA --> B\n```\n"
                ),
                "filename": "architecture-notes.md",
                "revision_name": "Markdown import",
            }
        )

        action = wizard.action_import()
        page = self.env["document.page"].browse(action["res_id"])

        self.assertTrue(page.exists())
        self.assertEqual(page.name, "Architecture Notes")
        self.assertEqual(page.parent_id, self.category)
        self.assertEqual(page.type, "content")
        self.assertEqual(page.history_head.name, "Markdown import")
        self.assertEqual(page.history_head.summary, "Imported from architecture-notes.md")
        self.assertIn("<h1>Architecture Notes</h1>", page.content)
        self.assertIn('data-language-id="mermaid"', page.content)
        self.assertEqual(action["res_model"], "document.page")
        self.assertEqual(action["view_mode"], "form")

    def test_explicit_title_overrides_markdown_heading(self):
        wizard = self.env["knowledge.markdown.import.wizard"].create(
            {
                "target_mode": "new",
                "parent_id": self.category.id,
                "page_name": "Custom title",
                "markdown_file": base64.b64encode(b"# File heading\n"),
                "filename": "fallback-title.md",
                "revision_name": "Markdown import",
            }
        )

        action = wizard.action_import()
        page = self.env["document.page"].browse(action["res_id"])
        self.assertEqual(page.name, "Custom title")
