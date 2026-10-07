# Social Publisher Markdown

Import Markdown files into the open-source Social Publisher for Odoo 19.

## What it does

- Create a new Social Post draft from a UTF-8 `.md` or `.markdown` file.
- Import Markdown into an existing editable Social Post.
- Render Markdown into sanitized Odoo HTML for the existing rich-text editor.
- Reuse Social Publisher's existing provider-safe `message_text` conversion.
- Keep publishing explicit: importing Markdown never posts automatically.

The addon works with the free `automatify_social` core. LinkedIn and X continue to
publish through their existing connector addons, so no provider-specific Markdown
logic is duplicated.

## Usage

- **Social Marketing → New from Markdown** creates a new draft.
- Use **New from Markdown** when creating a new post.
- Open a saved editable Social Post and click **Import Markdown** to replace its content.
- Review the rendered draft, choose LinkedIn/X accounts, then use **Post Now** or
  **Schedule** as usual.

## Dependencies

- `automatify_social`
- `automatify_markdown`

LGPL-3.0.
