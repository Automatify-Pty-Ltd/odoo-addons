# Social Publisher X

X connector for `automatify_social` on Odoo 19 Community.

## Stage 1 scope

- Text post publishing through `POST https://api.x.com/2/tweets`.
- OAuth 2.0 Authorization Code flow with PKCE (`S256`).
- Requests `tweet.read tweet.write users.read offline.access`.
- Resolves the connected account through `GET /2/users/me`.
- Stores refresh tokens and refreshes access tokens automatically before scheduled publishing.
- Uses the core scheduling, retry and per-channel target workflow.

## Setup

1. Create or select an X Developer App owned by the installing organization.
2. Enable OAuth 2.0 and ensure the app/account has API access for the requested operations.
3. Open **Social Marketing → Configuration → X Settings** in Odoo.
4. Enter the X Developer App Client ID and, for confidential apps, Client Secret.
5. Add the displayed callback URL to the X Developer App exactly.
6. Create an X Social Account and click **Connect X**.
7. Approve the requested permissions.

Each installation is responsible for its own X Developer App, API access, billing or usage credits, provider terms compliance, and usage limits. Provider availability and pricing can change over time.

## External service

This connector communicates directly with X's official OAuth and API endpoints.
X credentials are not bundled with the addon.

## Security

- PKCE verifier and CSRF state are one-time values tied to the initiating Odoo user/account and expire after 10 minutes.
- No credentials or tokens are committed to Git.
- Client credentials are stored in Odoo system parameters.
- Access/refresh tokens are stored in the trusted self-hosted Odoo database and are not displayed in the Social Account form.
- Tests do not call live X APIs.

Secret-at-rest encryption/key management is a deployment responsibility before
using sensitive production accounts.
