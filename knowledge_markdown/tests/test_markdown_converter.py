from odoo.tests.common import TransactionCase

from ..services import html_to_markdown, markdown_to_html


class TestMarkdownConverter(TransactionCase):
    def test_markdown_to_html_preserves_mermaid_language(self):
        converted = markdown_to_html(
            "# Architecture\n\n```mermaid\nflowchart LR\nA --> B\n```\n"
        )
        self.assertIn("<h1>Architecture</h1>", converted)
        self.assertIn('data-language-id="mermaid"', converted)
        self.assertIn("flowchart LR", converted)
        self.assertIn("A --&gt; B", converted)

    def test_html_to_markdown_exports_mermaid_fence(self):
        source = (
            '<p>Diagram</p>'
            '<pre data-embedded="readonlySyntaxHighlighting" '
            'data-language-id="mermaid">flowchart LR<br>A --&gt; B</pre>'
        )
        converted = html_to_markdown(source)
        self.assertIn("Diagram", converted)
        self.assertIn("```mermaid\nflowchart LR\nA --> B\n```", converted)

    def test_common_markdown_round_trip(self):
        source = (
            "# Title\n\n"
            "This is **bold** and *emphasized* with [a link](https://example.com).\n\n"
            "- one\n- two\n\n"
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        )
        html_value = markdown_to_html(source)
        exported = html_to_markdown(html_value)

        self.assertIn("# Title", exported)
        self.assertIn("**bold**", exported)
        self.assertIn("*emphasized*", exported)
        self.assertIn("[a link](https://example.com)", exported)
        self.assertIn("- one", exported)
        self.assertIn("| A | B |", exported)

    def test_import_sanitizes_raw_script(self):
        converted = markdown_to_html("<script>alert('x')</script>\n\nSafe")
        self.assertNotIn("<script", converted)
        self.assertIn("Safe", converted)
