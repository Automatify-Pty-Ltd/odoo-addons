{
    "name": "Knowledge Markdown",
    "version": "19.0.2.0.0",
    "summary": "Create, import, edit, and export Markdown knowledge pages",
    "category": "Knowledge",
    "author": "Automatify Pty Ltd",
    "website": "https://github.com/Automatify-Pty-Ltd/odoo-addons",
    "license": "AGPL-3",
    "depends": ["automatify_markdown", "mail", "html_editor"],
    "data": [
        "security/ir.model.access.csv",
        "views/knowledge_page_views.xml",
        "views/markdown_import_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "knowledge_markdown/static/src/cog_menu/markdown_import_menu.js",
            "knowledge_markdown/static/src/cog_menu/markdown_import_menu.xml",
        ],
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
}
