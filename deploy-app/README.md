# First App Store deployment

`deploy-app` is a first-release wrapper around a project submission script. It
collects the required values that cannot safely be guessed, writes the Fastlane
Deliver metadata files, creates the existing `app-store-submit` configuration,
then calls the supplied submission script with `--create-app`.

## Terminal usage

Run these commands in Terminal, replacing `/path/to/app` with the absolute path
to the Xcode app project you want to submit.

### First-time setup

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /Users/asgarov1/Projects/swift/scripts/app-store-submit \
  /path/to/app --init

cp /path/to/app/.deploy-app.env.example /path/to/app/.deploy-app.env
# Edit /path/to/app/.deploy-app.env and fill in every required value.
```

### Validate without contacting Apple

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /Users/asgarov1/Projects/swift/scripts/app-store-submit \
  /path/to/app --dry-run
```

### Create the App Store Connect record and submit the first build

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /Users/asgarov1/Projects/swift/scripts/app-store-submit \
  /path/to/app
```

Add `--release` to automatically release after Apple approves it. Add
`--no-tests` only if the same commit has already passed its tests.

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

### Resume or intentionally rerun

```sh
# Safely resumes a partial deployment, or skips a completed unchanged release.
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /Users/asgarov1/Projects/swift/scripts/app-store-submit \
  /path/to/app

# Deliberately reruns a release that has already been recorded as complete.
/Users/asgarov1/Projects/swift/scripts/deploy-app/deploy-app \
  /Users/asgarov1/Projects/swift/scripts/app-store-submit \
  /path/to/app --force
```

The wrapper validates and writes the fields Fastlane can upload: name, subtitle,
description, keywords, promotional text, release notes, support URL, privacy
URL, copyright, review contact, category, and build identifiers. It also
requires explicit content-rights, IDFA, and encryption declarations. Apple may
still request account-holder actions such as agreements, banking/tax setup,
pricing availability, age rating answers, or a review response; those are
account-specific and cannot be truthfully automated from a repository.

## Screenshots and App Previews

Place screenshots in `screenshots/iphone` and `screenshots/ipad`. The script
accepts only Apple’s highest required screenshot families: iPhone 6.9-inch
(`1260x2736`, `1290x2796`, or `1320x2868`) and iPad 13-inch (`2064x2752` or
`2048x2732`), in either orientation. It rejects transparency and more than ten
images per device family. Apple automatically scales these to smaller device
sizes when the interface is the same.

App Previews are optional. Put up to three videos per device family in
`previews`, naming iPhone videos with `IPHONE_67` and iPad videos with
`IPAD_PRO_3GEN_129`; for example, `onboarding_IPHONE_67.mp4` and
`onboarding_IPAD_PRO_3GEN_129.mp4`. The script validates Apple’s high-family
preview exports (886×1920 for iPhone and 1200×1600 for iPad, either
orientation), duration, frame rate, codec, extension, and 500 MB size limit,
then passes the localized previews to Fastlane’s `app_previews_path` upload.
