# First App Store deployment

`deploy-app` is a first-release wrapper around a project submission script. It
collects the required values that cannot safely be guessed, writes the Fastlane
Deliver metadata files, creates the existing `app-store-submit` configuration,
then calls the supplied submission script with `--create-app`.

```sh
SCRIPT=/Users/asgarov1/Projects/swift/scripts/app-store-submit
DEPLOY=/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app

$DEPLOY "$SCRIPT" /path/to/app --init
cp /path/to/app/.deploy-app.env.example /path/to/app/.deploy-app.env
# Complete .deploy-app.env.
$DEPLOY "$SCRIPT" /path/to/app --dry-run
$DEPLOY "$SCRIPT" /path/to/app
```

The delegated script must support the interface
`<script> <app-project-path> --create-app`. The bundled `app-store-submit`
script does. `--release` and `--no-tests` are forwarded to it.

## Resuming safely

`--init` is safe to repeat and preserves existing configuration. A successful
release writes a local `.deploy-app-state` file containing only the app/version
identifier and a configuration fingerprint. A rerun for the same
`RELEASE_VERSION` and unchanged `.deploy-app.env` skips the delegated upload.
If a run fails partway through, no completion state is written; rerun the same
command and the bundled submission script will continue if it finds an already
created App Store record. Change `RELEASE_VERSION` for a new App Store version.
Use `--force` only when you intentionally want to rerun a completed release.

The wrapper validates and writes the fields Fastlane can upload: name, subtitle,
description, keywords, promotional text, release notes, support URL, privacy
URL, copyright, review contact, category, and build identifiers. It also
requires explicit content-rights, IDFA, and encryption declarations. Apple may
still request account-holder actions such as agreements, banking/tax setup,
pricing availability, age rating answers, or a review response; those are
account-specific and cannot be truthfully automated from a repository.
