# App Store Connect API deployer

`deploy_app_store.py` deploys an already-signed IPA using only the current App Store Connect REST API. It does not invoke Fastlane, Transporter, `altool`, Xcode, or an Apple-ID session.

```sh
cd /Users/asgarov1/Projects/swift/scripts/deploy-app-api
./deploy_app_store.py --write-example deployment.json
# edit deployment.json and add localizations.json beneath its root
./deploy_app_store.py /absolute/path/to/app-assets
```

It uses `/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deployment.json` by default. Pass `--config /other/path.json` only when intentionally using a different configuration. It uses an App Store Connect team API key (`keyId`, `issuerId`, and the local `.p8` file). The only local executable dependency is macOS `openssl`, used solely to create the ES256 JWT required by Apple.

## Configuration

The generated `deployment.json` is a complete starting shape. Required fields are:

- `app.bundleId`, `app.sku`, `app.primaryLocale`
- `version.versionString`
- `build.ipaPath` and `build.bundleVersion`
- `localizationsPath`

The required positional `root` argument is the app-assets directory. `build.ipaPath`, `localizationsPath`, and media file paths are relative to that directory unless absolute. Before it archives, the deployer searches App Store Connect for the configured short version, build number, and platform. If that build has already been uploaded, it skips Xcode entirely and waits for that build to validate before attaching it to the App Store version; an IPA is not required on that path. Otherwise, set `build.createIpa` to `true` and provide `projectPath` plus `scheme` to have the deployer archive and export the signed IPA. `archivePath`, `exportPath`, `configuration`, `exportOptions`, and `allowProvisioningUpdates` are optional; the latter explicitly permits Xcode to obtain automatic-signing assets from Apple. If `createIpa` is false, provide an already-exported IPA at `build.ipaPath`.

Use `--build-only` to create and verify the configured IPA without contacting App Store Connect:

```sh
./deploy_app_store.py --build-only /absolute/path/to/app-assets
```

Use `app.attributes` for any supported global App attributes that should be reconciled (for example `isOrEverWasMadeForKids`, `accessibilityUrl`, and subscription status URLs), and `version.attributes` for supported App Store version attributes. These opt-in maps are passed as the corresponding JSON:API attributes, so they remain forward-compatible with Apple’s current schema without the script guessing legally sensitive settings. The app’s primary category is always set to Education and its Content Rights declaration is always set to “No, it does not contain, show, or access third-party content.”

Every deployment also sets all age-rating content descriptors and feature declarations to their “No” values (`NONE` or `false`), with no age-rating override. Every App Info localization uses `https://asgarov1.github.io/Privacy-Policies/<app_name>_privacy_policy`, where `<app_name>` is the lowercase, underscore-separated final component of the bundle ID (for example, `korean-topik-ii` becomes `korean_topik_ii`).

Every deployment also reconciles the App Review information for its App Store version: Javid Asgarov (`+436644311561`, `asgarov1@gmail.com`), no required demo account, and the note “The app does not require login. It works fully offline without an account.” These values are intentionally fixed by the script.

The `media` section has arrays of `{ locale, displayType }`; `folder` is optional. The deployer recursively uploads every non-hidden file in each folder, in stable path order. Use `files` with a non-empty list of explicit paths when a display type has a specific asset, such as an individual preview video; it takes precedence over `folder`. Without either, it expects screenshots in `screenshots/<locale>/<displayType>` and previews in `previews/<locale>/<displayType>` beneath `root`. Paths are resolved from `root` unless absolute. Screenshot display types use values such as `APP_IPHONE_67`; preview types use the corresponding values without the `APP_` prefix, such as `IPHONE_67`.

`purchases.subscriptionGroups[].subscriptions[]` accepts `name`, `productId`, `subscriptionPeriod`, optional `familySharable`, and optional USA `price`. `purchases.inAppPurchases[]` accepts `name`, `productId`, `inAppPurchaseType`, optional `familySharable`, `reviewNote`, and optional USA `price`.

## `localizations.json`

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
`supportUrl`, and related version fields are also accepted if `appStoreVersion`
is absent.

## Reruns and checkpoints

Every meaningful action begins with `STEP nn` in the log. `.deploy-app-api-state.json` stores only remote upload IDs and asset hashes with mode `0600`; it contains no credentials. Reruns find resources by stable keys, patch only values that differ, skip media whose remote name/size match, and resume expired/interrupted reservations safely. If App Store Connect reports an existing in-flight subscription or in-app-purchase version, the deployer reuses that version and continues synchronizing any missing product localizations instead of retrying its creation. Requests retry transient network failures, Apple rate limits, and server failures with exponential backoff.

Apple-side processing can exceed the default 30-minute `build.processingTimeoutSeconds`; a timeout is not a lost upload. Run the exact same command again to resume and attach the build once Apple marks it valid.

## Preconditions

Create the App Store Connect app record and its bundle identifier/signing entitlement once in the Apple portals first. Apple’s current public Apps API is read/modify only, so an API-only script cannot create this initial record; after that prerequisite, the deployment flow is REST API-only. Also truthfully configure privacy answers, age-rating declarations, export compliance, contracts/tax/banking, and any App Review details beyond the fixed contact/no-login/note fields above; these workflows are not safely inferable from an IPA and some cannot be fully created by the public API. The script intentionally does not submit for review.

Apple references used for this implementation: [Build uploads](https://developer.apple.com/documentation/appstoreconnectapi/buildupload), [asset uploads](https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect), and [v2 purchase-localization migration](https://developer.apple.com/documentation/appstoreconnectapi/migrating-in-app-purchase-metadata-to-v2).
