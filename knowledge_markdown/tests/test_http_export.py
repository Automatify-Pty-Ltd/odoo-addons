from urllib.parse import unquote

from odoo.tests.common import HttpCase


class TestMarkdownHttpExport(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.page = cls.env["document.page"].create(
            {
                "name": "Export Test",
                "type": "content",
            }
        )
        cls.page._create_history(
            {
                "page_id": cls.page.id,
                "name": "Initial",
                "summary": "Export fixture",
                "content": (
                    "<h1>Exported</h1>"
                    '<pre data-embedded="readonlySyntaxHighlighting" '
                    'data-language-id="mermaid">flowchart LR<br>A --&gt; B</pre>'
                ),
            }
        )

    def test_authenticated_export_downloads_markdown(self):
        self.authenticate("admin", "admin")
        response = self.url_open(f"/knowledge_markdown/export/{self.page.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("text/markdown", response.headers.get("Content-Type", ""))
        disposition = unquote(response.headers.get("Content-Disposition", ""))
        self.assertIn("Export Test.md", disposition)
        self.assertIn("# Exported", response.text)
        self.assertIn("```mermaid\nflowchart LR\nA --> B\n```", response.text)
