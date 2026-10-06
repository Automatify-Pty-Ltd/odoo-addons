import base64

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.automatify_markdown.services import (
    decode_markdown_file,
    html_to_markdown,
    markdown_to_html,
)


class TestMarkdownServices(TransactionCase):
    def test_markdown_to_html_preserves_mermaid_language(self):
        converted = markdown_to_html(
            "# Architecture\n\n```mermaid\nflowchart LR\nA --> B\n```\n"
        )
        self.assertIn("<h1>Architecture</h1>", converted)
        self.assertIn('data-language-id="mermaid"', converted)
        self.assertIn("A --&gt; B", converted)

    def test_html_to_markdown_exports_mermaid_fence(self):
        source = (
            "<p>Diagram</p>"
            '<pre data-embedded="readonlySyntaxHighlighting" '
            'data-language-id="mermaid">flowchart LR<br>A --&gt; B</pre>'
        )
        converted = html_to_markdown(source)
        self.assertIn("```mermaid\nflowchart LR\nA --> B\n```", converted)

    def test_common_markdown_round_trip(self):
        source = (
            "# Title\n\n"
            "This is **bold** and *emphasized* with [a link](https://example.com).\n\n"
            "- one\n- two\n\n"
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        )
        exported = html_to_markdown(markdown_to_html(source))
        self.assertIn("# Title", exported)
        self.assertIn("**bold**", exported)
        self.assertIn("[a link](https://example.com)", exported)
        self.assertIn("| A | B |", exported)

    def test_markdown_is_sanitized(self):
        converted = markdown_to_html("<script>alert('x')</script>\n\nSafe")
        self.assertNotIn("<script", converted)
        self.assertIn("Safe", converted)

    def test_decode_upload_normalizes_filename(self):
        source, filename = decode_markdown_file(
            base64.b64encode(b"# Imported\n"), "../post.md"
        )
        self.assertEqual(source, "# Imported\n")
        self.assertEqual(filename, "post.md")

    def test_decode_upload_rejects_non_markdown(self):
        with self.assertRaises(UserError):
            decode_markdown_file(base64.b64encode(b"text"), "post.txt")
