from odoo import _, models
from odoo.exceptions import UserError


class AutomatifySocialPost(models.Model):
    _inherit = "automatify.social.post"

    def action_open_markdown_import(self):
        self.ensure_one()
        self.check_access("write")
        if self.state in ("processing", "published"):
            raise UserError(
                _("Markdown can only be imported before publication has completed.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Markdown"),
            "res_model": "automatify.social.markdown.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_post_id": self.id},
        }
