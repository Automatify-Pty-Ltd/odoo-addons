{
    "name": "Knowledge Markdown",
    "version": "19.0.0.1.0",
    "summary": "Import and export OCA Knowledge pages as Markdown",
    "category": "Knowledge",
    "author": "Automatify Pty Ltd",
    "website": "https://github.com/Automatify-Pty-Ltd/odoo-addons",
    "license": "AGPL-3",
    "depends": ["document_page"],
    "external_dependencies": {"python": ["markdown"]},
    "data": [
        "security/ir.model.access.csv",
        "views/markdown_import_wizard_views.xml",
        "views/document_page_views.xml",
    ],
    "installable": True,
    "application": False,
}
