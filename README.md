# Automatify Odoo Addons

Open-source Odoo addons maintained by Automatify Pty Ltd.

This repository contains small, focused modules that solve practical Odoo problems without depending on private Automatify infrastructure or secrets.

## Addons

| Addon | Odoo | Purpose |
| --- | --- | --- |
| [`automatify_markdown`](automatify_markdown/) | 19.0 | Shared Markdown conversion, sanitization, and upload validation core. |
| [`knowledge_markdown`](knowledge_markdown/) | 19.0 | Standalone Markdown knowledge pages with revisions and import/export. |
| [`external_app_connect`](external_app_connect/) | 19.0 | Secure authorization-code + PKCE connections from external apps to scoped Odoo endpoints. |
| [`inventify_inventory_connect`](inventify_inventory_connect/) | 19.0 | One-click Inventify connection, Inventory discovery, and per-connection root configuration. |
| [`automatify_social`](automatify_social/) | 19.0 | Open social publishing core with scheduling, retries, multi-company isolation, and connector hooks. |
| [`automatify_social_linkedin`](automatify_social_linkedin/) | 19.0 | LinkedIn OAuth and text-post publishing connector for Social Publisher. |
| [`automatify_social_x`](automatify_social_x/) | 19.0 | X OAuth 2.0 PKCE and text-post publishing connector for Social Publisher. |
| [`automatify_social_markdown`](automatify_social_markdown/) | 19.0 | Create or update Social Publisher drafts from Markdown files. |

`external_app_connect` is the reusable connection/security layer. App-specific addons such as `inventify_inventory_connect` add narrow business scopes and endpoints without exposing generic Odoo RPC access.

The Social Publisher connectors contain no provider credentials. Each installation uses its own provider developer app, permissions, API access, and provider-side limits. Internal Automatify deployment configuration is deliberately kept outside this public repository.

Each addon documents its own dependencies, installation steps, supported scope, external services, and license.

## Security

Do not commit credentials, access tokens, private keys, internal deployment configuration, or customer/account identifiers. See [SECURITY.md](SECURITY.md) for private vulnerability reporting.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
