# Automatify Odoo Addons

Open-source Odoo addons maintained by Automatify Pty Ltd.

This repository contains small, focused modules that solve practical Odoo problems without depending on private Automatify infrastructure or secrets.

## Addons

| Addon | Odoo | Purpose |
| --- | --- | --- |
| [`knowledge_markdown`](knowledge_markdown/) | 19.0 | Import and export OCA Knowledge pages as Markdown. |
| [`external_app_connect`](external_app_connect/) | 19.0 | Secure authorization-code + PKCE connections from external apps to scoped Odoo endpoints. |
| [`inventify_inventory_connect`](inventify_inventory_connect/) | 19.0 | One-click Inventify connection, Inventory discovery, and per-connection root configuration. |

`external_app_connect` is the reusable connection/security layer. App-specific addons such as `inventify_inventory_connect` add narrow business scopes and endpoints without exposing generic Odoo RPC access.

Each addon documents its own dependencies, installation steps, supported scope, and license.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
