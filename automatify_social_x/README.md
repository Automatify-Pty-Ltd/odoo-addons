# Social Publisher X

X connector for `automatify_social` on Odoo 19 Community.

## Stage 1.1 scope

- Provider-safe text post publishing through `POST https://api.x.com/2/tweets`.
- One JPG, PNG, or WebP image per post through the current X API v2 chunked media flow: initialize, append 4 MiB chunks, finalize, then attach the returned media id to the Post.
- OAuth 2.0 Authorization Code flow with PKCE (`S256`).
- Requests `tweet.read tweet.write users.read media.write offline.access`.
- Resolves the connected account through `GET /2/users/me`.
- Stores refresh tokens and refreshes access tokens automatically before scheduled publishing.
- Uses the core scheduling, retry and per-channel target workflow.
- Stores the created X post URL on the publication target.

The Odoo editor stores sanitized rich HTML, while this connector publishes the
core's provider-safe text rendering instead of sending raw HTML to X.

## Setup

1. Create or select an X Developer App owned by the installing organization.
2. Enable OAuth 2.0 and ensure the app/account has API access for the requested operations, including media upload.
3. Open **Social Marketing → Configuration → X Settings** in Odoo.
4. Enter the X Developer App Client ID and, for confidential apps, Client Secret.
5. Add the displayed callback URL to the X Developer App exactly.
6. Create an X Social Account and click **Connect X**.
7. Approve the requested permissions.

Existing X connections created before Stage 1.1 must reconnect once so the new
`media.write` scope is present in the access/refresh token grant.

Each installation is responsible for its own X Developer App, API access, billing
or usage credits, provider terms compliance, and usage limits. Provider
availability and pricing can change over time.

## External service

This connector communicates directly with X's official OAuth, media-upload and
Posts API endpoints. X credentials are not bundled with the addon. Post text and
selected image bytes are sent directly from the Odoo installation to X only when
the user publishes or when a scheduled post becomes due.

## Security

- PKCE verifier and CSRF state are one-time values tied to the initiating Odoo user/account and expire after 10 minutes.
- No credentials or tokens are committed to Git.
- Client credentials are stored in Odoo system parameters.
- Access/refresh tokens are stored in the trusted self-hosted Odoo database and are not displayed in the Social Account form.
- Tests mock provider HTTP and do not call live X APIs.

Secret-at-rest encryption/key management is a deployment responsibility before
using sensitive production accounts.
