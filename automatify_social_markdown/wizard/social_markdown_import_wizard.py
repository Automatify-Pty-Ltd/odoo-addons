from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.automatify_markdown.services import (
    decode_markdown_file,
    markdown_to_html,
)


class SocialMarkdownImportWizard(models.TransientModel):
    _name = "automatify.social.markdown.import.wizard"
    _description = "Import Markdown into Social Publisher"

    post_id = fields.Many2one(
        "automatify.social.post",
        string="Social Post",
        readonly=True,
    )
    markdown_file = fields.Binary(string="Markdown file", required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        source, _filename = decode_markdown_file(self.markdown_file, self.filename)
        converted = markdown_to_html(source)

        if self.post_id:
            post = self.post_id.exists()
            if not post:
                raise UserError(_("The target Social Post no longer exists."))
            post.check_access("write")
            post.write({"message": converted})
            return {"type": "ir.actions.client", "tag": "reload"}

        Post = self.env["automatify.social.post"]
        Post.check_access("create")
        post = Post.create(
            {
                "message": converted,
                "company_id": self.env.company.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": post.name,
            "res_model": "automatify.social.post",
            "res_id": post.id,
            "view_mode": "form",
            "target": "current",
        }
