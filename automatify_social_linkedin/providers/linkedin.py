from datetime import timedelta

import requests

from odoo import fields
from odoo.exceptions import UserError

from odoo.addons.automatify_social.providers.base import (
    AmbiguousPublishError,
    ProviderPublishResult,
    SocialProvider,
)


class LinkedInProvider(SocialProvider):
    key = "linkedin"
    label = "LinkedIn"
    endpoint = "https://api.linkedin.com/rest/posts"
    image_initialize_endpoint = "https://api.linkedin.com/rest/images?action=initializeUpload"
    timeout = 20

    @staticmethod
    def _headers(token, version, content_type="application/json"):
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": version,
        }

    @staticmethod
    def _response_detail(response):
        return (response.text or "")[:1000]

    def _upload_image(self, account, attachment, token, author, version):
        allowed_types = {"image/jpeg", "image/png", "image/gif"}
        if attachment.mimetype not in allowed_types:
            raise UserError(
                "LinkedIn image publishing supports JPG, PNG, and GIF files."
            )
        if not attachment.raw:
            raise UserError("The selected LinkedIn image attachment is empty.")

        headers = self._headers(token, version)
        try:
            initialize = requests.post(
                self.image_initialize_endpoint,
                headers=headers,
                json={"initializeUploadRequest": {"owner": author}},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"LinkedIn image initialization failed: {exc}") from exc

        if initialize.status_code != 200:
            message = (
                f"LinkedIn rejected image initialization ({initialize.status_code}): "
                f"{self._response_detail(initialize)}"
            )
            if initialize.status_code in (401, 403):
                account.write({"connection_state": "error", "last_error": message})
            raise UserError(message)

        value = (initialize.json() or {}).get("value") or {}
        upload_url = value.get("uploadUrl")
        image_urn = value.get("image")
        if not upload_url or not image_urn:
            raise UserError(
                "LinkedIn image initialization did not return an upload URL and image URN."
            )

        try:
            uploaded = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": attachment.mimetype,
                },
                data=attachment.raw,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"LinkedIn image upload failed: {exc}") from exc

        if uploaded.status_code not in (200, 201, 202):
            raise UserError(
                f"LinkedIn rejected image upload ({uploaded.status_code}): "
                f"{self._response_detail(uploaded)}"
            )
        return image_urn

    def publish(self, account, post):
        if (
            account.linkedin_token_expires_at
            and account.linkedin_token_expires_at
            <= fields.Datetime.now() + timedelta(minutes=1)
        ):
            account.write(
                {
                    "connection_state": "error",
                    "last_error": "LinkedIn access token expired; reconnect the account.",
                }
            )
            raise UserError("LinkedIn access token expired; reconnect the account.")

        token = account.linkedin_access_token
        author = account.linkedin_author_urn or account.external_account_id
        version = account.linkedin_api_version or "202609"
        if not token:
            raise UserError("LinkedIn access token is not configured for this account.")
        if not author:
            raise UserError("LinkedIn author URN is not configured for this account.")

        payload = {
            "author": author,
            "commentary": post.message_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        if post.image_ids:
            image = post.image_ids.ensure_one()
            image_urn = self._upload_image(account, image, token, author, version)
            payload["content"] = {
                "media": {
                    "id": image_urn,
                    "altText": (image.name or "Social post image")[:120],
                }
            }

        headers = self._headers(token, version)
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AmbiguousPublishError(
                "LinkedIn publication outcome is unknown because the response was lost. "
                "Verify the post on LinkedIn before attempting any retry."
            ) from exc

        if response.status_code >= 500:
            raise AmbiguousPublishError(
                "LinkedIn publication outcome is unknown because LinkedIn returned a server "
                "error after the publish request. Verify the post on LinkedIn before attempting "
                "any retry."
            )

        if response.status_code != 201:
            detail = self._response_detail(response)
            message = f"LinkedIn rejected the post ({response.status_code}): {detail}"
            if response.status_code in (401, 403):
                account.write(
                    {
                        "connection_state": "error",
                        "last_error": message,
                    }
                )
            raise UserError(message)

        post_urn = response.headers.get("x-restli-id")
        external_url = (
            f"https://www.linkedin.com/feed/update/{post_urn}/" if post_urn else None
        )
        return ProviderPublishResult(
            external_post_id=post_urn,
            external_url=external_url,
            published_at=fields.Datetime.now(),
        )
