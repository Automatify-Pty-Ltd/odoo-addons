# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately to **admin@automatify.com.au**.

Do not open a public GitHub issue for vulnerabilities that could expose credentials, OAuth tokens, private keys, authorization bypasses, customer data, or sensitive deployment details.

Include the affected addon/version, reproduction steps, impact, and any suggested mitigation if available. Please avoid including real production credentials or personal data in the report.

## Repository hygiene

Public addon source must not contain:

- access tokens, API keys, OAuth client secrets, passwords, or private keys;
- internal production/demo hostnames or deployment instructions;
- real provider account/page identifiers used by Automatify;
- customer data or environment-specific configuration.

Examples and tests should use clearly synthetic identifiers and mocked external API calls.
