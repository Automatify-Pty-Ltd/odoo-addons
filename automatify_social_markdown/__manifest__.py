{
    "name": "Social Publisher Markdown",
    "version": "19.0.1.0.1",
    "summary": "Create and update Social Publisher drafts from Markdown files",
    "category": "Marketing/Social Marketing",
    "author": "Automatify Pty Ltd",
    "website": "https://automatify.com.au",
    "support": "admin@automatify.com.au",
    "license": "LGPL-3",
    "depends": ["automatify_social", "automatify_markdown"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/social_markdown_import_wizard_views.xml",
        "views/social_post_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
