from odoo import _, models
from odoo.exceptions import UserError


class DocumentPage(models.Model):
    _inherit = "document.page"

    def action_open_markdown_import(self):
        self.ensure_one()
        if self.type != "content":
            raise UserError(_("Markdown import is only available for content pages."))
        self.check_access("write")
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Markdown"),
            "res_model": "knowledge.markdown.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_page_id": self.id},
        }

    def action_export_markdown(self):
        self.ensure_one()
        if self.type != "content":
            raise UserError(_("Markdown export is only available for content pages."))
        self.check_access("read")
        return {
            "type": "ir.actions.act_url",
            "url": f"/knowledge_markdown/export/{self.id}",
            "target": "self",
        }
