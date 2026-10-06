# Markdown Core

Reusable Markdown services for Odoo 19.

This technical addon contains the shared Markdown engine used by Automatify addons.
It has no Knowledge or Social Publisher models, menus, or provider integrations.

## Features

- Convert Markdown to sanitized Odoo HTML.
- Convert Odoo HTML back to portable Markdown.
- Preserve headings, emphasis, links, images, lists, blockquotes, tables, inline
  code, fenced code blocks, and Mermaid language identifiers.
- Validate uploaded `.md` / `.markdown` files, UTF-8 encoding, and a 2 MiB
  default size limit.

## Consumers

- `knowledge_markdown` provides standalone Markdown knowledge pages.
- `automatify_social_markdown` imports Markdown into Social Publisher drafts.

## Dependencies

- Odoo 19
- Python `Markdown>=3.5,<4`

LGPL-3.0.
