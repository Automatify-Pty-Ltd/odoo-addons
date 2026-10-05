# Social Publisher Release Checklist

This checklist applies to public releases of:

- `automatify_social`
- `automatify_social_linkedin`
- `automatify_social_x`

## Source boundary

- [ ] Release only from this public `odoo-addons` repository.
- [ ] Do not copy private deployment docs, infrastructure automation, environment files, or credentials into the release.
- [ ] Keep provider setup generic: each installation supplies its own developer app and credentials.
- [ ] Use synthetic provider IDs/URNs in examples and tests.

## Odoo / Marketplace metadata

- [ ] Manifest has an explicit short display name, version, author, website, support email, category, and license.
- [ ] `static/description/index.html` is English, accurate, and describes only functionality present in the release.
- [ ] External provider requirements and limitations are disclosed clearly.
- [ ] Add only real screenshots captured from a clean demo installation; do not use mock or misleading screenshots.
- [ ] Re-check current Odoo Apps vendor guidelines immediately before submission.

## Validation

- [ ] Public CI passes on the pinned Odoo 19 image.
- [ ] Core installs and its tests pass on a clean database.
- [ ] LinkedIn connector installs and its mocked tests pass on a clean database.
- [ ] X connector installs and its mocked tests pass on a clean database.
- [ ] No test performs a live provider write.
- [ ] Sanitization checks pass with no internal environment markers or secret-looking files.
- [ ] Provider API versions, OAuth scopes, endpoints, and current provider requirements have been revalidated against official documentation.

## Release safety

- [ ] No production credentials are used while preparing the Marketplace package.
- [ ] No private repository or deployment workflow is required for a customer to install the addon.
- [ ] Demo validation is complete before screenshots are captured.
- [ ] Marketplace publishing is a separate explicit action after code review and CI; preparing this repository does not publish an app.
