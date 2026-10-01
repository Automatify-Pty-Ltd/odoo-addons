# Inventify Inventory Connect

`inventify_inventory_connect` is the Inventify-specific extension for the reusable [`external_app_connect`](../external_app_connect/) authorization module.

The goal is a one-click product flow rather than asking a customer to copy an Odoo password or generic JSON-2 API key into the mobile app.

## User flow

1. In Inventify, choose **Settings → Integrations → Odoo → Connect Odoo**.
2. Enter the customer's Odoo base URL.
3. Inventify's trusted backend discovers `/.well-known/odoo-app-connect`, creates `state` plus a PKCE verifier/challenge, and opens Odoo's authorization URL in the browser.
4. Odoo performs its normal login and shows a consent page for the Inventify Inventory permissions.
5. On **Allow**, Odoo returns a five-minute one-time authorization code to Inventify's registered callback.
6. Inventify's trusted backend exchanges that code plus the PKCE verifier for a scoped connector token and stores the token server-side. The mobile app never receives the connector token.
7. Inventify reads the warehouses/root locations visible to the connected Odoo user, the user selects the target root, and that selection is stored per Odoo connection.
8. Subsequent Inventory synchronization uses only the narrow Inventify endpoints granted by the connection.

## Registered Inventify client

Installing this addon registers the public client ID:

`inventify.mobile.v1`

Allowed callbacks are currently:

- `https://xrikoshdvntnuypticgc.supabase.co/functions/v1/odoo-connect-callback`
- `inventify://odoo-connected`

The connector token is valid for 30 days and can be revoked from Odoo. Token renewal/rotation will use the same explicit connection model rather than putting credentials in the phone.

## Scopes

- `profile:read` — basic connected-user/company identity from the base connector.
- `inventify:inventory:read` — list the connected company, warehouses, and eligible Inventory roots.
- `inventify:inventory:write` — configure the Inventify root and, as Inventory sync endpoints are added, authorize only Inventify-managed Inventory writes.

The addon intentionally does **not** grant generic model/method RPC access.

## Setup API

With a connector bearer token:

- `GET /inventify-connect/api/v1/connection` — connection/company status and selected root.
- `GET /inventify-connect/api/v1/locations` — warehouses and eligible internal/view locations.
- `POST /inventify-connect/api/v1/settings` with `{"root_location_id": 123}` — store the selected root for this connection.

All Inventory reads run as the connected Odoo user, so Odoo ACLs and record rules still apply. A user without Inventory access receives a permission error.

## Licensing

AGPL-3.0. The Odoo-side trust bridge is intentionally open source. Inventify's paid Team plan remains the commercial product; future managed features such as hosted connector administration, enterprise policies, audit dashboards, webhook delivery, and managed token rotation can be commercial without hiding the credential-handling module from customers.
