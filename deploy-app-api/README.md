# App Store Connect API deployer

`deploy_app_store.py` deploys an already-signed IPA using only the current App Store Connect REST API. It does not invoke Fastlane, Transporter, `altool`, Xcode, or an Apple-ID session.

```sh
cd /Users/asgarov1/Projects/swift/scripts/deploy-app-api
./deploy_app_store.py --write-example deployment.json                          # shared settings
./deploy_app_store.py --write-project-example /absolute/path/to/app-assets/deployment.json  # per-app settings
./deploy_app_store.py /absolute/path/to/app-assets
```

It merges the shared `/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deployment.json` with the app's own `<root>/deployment.json` (see Configuration). Pass `--config` / `--project-config` only when intentionally using different files. It uses an App Store Connect team API key (`keyId`, `issuerId`, and the local `.p8` file). The only local executable dependency is macOS `openssl`, used solely to create the ES256 JWT required by Apple.

## Configuration

Configuration is split in two files that are deep-merged at startup:

- **Shared** — `deploy-app-api/deployment.json` (or `--config`): everything identical across apps: API key, `app.primaryLocale`, version `platform`/`releaseType`/`usesIdfa`/`copyright`, build settings (`createIpa`, `configuration`, `exportPath`, `exportOptions`, `allowProvisioningUpdates`, `processingTimeoutSeconds`), `localizationsPath`, `media`, and the purchase catalogue (names, periods, types, prices).
- **Per project** — `<root>/deployment.json` (or `--project-config`): what differs per app: `app.bundleId`, `app.sku`, `version.versionString`, `build.ipaPath`/`bundleVersion`/`projectPath`/`scheme`/`archivePath`, and each purchase's `productId`.

```json
{
  "app": { "bundleId": "com.example.app", "sku": "example-app" },
  "version": { "versionString": "1.0" },
  "build": { "ipaPath": "build/Example.ipa", "bundleVersion": "1", "projectPath": "Example.xcodeproj", "scheme": "Example", "archivePath": "build/Example.xcarchive" },
  "purchases": {
    "subscriptionGroups": [{ "referenceName": "Premium", "subscriptions": [{ "name": "Monthly Subscription", "productId": "com.example.app.premium.monthly" }] }],
    "inAppPurchases": [{ "name": "Lifetime Access", "productId": "com.example.app.premium.lifetime" }]
  }
}
```

Objects merge recursively and project values win. Subscription groups, subscriptions, and in-app purchases are matched by `referenceName`/`name`, so the project file only adds `productId` to the shared entries (a project entry with a new name is appended). Any other key in the project file — including one normally kept shared — overrides the shared value for that app. `--write-example PATH` and `--write-project-example PATH` write starting shapes for each file.

Required after merging (checked before any API call): `apiKey.*`, `app.bundleId`, `app.sku`, `app.primaryLocale`, `version.versionString`, `build.bundleVersion`, and a `productId` for every purchase.

The required positional `root` argument is the app-assets directory. `build.ipaPath`, `localizationsPath`, and media file paths are relative to that directory unless absolute. Before it archives, the deployer searches App Store Connect for the configured short version, build number, and platform. If that build has already been uploaded, it skips Xcode entirely and waits for that build to validate before attaching it to the App Store version; an IPA is not required on that path. Otherwise, set `build.createIpa` to `true` and provide `projectPath` plus `scheme` to have the deployer archive and export the signed IPA. `archivePath`, `exportPath`, `configuration`, `exportOptions`, and `allowProvisioningUpdates` are optional; the latter explicitly permits Xcode to obtain automatic-signing assets from Apple. If `createIpa` is false, provide an already-exported IPA at `build.ipaPath`.

Use `--build-only` to create and verify the configured IPA without contacting App Store Connect:

```sh
./deploy_app_store.py --build-only /absolute/path/to/app-assets
```

Use `app.attributes` for any supported global App attributes that should be reconciled (for example `isOrEverWasMadeForKids`, `accessibilityUrl`, and subscription status URLs), and `version.attributes` for supported App Store version attributes. These opt-in maps are passed as the corresponding JSON:API attributes, so they remain forward-compatible with Apple’s current schema without the script guessing legally sensitive settings. The app’s primary category is always set to Education and its Content Rights declaration is always set to “No, it does not contain, show, or access third-party content.”

