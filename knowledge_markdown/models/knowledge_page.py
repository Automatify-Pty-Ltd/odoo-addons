from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KnowledgeMarkdownPage(models.Model):
    _name = "knowledge.markdown.page"
    _description = "Markdown Knowledge Page"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, tracking=True)
    page_type = fields.Selection(
        [("category", "Category"), ("content", "Page")],
        string="Type",
        default="content",
        required=True,
        tracking=True,
    )
    parent_id = fields.Many2one(
        "knowledge.markdown.page",
        string="Category",
        ondelete="restrict",
        index=True,
        domain=[("page_type", "=", "category")],
        tracking=True,
    )
    child_ids = fields.One2many(
        "knowledge.markdown.page",
        "parent_id",
        string="Children",
    )
    content = fields.Html(sanitize=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    history_ids = fields.One2many(
        "knowledge.markdown.page.history",
        "page_id",
        string="Revisions",
        readonly=True,
    )
    history_count = fields.Integer(compute="_compute_history_count")

    @api.depends("history_ids")
    def _compute_history_count(self):
        for page in self:
            page.history_count = len(page.history_ids)

    @api.constrains("parent_id", "page_type")
    def _check_parent(self):
        if not self._check_recursion():
            raise ValidationError(_("You cannot create recursive Knowledge categories."))
        for page in self:
            if page.parent_id and page.parent_id.page_type != "category":
                raise ValidationError(_("A Knowledge page can only be placed inside a category."))
            if page.page_type == "category" and page.content:
                raise ValidationError(_("Categories cannot contain page content."))

    def action_open_markdown_import(self):
        self.ensure_one()
        if self.page_type != "content":
            raise UserError(_("Markdown import is only available for content pages."))
        self.check_access("write")
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Markdown"),
            "res_model": "knowledge.markdown.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_target_mode": "existing",
                "default_page_id": self.id,
            },
        }

    def action_export_markdown(self):
        self.ensure_one()
        if self.page_type != "content":
            raise UserError(_("Markdown export is only available for content pages."))
        self.check_access("read")
        return {
            "type": "ir.actions.act_url",
            "url": f"/knowledge_markdown/export/{self.id}",
            "target": "self",
        }

    def create_revision(self, name, summary, content):
        self.ensure_one()
        if self.page_type != "content":
            raise UserError(_("Only content pages can have revisions."))
        self.check_access("write")
        self.write({"content": content})
        return self.env["knowledge.markdown.page.history"].create(
            {
                "page_id": self.id,
                "name": name,
                "summary": summary,
                "content": content,
            }
        )


class KnowledgeMarkdownPageHistory(models.Model):
    _name = "knowledge.markdown.page.history"
    _description = "Markdown Knowledge Page Revision"
    _order = "create_date desc, id desc"

    page_id = fields.Many2one(
        "knowledge.markdown.page",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True)
    summary = fields.Char()
    content = fields.Html(sanitize=True)
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
