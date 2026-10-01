# External App Connect

`external_app_connect` adds a small, reusable authorization layer for connecting external applications to Odoo 19 without asking users to copy passwords or long-lived Odoo API keys into those applications.

It is intentionally an **OAuth-style connection protocol**, not a claim of full OAuth 2.0 / OpenID Connect conformance. The module implements the security properties needed for an app-connect flow: authorization code, mandatory PKCE S256, exact redirect URI matching, `state`, one-time short-lived codes, hashed bearer tokens, explicit scopes, revocation, and a consent screen.

## Why a separate connector token?

Odoo 19 JSON-2 API keys authenticate with the permissions of their Odoo user. Giving an arbitrary external application a generic `rpc` API key can expose much more than that application needs.

External App Connect therefore issues its own scoped bearer token. The raw token is shown only once and stored only by the external application's trusted backend. Odoo stores only a SHA-256 hash. App-specific addons define narrow scopes and HTTP endpoints that accept these tokens.

This makes the base module useful for Inventify and for unrelated integrations without turning it into a generic remote CRUD gateway.

## Flow

1. An Odoo administrator registers an application under **App Connect → Applications**, including exact redirect URI(s) and allowed scopes.
2. The external application's backend generates `state`, a PKCE verifier, and the S256 challenge.
3. The app opens:

   `/external-app/connect/authorize?response_type=code&client_id=...&redirect_uri=...&scope=...&state=...&code_challenge=...&code_challenge_method=S256`

4. Odoo requires a normal user login and shows a consent screen listing the requested permissions.
5. On **Allow**, Odoo redirects to the registered URI with a five-minute, one-time authorization `code` and the original `state`.
6. The trusted backend exchanges `code + code_verifier` at `POST /external-app/connect/token`.
7. Odoo returns a scoped bearer token. The token lifetime is configurable per client and capped at 90 days.
8. App-specific endpoints authenticate the bearer token and enforce required scopes.
9. `POST /external-app/connect/revoke` invalidates a token immediately.

Metadata is available at `/.well-known/odoo-app-connect`.

## Built-in proof endpoint

The module provides the scope `profile:read` and a minimal endpoint:

`GET /external-app/connect/api/v1/me`

With a valid connector bearer token carrying `profile:read`, it returns only the connected user's display name, current company, client ID, and granted scope. It does not expose email, password, API keys, arbitrary models, or generic ORM operations.

## Extending from another addon

A feature addon should create one or more `external.app.scope` records and expose only the business operations it needs. In a controller, authenticate like this:

```python
token = request.env["external.app.access.token"].authenticate_bearer(
    request.httprequest.headers.get("Authorization"),
    required_scopes={"inventory:write"},
)

# Run narrow operations as the connected Odoo user so normal ACLs and record
# rules still apply.
locations = request.env["stock.location"].with_user(token.user_id).search([...])
```

Do not add a generic `model/method/domain` proxy. Scopes should map to a small, reviewable set of application capabilities.

## Security properties

- redirect URIs are exact-match allow-listed; fragments are rejected;
- non-local web callbacks must use HTTPS; custom mobile schemes are supported;
- `state` is mandatory;
- PKCE S256 is mandatory;
- authorization codes expire after five minutes and are one-time;
- authorization codes and access tokens are stored only as hashes;
- access tokens expire after at most 90 days and can be revoked;
- clients may request only administrator-approved scopes;
- no Odoo password or Odoo JSON-2 API key is sent to the external application;
- external apps get no arbitrary ORM/RPC access from this base addon.

Production deployments should additionally use HTTPS, normal Odoo hardening, reverse-proxy rate limits, and an appropriate retention policy for expired connection records.

## License

AGPL-3.0, matching the open-source addon repository.
