# First App Store deployment

`deploy-app` is a first-release wrapper around a project submission script. It
collects the required values that cannot safely be guessed, writes the Fastlane
Deliver metadata files, creates the bundled `app-store-submit` configuration,
then calls that bundled submission helper with `--create-app`.

## Terminal usage

Run these commands in Terminal, replacing `/path/to/app` with the absolute path
to the Xcode app project you want to submit.

### First-time setup

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /path/to/app
```

When `.deploy-app.env` is missing, the command derives the bundle identifier,
Xcode project, scheme, version, and (when available) language-app details, then
shows the full resolved configuration. Choose `C` to save and continue with
those values, or `E` to edit them one by one. `--configure` always opens the
detailed editing flow for an existing configuration. The resulting
`.deploy-app.env` is written with owner-only permissions and is never
overwritten on later runs. If you remove a required attribute from an existing
file, the next interactive run asks only for the missing value and writes the
completed configuration back to the file.

To create only the documented example file without starting interactive setup:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /path/to/app --init
```

If running without an interactive terminal, copy the example file to
`.deploy-app.env` and complete it manually.

### Validate without contacting Apple

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
/path/to/app --dry-run
```

This performs the same local configuration, metadata, screenshot, and App
Preview validation as a submission, but does not build, publish the privacy
policy, or contact Apple.

### Run App Store checks, or explicitly submit a build

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /path/to/app
```

The default run stops after Fastlane precheck. It does not upload a build,
attach a build to a version, or submit the app for review. The Fastlane check
always skips tests, so run and verify the relevant test suite before starting a
submission.

To upload and submit, pass `--submit`; add `--release` only when that explicit
submission should release automatically after approval:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/app-store-submit \
  /path/to/app --submit --no-tests
```

To set the app itself (not IAPs) to Apple's globally free 0.00 price, use:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/app-store-submit \
  /path/to/app --set-free-price --no-tests
```

The bundled `app-store-submit` script is kept alongside `deploy-app`; the
wrapper always forwards `--no-tests`.

### Authentication and signing

Deployments use only the configured App Store Connect API key. They never use
`APPLE_ID`, `FASTLANE_SESSION`, or Fastlane's `produce` action, so remove any
legacy session from local deployment files when convenient. The helper also
does not pass `-allowProvisioningUpdates` to Xcode. Configure the app's bundle
identifier, certificate, and provisioning profile before deployment; this
avoids an implicit Developer Portal sign-in during an upload.

For a brand-new app, the API key must have permission to create apps in App
Store Connect and the bundle identifier must already be registered for signing.
The helper makes one API lookup and at most one create request; it does not
retry Apple ID authentication or poll app creation.

### Team selection

The App Store Connect API key determines the App Store Connect team, so the
helper does not select a team interactively. Use an API key created in the
membership that owns the app.

## Resuming safely

`--init` is safe to repeat and preserves existing configuration. A successful
release writes a local `.deploy-app-state` file containing only the app/version
identifier and a configuration fingerprint. A rerun for the same
`RELEASE_VERSION` and unchanged `.deploy-app.env` skips the delegated upload.
If a run fails partway through, no completion state is written; rerun the same
command and the bundled submission script will continue if it finds an already
created App Store record. Change `RELEASE_VERSION` for a new App Store version.
Use `--force` only when you intentionally want to rerun a completed release.
The selected `BUILD_NUMBER` is held constant for a release, so a retry does not
silently create another build; change both `RELEASE_VERSION` and `BUILD_NUMBER`
for the next App Store version.

### Reset local deployment setup

To discard the local deployment configuration and generated App Store metadata
for one project, run:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/reset.sh \
  /path/to/app
```

The command lists its targets and asks for confirmation. It removes only
`.deploy-app.env`, `.deploy-app.env.example`, `.app-store-submit.env`,
`.deploy-app-state`, and `store-metadata/`; it does not remove screenshots,
previews, the project itself, published privacy policies, or an App Store
Connect record. Add `--yes` only for a non-interactive invocation.

### Resume or intentionally rerun

```sh
# Safely resumes a partial deployment, or skips a completed unchanged release.
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /path/to/app

