import base64
import binascii
import os

from odoo import _
from odoo.exceptions import UserError


DEFAULT_MAX_MARKDOWN_BYTES = 2 * 1024 * 1024


def decode_markdown_file(payload, filename=None, *, max_bytes=DEFAULT_MAX_MARKDOWN_BYTES):
    """Validate and decode a base64-encoded UTF-8 Markdown upload."""
    safe_filename = os.path.basename((filename or "document.md").strip()) or "document.md"
    if not safe_filename.lower().endswith((".md", ".markdown")):
        raise UserError(_("Please upload a .md or .markdown file."))

    try:
        raw = base64.b64decode(payload or b"", validate=True)
    except (binascii.Error, ValueError):
        raise UserError(_("The uploaded file could not be decoded.")) from None

    if len(raw) > max_bytes:
        raise UserError(_("Markdown files are limited to 2 MiB."))

    try:
        return raw.decode("utf-8"), safe_filename
    except UnicodeDecodeError:
        raise UserError(_("The Markdown file must be UTF-8 encoded.")) from None
