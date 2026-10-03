from datetime import datetime, timezone

import requests

from odoo.exceptions import UserError

from odoo.addons.automatify_social.providers.base import ProviderPublishResult, SocialProvider


class XProvider(SocialProvider):
    key = "x"
    label = "X"
    endpoint = "https://api.x.com/2/tweets"
    media_endpoint = "https://api.x.com/2/media/upload"
    media_chunk_size = 4 * 1024 * 1024
    timeout = 20

    @staticmethod
    def _response_detail(response):
        return (response.text or "")[:1000]

    @staticmethod
    def _auth_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def _upload_image(self, account, attachment, token):
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if attachment.mimetype not in allowed_types:
            raise UserError("X image publishing supports JPG, PNG, and WebP files.")
        raw = attachment.raw
        if not raw:
            raise UserError("The selected X image attachment is empty.")

        try:
            initialize = requests.post(
                f"{self.media_endpoint}/initialize",
                headers={
                    **self._auth_headers(token),
                    "Content-Type": "application/json",
                },
                json={
                    "total_bytes": len(raw),
                    "media_type": attachment.mimetype,
                    "media_category": "tweet_image",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"X media initialization failed: {exc}") from exc

        if not 200 <= initialize.status_code < 300:
            message = (
                f"X rejected media initialization ({initialize.status_code}): "
                f"{self._response_detail(initialize)}"
            )
            if initialize.status_code in (401, 403):
                account.write({"connection_state": "error", "last_error": message})
            raise UserError(message)

        media_id = ((initialize.json() or {}).get("data") or {}).get("id")
        if not media_id:
            raise UserError("X media initialization did not return a media id.")

        for segment_index, offset in enumerate(range(0, len(raw), self.media_chunk_size)):
            chunk = raw[offset : offset + self.media_chunk_size]
            try:
                appended = requests.post(
                    f"{self.media_endpoint}/{media_id}/append",
                    headers=self._auth_headers(token),
                    data={"segment_index": str(segment_index)},
                    files={
                        "media": (
                            attachment.name or "social-image",
                            chunk,
                            attachment.mimetype,
                        )
                    },
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise UserError(f"X media upload failed: {exc}") from exc

            if not 200 <= appended.status_code < 300:
                raise UserError(
                    f"X rejected media upload ({appended.status_code}): "
                    f"{self._response_detail(appended)}"
                )

        try:
            finalized = requests.post(
                f"{self.media_endpoint}/{media_id}/finalize",
                headers=self._auth_headers(token),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"X media finalize failed: {exc}") from exc

        if not 200 <= finalized.status_code < 300:
            raise UserError(
                f"X rejected media finalize ({finalized.status_code}): "
                f"{self._response_detail(finalized)}"
            )
        return media_id

    def publish(self, account, post):
        token = account._x_get_access_token()
        payload = {"text": post.message_text}

        if post.image_ids:
            image = post.image_ids.ensure_one()
            media_id = self._upload_image(account, image, token)
            payload["media"] = {"media_ids": [media_id]}

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"X request failed: {exc}") from exc

        if response.status_code != 201:
            detail = self._response_detail(response)
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