# Deliberately reruns a release that has already been recorded as complete.
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /path/to/app --force
```

The wrapper validates and writes the fields Fastlane can upload: name, subtitle,
description, keywords, promotional text, release notes, support URL, privacy
URL, copyright, review contact, category, and build identifiers. It submits the
configured content-rights, IDFA, encryption, and age-rating declarations. New
Jlingo configurations default to a current copyright year, free pricing (tier
`0`), sale in every territory, and an offline learning app's no-content/no-feature
age-rating answers; change these values if they are not truthful for the app.

### App privacy data-use declaration

App Store Connect requires published data-use answers before it will accept a
version for review. Complete and publish the truthful answers directly in App
Store Connect before deployment. The submission helper does not read, validate,
or publish privacy answers because Apple doesn't expose that capability through
the App Store Connect API.

Current Fastlane cannot reliably update App Store pricing or global territory
availability with an API key: Apple has retired the API relationships that
Fastlane uses for its `price_tier` option. Before the first submission, set the
saved `PRICE_TIER` and `AVAILABLE_IN_ALL_TERRITORIES` values once in App Store
Connect at **Monetization → Pricing and Availability**: select a price of
`0.00`, enable all countries or regions, and enable availability in new
territories. The submission lane intentionally leaves those settings untouched,
so it can be retried without changing sale availability. Apple may still request
account-holder actions such as agreements, banking/tax setup, or a review
response.

## Privacy policy publication

Before it contacts App Store Connect, `deploy-app` copies
`PRIVACY_POLICY_SOURCE` into the checkout named by `PRIVACY_POLICIES_REPO` at
`PRIVACY_POLICY_PUBLISHED_PATH`, commits only that file, pushes it to `origin`,
and checks that `PRIVACY_URL` can be reached. For the shared policy repository,
the URL must exactly be:

```text
https://asgarov1.github.io/Privacy-Policies/<PRIVACY_POLICY_PUBLISHED_PATH-without-.md>
```

For example, an app with
`PRIVACY_POLICY_PUBLISHED_PATH=spanish_a1_privacy_policy.md` must use
`PRIVACY_URL=https://asgarov1.github.io/Privacy-Policies/spanish_a1_privacy_policy`.
The policy source must already contain truthful, app-specific data-practice
statements; the script deliberately does not invent legal claims. A dry run
validates the configuration but does not publish the policy or contact Apple.

## Language-app descriptions and keywords

For Jlingo language apps, set `LANGUAGE_NAME` and `LANGUAGE_LEVEL` in
`.deploy-app.env` for the app being submitted, for example `Spanish` and `A1`.
Leaving `DESCRIPTION` and `KEYWORDS` empty then creates a tailored default
description and keyword list for that language and level. Keywords include the
language, level, learning-module terms, and `jlpt` or `topik` only when those
exam labels match Japanese or Korean respectively. The description
describes the app's offline learning modules, samples, purchase options, and
Certificate of Completion without making a language-specific exam claim. Set
either field when you need custom App Store copy; non-language apps must set
both fields explicitly. The wrapper enforces Apple's current length limits:
4,000 characters for descriptions and 100 characters for keywords.

## Screenshots and App Previews

Place screenshots in `screenshots/iphone` and `screenshots/ipad`. The script
accepts only Apple’s highest required screenshot families: iPhone 6.9-inch
(`1260x2736`, `1290x2796`, or `1320x2868`) and iPad 13-inch (`2064x2752` or
`2048x2732`), in either orientation. It rejects transparency and more than ten
images per device family. Apple automatically scales these to smaller device
sizes when the interface is the same.

On retries, `SKIP_SCREENSHOTS_IF_UNCHANGED=1` (the default) compares MD5
checksums of the staged screenshots with completed App Store Connect screenshots.
If every exact image is already there, Fastlane skips the screenshot workflow;
changed or incomplete media is uploaded normally. Set it to `0` to force the
normal Fastlane screenshot check.

App Previews are optional. Put up to three videos per device family in
`previews`, naming iPhone videos with `IPHONE_67` and iPad videos with
`IPAD_PRO_3GEN_129`; for example, `onboarding_IPHONE_67.mp4` and
`onboarding_IPAD_PRO_3GEN_129.mp4`. The script validates Apple’s high-family
preview exports (886×1920 for iPhone and 1200×1600 for iPad, either
orientation), duration, frame rate, codec, extension, and 500 MB size limit,
then passes the localized previews to Fastlane’s `app_previews_path` upload.
