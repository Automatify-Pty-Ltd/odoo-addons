# Social Publisher LinkedIn

LinkedIn connector for `automatify_social` on Odoo 19 Community.

## Current Stage 1.1 scope

- Publishes provider-safe social text through `POST https://api.linkedin.com/rest/posts`.
- Publishes one JPG, PNG, or GIF image per post through LinkedIn's versioned Images API and attaches the returned image URN to the Posts API payload.
- Supports personal-profile and Company Page authors.
- Uses LinkedIn 3-legged OAuth Authorization Code flow.
- Uses one-time OAuth `state` records tied to the initiating Odoo user/account and expiring after 10 minutes.
- Personal profiles request `r_basicprofile w_member_social` and resolve the member id through `/v2/me`.
- Company Pages request `rw_organization_admin w_organization_social` and validate eligible pages through `/rest/organizationAcls`.
- Sends `Linkedin-Version` and `X-Restli-Protocol-Version: 2.0.0` for versioned Marketing APIs.
- Captures LinkedIn's `x-restli-id` as the external post id and stores a convenient LinkedIn feed URL in the publication target.
- Uses the core scheduling/retry workflow.

The Odoo editor stores sanitized rich HTML, while this connector publishes the
core's provider-safe text rendering instead of sending raw HTML to LinkedIn.

## Setup

1. Create or select a LinkedIn Developer App owned by the installing organization.
2. Ensure the app has the LinkedIn products/permissions required for the requested scopes.
3. Open **Social Marketing → Configuration → LinkedIn Settings** in Odoo.
4. Enter the app Client ID and Client Secret.
5. Add the displayed Odoo OAuth Redirect URL to the app's **Auth** tab as an exact Redirect URL.
6. Create a LinkedIn Social Account and choose Personal Profile or Company Page.
7. For a Company Page, the connector auto-selects it when exactly one eligible page is returned. If the member can publish for multiple pages, enter the desired `urn:li:organization:...` in LinkedIn Author URN before reconnecting.
8. Click **Connect LinkedIn** and approve the requested permissions.

Each installation is responsible for its own LinkedIn Developer App, API access,
permissions, terms compliance, and provider-side usage limits. Provider access and
permission names can change over time.

## External service

This connector communicates directly with LinkedIn's official OAuth, Images and
Posts API endpoints. LinkedIn credentials are not bundled with the addon. Post
text and selected image bytes are sent directly from the Odoo installation to
LinkedIn only when the user publishes or when a scheduled post becomes due.

## Security

- No OAuth client credentials or tokens are committed to Git.
- Client credentials are stored in Odoo system parameters.
- Access/refresh tokens remain in the trusted self-hosted Odoo database and are not shown in the Social Account form.
- OAuth callback requires an authenticated Odoo user and verifies the one-time `state` belongs to that same user.
- Tests mock provider HTTP and do not call live LinkedIn APIs.

Secret-at-rest encryption/key-management is a deployment responsibility before
using sensitive production accounts.
