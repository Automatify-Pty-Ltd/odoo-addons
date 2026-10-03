# Social Publisher

Open-source social publishing core for Odoo 19 Community.

## Current Stage 1.1 scope

The addon provides native Odoo models and workflow for social accounts, posts,
per-account publication targets, scheduling, retries, company isolation, and
provider extension hooks. Stage 1.1 adds a richer publishing experience while
keeping baseline authoring and publishing open source.

Current core UX includes:

- Odoo rich-text post authoring.
- Provider-safe plaintext rendering for external APIs.
- One image attachment directly from the Social Post form.
- Post now and future scheduling with distinct `Scheduled At` / `Published At`
  semantics.
- Per-channel external post ID, network URL, status and error details.
- Retry handling and multi-company isolation.

The core intentionally contains no production credentials and performs no
provider-specific HTTP calls by itself.

Connector addons extend the Social Account model through normal Odoo inheritance.
Each installed connector adds its platform choice and returns its provider service
for accounts of that platform. Because the hooks live in the current Odoo database
registry, one database cannot accidentally expose a connector installed only in
another database served by the same Odoo process.

## Workflow

`Draft -> Scheduled -> Processing -> Published/Failed`

Posts can also be cancelled and failed targets can be retried. A five-minute
cron publishes due scheduled posts in bounded batches. `Post Now` from Draft
clears an incidental scheduled timestamp so `Scheduled At` only means a real
scheduled publication time.

## Authoring model

`message` is stored as sanitized HTML so Odoo can provide its native rich editor.
`message_text` is the provider-safe plaintext representation used by connector
APIs. This lets authors work with paragraphs, emphasis and links without sending
raw HTML to LinkedIn, X or future providers.

Stage 1.1 deliberately starts with one image per post. Multi-image/video support
can expand later without changing the provider contract.

## Provider contract

A provider implements `publish(account, post)` and returns a
`ProviderPublishResult`, including the provider post ID and an external URL when
available. Connector addons extend `_social_platform_selection()` and
`_get_social_provider()` on `automatify.social.account` through standard Odoo
model inheritance. Adding a new network therefore does not require changing the
core addon.

The core does not define LinkedIn, X, Meta, or any other provider.

## Open-source boundary

Baseline authoring and publishing remain free/open source: rich authoring, image
attachment UI, scheduling, retry/error handling, external post links, basic
provider validation, and baseline provider connectors.

Advanced team workflow and intelligence are better candidates for optional paid
addons: approvals/governance, advanced analytics, CRM attribution, AI drafting
and variants, brand governance, advanced asset libraries, bulk/campaign
scheduling, and similar scale features.

## External services

The core itself makes no external network requests. Connector addons may call
their provider's official API and require credentials created by the installing
organization in that provider's developer portal.

## Security and reliability

- No provider secrets are stored by the core.
- No external network requests are made by the core.
- Record rules restrict data to the user's allowed companies.
- Provider credentials and OAuth behavior stay isolated in connector addons.
- Publication is serialized per post to reduce duplicate writes from concurrent
  manual and scheduled publication attempts.
- A post that already succeeded on at least one channel cannot be reset in a way
  that would silently republish successful channels; failed channels use Retry Failed.

The release source is published from the public `Automatify-Pty-Ltd/odoo-addons`
repository. Internal deployment automation is intentionally not part of this addon.