Every App Info localization uses `https://asgarov1.github.io/Privacy-Policies/<app_name>_privacy_policy`, where `<app_name>` is the lowercase, underscore-separated final component of the bundle ID (for example, `korean-topik-ii` becomes `korean_topik_ii`). Age-rating declarations are configured manually in App Store Connect and are never read or changed by this script.

Every deployment also reconciles the App Review information for its App Store version: Javid Asgarov (`+436644311561`, `asgarov1@gmail.com`), no required demo account, and the note “The app does not require login. It works fully offline without an account.” These values are intentionally fixed by the script.

The `media` section has arrays of `{ locale, displayType }`; `folder` is optional. The deployer recursively uploads every non-hidden file in each folder, in stable path order. Use `files` with a non-empty list of explicit paths when a display type has a specific asset, such as an individual preview video; it takes precedence over `folder`. Without either, it expects screenshots in `screenshots/<locale>/<displayType>` and previews in `previews/<locale>/<displayType>` beneath `root`. Paths are resolved from `root` unless absolute. Screenshot display types use values such as `APP_IPHONE_67`; preview types use the corresponding values without the `APP_` prefix, such as `IPHONE_67`.

Jlingo clients additionally use a fixed screenshot layout: `screenshots/iphone/<language>` and `screenshots/ipad/<language>`. The deployer automatically uploads those folders as `APP_IPHONE_67` and `APP_IPAD_PRO_3GEN_129`, respectively, but only when the corresponding App Store locale is present in `localizations.json`. The fixed folder-to-store-locale mapping is `ar→ar-SA`, `en→en-US`, `fi→fi`, `fr→fr-FR`, `de→de-DE`, `it→it`, `ja→ja`, `zh-Hans→zh-Hans`, `pl→pl`, `pt→pt-PT`, `ru→ru`, `sh→hr`, `es→es-ES`, and `tr→tr`. Bulgarian is not an App Store Connect language, so `bg-BG` is skipped for all App Store Connect localizations (metadata, screenshots, subscription groups, and products). This is the shared localization set for Jlingo clients; do not add arbitrary screenshot-directory locales. Explicit screenshot media entries remain supported and take precedence for the same locale/display type.

`purchases.subscriptionGroups[].subscriptions[]` accepts `name`, `productId`, `subscriptionPeriod`, optional `familySharable`, and an optional USA base `price`. `purchases.inAppPurchases[]` accepts `name`, `productId`, `inAppPurchaseType`, optional `familySharable`, and an optional USA base `price`. All subscriptions and in-app purchases are made available in every active App Store territory, including territories Apple adds later.

The app itself defaults to a free USD base price (`app.price: 0`) and is made available in every active App Store territory, including future territories. Set `app.price` to a non-negative USD amount to choose a different initial base price; an existing App Store price schedule is preserved.

Every subscription and in-app purchase uses the fixed App Review note that
explains how to reach **Unlock Premium**. The matching review screenshot is the
shared [`Premium_with_three_options.jpg`](/Users/asgarov1/Projects/swift/scripts/Premium_with_three_options.jpg) in the scripts directory. On reruns, the deployer leaves any existing product review screenshot unchanged; it uploads the shared file only when the product has no review screenshot.

## `localizations.json`

For Jlingo language apps, every locale must use the same canonical
`appInformation.name`: `Jlingo ${language} ${level}` (for example,
`Jlingo German A1`). The language portion remains in English; only the other
store metadata is translated.

```json
{
  "en-US": {
    "appInformation": {
      "name": "Example",
      "subtitle": "Learn something useful",
      "privacyPolicyUrl": "https://example.com/privacy"
    },
    "appStoreVersion": {
      "description": "A complete App Store description.",
      "keywords": "learning,practice,example",
      "marketingUrl": "https://example.com",
      "supportUrl": "https://example.com/support",
      "whatsNew": "First release."
    },
    "subscriptions": {
      "com.example.app.monthly": {
        "displayName": "Monthly Premium",
        "description": "Unlimited premium access every month."
      }
    },
    "inAppPurchases": {
      "com.example.app.lifetime": {
        "displayName": "Lifetime Access",
        "description": "Unlock all premium features forever."
      }
    }
  }
}
```

