{
    "name": "Inventify Inventory Connect",
    "version": "19.0.1.0.0",
    "summary": "Connect Inventify to Odoo Inventory without sharing Odoo passwords or generic API keys",
    "category": "Inventory",
    "author": "Automatify Pty Ltd",
    "website": "https://automatify.com.au",
    "license": "AGPL-3",
    "depends": ["external_app_connect", "stock"],
    "data": [
        "data/scopes.xml",
        "data/client.xml",
    ],
    "installable": True,
    "application": False,
}
