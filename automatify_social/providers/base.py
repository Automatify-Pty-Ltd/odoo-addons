from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ProviderPublishResult:
    external_post_id: Optional[str] = None
    external_url: Optional[str] = None
    published_at: Optional[datetime] = None


class SocialProvider:
    """Base contract implemented by connector addons."""

    key = None
    label = None

    def publish(self, account, post):
        raise NotImplementedError