The deployer always sets Promotional Text to “No account, no registration, fully
offline — ideal for learning wherever you are.” It applies the built-in locale
translation for supported languages and falls back to that English text for any
other locale, so `promotionalText` in `localizations.json` is intentionally
ignored. The legacy-compatible `appInformation.description`, `keywords`,
`supportUrl`, and related version fields are also accepted and are overridden
individually by fields in `appStoreVersion`. For an app update, every App Store metadata locale must provide
`appStoreVersion.whatsNew`; the legacy `appInformation.releaseNotes` key is also
accepted. The deployer omits `whatsNew` for an app's first version, where Apple
does not require it.

Each configured subscription group is localized through its draft
`subscriptionGroupVersion`. Add a locale-specific `subscriptionGroup` object
with `displayName` (and optional `customAppName`) to override its text. When it
is absent, the deployer creates a missing group localization from that locale's
`appInformation.name`, so every listed locale—including Korean when present—is
covered without duplicating the app name.

## Reruns and checkpoints

Localized text is validated against App Store Connect's character limits for every store locale before any remote change: app name/subtitle 30, keywords 100, promotional text 170, description/what's new 4000, subscription-group name 75 and custom app name 30, subscription display name 30 and description 55, in-app purchase display name 30 and description 45 (product name and IAP description limits are conservative). Text is never truncated: the deployer lists every over-long value and stops, and the fix is to rewrite that text in `localizations.json`. If Apple still rejects a value as too long, the deployment stops with the field, locale and Apple's maximum; rewrite the text and update `FIELD_LIMITS`.

Every meaningful action begins with `STEP nn` in the log. `.deploy-app-api-state.json` stores only remote upload IDs and asset hashes with mode `0600`; it contains no credentials. Reruns find resources by stable keys, patch only values that differ, skip media whose remote name/size match, and resume expired/interrupted reservations safely. If App Store Connect reports an existing in-flight subscription or in-app-purchase version, the deployer reuses that version and continues synchronizing any missing product localizations instead of retrying its creation. Requests retry transient network failures, Apple rate limits, and server failures with exponential backoff.

Apple-side processing can exceed the default 30-minute `build.processingTimeoutSeconds`; a timeout is not a lost upload. Run the exact same command again to resume and attach the build once Apple marks it valid.

## Preconditions

Create the App Store Connect app record and its bundle identifier/signing entitlement once in the Apple portals first. Apple’s current public Apps API is read/modify only, so an API-only script cannot create this initial record; after that prerequisite, the deployment flow is REST API-only. Also truthfully configure privacy answers, age-rating declarations, export compliance, contracts/tax/banking, and any App Review details beyond the fixed contact/no-login/note fields above; these workflows are not safely inferable from an IPA and some cannot be fully created by the public API. The script intentionally does not submit for review.

Apple references used for this implementation: [Build uploads](https://developer.apple.com/documentation/appstoreconnectapi/buildupload), [asset uploads](https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect), and [v2 purchase-localization migration](https://developer.apple.com/documentation/appstoreconnectapi/migrating-in-app-purchase-metadata-to-v2).

## Updating an existing release

The deployer always selects the highest editable App Store version for the configured platform, comparing numeric version components (so `3.10` is newer than `3.9`), regardless of `version.versionString`. If none is editable, it creates `version.versionString`; if that number already exists in a non-editable state, it stops and asks for a new release number. Selection happens before build lookup, and the selected version becomes the default build short version. An explicit `build.shortVersion` must match the selected version; the IPA must also be built with that version. After ensuring the version exists, it selects the editable App Info for category and localized app information by `state` (or legacy `appStoreState`), rather than assuming the first App Info is editable. Apple can return both live and upcoming App Info records; see [Apple’s App Info reference](https://developer.apple.com/documentation/appstoreconnectapi/get-v1-apps-_id_-appinfos). Version localizations remain attached to the selected App Store version.

If no unique editable App Info exists, deployment stops with the observed IDs and states instead of targeting live metadata. Ensure the target version is editable and rerun. Attribute errors with code `ENTITY_ERROR.ATTRIBUTE.INVALID.INVALID_STATE` are handled immediately, like the older `STATE_ERROR` response. A locked field produces a warning that its requested value was not applied; other editable fields continue to synchronize.

Offline regression checks: `python3 -B -m unittest discover -s deploy-app-api/tests -v`.
