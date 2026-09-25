# App Store submission from the CLI

`app-store-submit` submits any app project without opening Xcode or App Store
Connect. It tests, increments the build number, archives with automatic signing,
uploads the IPA, metadata, screenshots, and previews, then submits the selected
build for review.

For a new project:

```sh
/Users/asgarov1/Projects/swift/scripts/app-store-submit /path/to/app --init
cp /path/to/app/.app-store-submit.env.example /path/to/app/.app-store-submit.env
# Fill in .app-store-submit.env and /path/to/app/store-metadata/en-US.
/Users/asgarov1/Projects/swift/scripts/app-store-submit /path/to/app --create-app
```

The first command creates the Apple Developer identifier and App Store Connect
record. It needs an Apple ID and `FASTLANE_SESSION`; normal submissions use the
App Store Connect API key configured in the app's ignored `.app-store-submit.env`.

Use `--release` for automatic release after approval, `--no-tests` only when the
same commit has already passed tests, and `--dry-run` to validate inputs without
contacting Apple. Apple agreements, tax/banking setup, review approval, and the
truth of legal declarations remain account-holder responsibilities.
