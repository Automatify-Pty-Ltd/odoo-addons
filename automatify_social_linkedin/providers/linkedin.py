from datetime import timedelta

import requests

from odoo import fields
from odoo.exceptions import UserError

from odoo.addons.automatify_social.providers.base import ProviderPublishResult, SocialProvider


class LinkedInProvider(SocialProvider):
    key = "linkedin"
    label = "LinkedIn"
    endpoint = "https://api.linkedin.com/rest/posts"
    timeout = 20

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
            "commentary": post.message,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": version,
        }
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(f"LinkedIn request failed: {exc}") from exc

        if response.status_code != 201:
            detail = (response.text or "")[:1000]
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
        return ProviderPublishResult(
            external_post_id=post_urn,
            published_at=fields.Datetime.now(),
        )
