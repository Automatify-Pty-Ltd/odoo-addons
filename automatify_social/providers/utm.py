"""Opt-in campaign tags for outbound links on explicitly configured websites."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def tag_social_links(text, configured_hosts, source, post_id):
    """Keep the authored text intact; add only missing tags to approved hosts."""
    hosts = {host.strip().lower() for host in (configured_hosts or "").split(",") if host.strip()}
    if not hosts or not source or not post_id:
        return text
    tags = {
        "utm_source": source,
        "utm_medium": "social",
        "utm_campaign": "odoo_social",
        "utm_content": f"post_{post_id}",
    }

    def replace(match):
        original = match.group(0)
        url = original.rstrip(".,;:!?")
        # A surrounding sentence/Markdown link may have unmatched closing brackets.
        while url and url[-1] in ")]}":
            closing = url[-1]
            opening = {")": "(", "]": "[", "}": "{"}[closing]
            if url.count(closing) <= url.count(opening):
                break
            url = url[:-1]
        suffix = original[len(url):]
        try:
            parts = urlsplit(url)
            if (
                parts.hostname not in hosts
                or parts.username is not None
                or parts.password is not None
                or parts.port not in (None, 443 if parts.scheme == "https" else 80)
            ):
                return original
            keys = {key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
            # Do not modify signed/authentication URLs, even on an approved host.
            if keys.intersection({"signature", "sig", "token", "access_token", "auth", "code", "x-amz-signature", "x-goog-signature"}):
                return original
            missing = {key: value for key, value in tags.items() if key not in keys}
            if not missing:
                return original
            # Preserve the original encoded query instead of re-encoding it.
            query = parts.query + ("&" if parts.query else "") + urlencode(missing)
            return urlunsplit(parts._replace(query=query)) + suffix
        except ValueError:
            return original

    return _URL.sub(replace, text)
