import base64
import binascii
import os
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..services import markdown_to_html


MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
_ATX_H1_RE = re.compile(r"(?m)^\s*#\s+(.+?)\s*#*\s*$")
_INLINE_MARKUP_RE = re.compile(r"[*_`~]+")


class MarkdownImportWizard(models.TransientModel):
    _name = "knowledge.markdown.import.wizard"
    _description = "Import Markdown into Knowledge"

    target_mode = fields.Selection(
        [("new", "New Knowledge page"), ("existing", "Existing Knowledge page")],
        default="new",
        required=True,
        readonly=True,
    )
    page_id = fields.Many2one(
        "document.page",
        readonly=True,
        domain=[("type", "=", "content")],
    )
    parent_id = fields.Many2one(
        "document.page",
        string="Category",
        domain=[("type", "=", "category")],
    )
    page_name = fields.Char(
        string="Title",
        help="Optional. If empty, the first level-one Markdown heading or the file name is used.",
    )
    markdown_file = fields.Binary(string="Markdown file", required=True)
    filename = fields.Char()
    revision_name = fields.Char(default="Markdown import", required=True)
    revision_summary = fields.Char()

    def action_import(self):
        self.ensure_one()
        source, filename = self._decode_markdown_file()
        converted = markdown_to_html(source)
        summary = self.revision_summary or _("Imported from %s", filename)

        if self.target_mode == "existing":
            return self._import_into_existing(converted, summary)
        if self.target_mode == "new":
            return self._create_page(source, converted, filename, summary)
        raise UserError(_("Unsupported Markdown import target."))

    def _import_into_existing(self, converted, summary):
        page = self.page_id.exists()
        if not page or page.type != "content":
            raise UserError(_("The target Knowledge page no longer exists."))
        page.check_access("write")
        page._create_history(
            {
                "page_id": page.id,
                "name": self.revision_name,
                "summary": summary,
                "content": converted,
            }
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def _create_page(self, source, converted, filename, summary):
        parent = self.parent_id.exists()
        if not parent or parent.type != "category":
            raise UserError(_("Choose a Knowledge category for the new page."))
        parent.check_access("read")

        Page = self.env["document.page"]
        Page.check_access("create")
        title = self._page_title(source, filename)
        page = Page.create(
            {
                "name": title,
                "type": "content",
                "parent_id": parent.id,
            }
        )
        page._create_history(
            {
                "page_id": page.id,
                "name": self.revision_name,
                "summary": summary,
                "content": converted,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": page.name,
            "res_model": "document.page",
            "res_id": page.id,
            "view_mode": "form",
            "target": "current",
        }

    def _decode_markdown_file(self):
        filename = os.path.basename((self.filename or "document.md").strip()) or "document.md"
        if not filename.lower().endswith((".md", ".markdown")):
            raise UserError(_("Please upload a .md or .markdown file."))

        try:
            raw = base64.b64decode(self.markdown_file or b"", validate=True)
        except (binascii.Error, ValueError):
            raise UserError(_("The uploaded file could not be decoded.")) from None

        if len(raw) > MAX_MARKDOWN_BYTES:
            raise UserError(_("Markdown files are limited to 2 MiB."))

        try:
            return raw.decode("utf-8"), filename
        except UnicodeDecodeError:
            raise UserError(_("The Markdown file must be UTF-8 encoded.")) from None

    def _page_title(self, source, filename):
        explicit = (self.page_name or "").strip()
        if explicit:
            return explicit

        heading = _ATX_H1_RE.search(source or "")
        if heading:
            title = _INLINE_MARKUP_RE.sub("", heading.group(1)).strip()
            if title:
                return title[:200]

        stem = os.path.splitext(filename)[0]
        fallback = re.sub(r"[_-]+", " ", stem).strip()
        return (fallback or _("Imported Markdown"))[:200]
