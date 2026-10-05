{
    "name": "External App Connect",
    "version": "19.0.1.0.0",
    "summary": "OAuth-style authorization code + PKCE connections for external apps",
    "category": "Technical",
    "author": "Automatify Pty Ltd",
    "website": "https://github.com/Automatify-Pty-Ltd/odoo-addons",
    "license": "AGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/scopes.xml",
        "views/external_app_connect_views.xml",
        "views/external_app_connect_templates.xml",
    ],
    "installable": True,
    "application": False,
}
