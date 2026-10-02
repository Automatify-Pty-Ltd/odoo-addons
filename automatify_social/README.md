# Social Publisher

Open-source social publishing core for Odoo 19 Community.

## Current Stage 1 scope

The addon provides native Odoo models and workflow for social accounts, posts,
per-account publication targets, scheduling, retries, company isolation, and
provider extension hooks. It intentionally contains no production credentials
and performs no provider-specific HTTP calls by itself.

Connector addons extend the Social Account model through normal Odoo inheritance.
Each installed connector adds its platform choice and returns its provider service
for accounts of that platform. Because the hooks live in the current Odoo database
registry, one database cannot accidentally expose a connector installed only in
another database served by the same Odoo process.

## Workflow

`Draft -> Scheduled -> Processing -> Published/Failed`

Posts can also be cancelled and failed targets can be retried. A five-minute
cron publishes due scheduled posts in bounded batches.

## Provider contract

A provider implements `publish(account, post)` and returns a
`ProviderPublishResult`. Connector addons extend `_social_platform_selection()`
and `_get_social_provider()` on `automatify.social.account` through standard Odoo
model inheritance. Adding a new network therefore does not require changing the
core addon.

The core does not define LinkedIn, X, Meta, or any other provider.

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
