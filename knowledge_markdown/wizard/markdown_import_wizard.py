import base64
import binascii

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..services import markdown_to_html


MAX_MARKDOWN_BYTES = 2 * 1024 * 1024


class MarkdownImportWizard(models.TransientModel):
    _name = "knowledge.markdown.import.wizard"
    _description = "Import Markdown into Knowledge"

    page_id = fields.Many2one(
        "document.page",
        required=True,
        readonly=True,
        domain=[("type", "=", "content")],
    )
    markdown_file = fields.Binary(string="Markdown file", required=True)
    filename = fields.Char()
    revision_name = fields.Char(default="Markdown import", required=True)
    revision_summary = fields.Char()

    def action_import(self):
        self.ensure_one()
        page = self.page_id.exists()
        if not page or page.type != "content":
            raise UserError(_("The target Knowledge page no longer exists."))
        page.check_access("write")

        filename = (self.filename or "document.md").strip()
        if not filename.lower().endswith((".md", ".markdown")):
            raise UserError(_("Please upload a .md or .markdown file."))

        try:
            raw = base64.b64decode(self.markdown_file or b"", validate=True)
        except (binascii.Error, ValueError):
            raise UserError(_("The uploaded file could not be decoded.")) from None

        if len(raw) > MAX_MARKDOWN_BYTES:
            raise UserError(_("Markdown files are limited to 2 MiB."))

        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise UserError(_("The Markdown file must be UTF-8 encoded.")) from None

        converted = markdown_to_html(source)
        summary = self.revision_summary or _("Imported from %s", filename)
        page._create_history(
            {
                "page_id": page.id,
                "name": self.revision_name,
                "summary": summary,
                "content": converted,
            }
        )

        return {"type": "ir.actions.client", "tag": "reload"}
