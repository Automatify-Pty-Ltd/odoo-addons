from werkzeug.exceptions import NotFound

from odoo.exceptions import AccessError
from odoo.http import Controller, content_disposition, request, route
from odoo.tools import osutil

from ..services import html_to_markdown


class KnowledgeMarkdownController(Controller):
    @route(
        "/knowledge_markdown/export/<int:page_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def export_markdown(self, page_id, **kwargs):
        page = request.env["document.page"].browse(page_id).exists()
        if not page or page.type != "content":
            raise NotFound()

        try:
            page.check_access("read")
        except AccessError:
            raise NotFound() from None

        markdown = html_to_markdown(page.content or "")
        stem = osutil.clean_filename(page.name or f"knowledge-{page.id}") or "knowledge"
        filename = f"{stem}.md"

        return request.make_response(
            markdown.encode("utf-8"),
            headers=[
                ("Content-Type", "text/markdown; charset=utf-8"),
                ("Content-Disposition", content_disposition(filename)),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
