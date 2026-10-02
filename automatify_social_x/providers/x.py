from datetime import datetime, timezone

import requests

from odoo.exceptions import UserError

from odoo.addons.automatify_social.providers.base import ProviderPublishResult, SocialProvider


class XProvider(SocialProvider):
    key = "x"
    label = "X"
    endpoint = "https://api.x.com/2/tweets"
    timeout = 20

    def publish(self, account, post):
        token = account._x_get_access_token()
        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"text": post.message},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"X request failed: {exc}") from exc

        if response.status_code != 201:
            detail = (response.text or "")[:1000]
            message = f"X rejected the post ({response.status_code}): {detail}"
            if response.status_code in (401, 403):
                account.write(
                    {
                        "connection_state": "error",
                        "last_error": message,
                    }
                )
            raise UserError(message)

        payload = response.json().get("data") or {}
        post_id = payload.get("id")
        if not post_id:
            raise UserError("X created the post but did not return a post id.")
        username = (account.handle or "").lstrip("@")
        external_url = (
            f"https://x.com/{username}/status/{post_id}"
            if username
            else f"https://x.com/i/web/status/{post_id}"
        )
        return ProviderPublishResult(
            external_post_id=post_id,
            external_url=external_url,
            published_at=datetime.now(timezone.utc),
        )
