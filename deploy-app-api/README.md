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

The required positional `root` argument is the app-assets directory. `build.ipaPath`, `localizationsPath`, and media file paths are relative to that directory unless absolute. Set `build.createIpa` to `true` and provide `projectPath` plus `scheme` to have the deployer archive and export the signed IPA through Xcode before it makes App Store Connect changes. `archivePath`, `exportPath`, `configuration`, `exportOptions`, and `allowProvisioningUpdates` are optional; the latter explicitly permits Xcode to obtain automatic-signing assets from Apple. Otherwise, provide an already-exported IPA at `build.ipaPath`.

Use `--build-only` to create and verify the configured IPA without contacting App Store Connect:

```sh
./deploy_app_store.py --build-only /absolute/path/to/app-assets
```

Use `app.attributes` for any supported global App attributes that should be reconciled (for example `contentRightsDeclaration`, `isOrEverWasMadeForKids`, `accessibilityUrl`, and subscription status URLs), and `version.attributes` for supported App Store version attributes. These opt-in maps are passed as the corresponding JSON:API attributes, so they remain forward-compatible with Apple’s current schema without the script guessing legally sensitive settings.

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
      "promotionalText": "A short promotion.",
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

The legacy-compatible `appInformation.description`, `keywords`, `supportUrl`, and related version fields are also accepted if `appStoreVersion` is absent.

## Reruns and checkpoints

Every meaningful action begins with `STEP nn` in the log. `.deploy-app-api-state.json` stores only remote upload IDs and asset hashes with mode `0600`; it contains no credentials. Reruns find resources by stable keys, patch only values that differ, skip media whose remote name/size match, and resume expired/interrupted reservations safely. Requests retry transient network failures, Apple rate limits, and server failures with exponential backoff.

Apple-side processing can exceed the default 30-minute `build.processingTimeoutSeconds`; a timeout is not a lost upload. Run the exact same command again to resume and attach the build once Apple marks it valid.

## Preconditions

Create the App Store Connect app record and its bundle identifier/signing entitlement once in the Apple portals first. Apple’s current public Apps API is read/modify only, so an API-only script cannot create this initial record; after that prerequisite, the deployment flow is REST API-only. Also truthfully configure privacy answers, age-rating declarations, export compliance, contracts/tax/banking, and review details; these workflows are not safely inferable from an IPA and some cannot be fully created by the public API. The script intentionally does not submit for review.

Apple references used for this implementation: [Build uploads](https://developer.apple.com/documentation/appstoreconnectapi/buildupload), [asset uploads](https://developer.apple.com/documentation/appstoreconnectapi/uploading-assets-to-app-store-connect), and [v2 purchase-localization migration](https://developer.apple.com/documentation/appstoreconnectapi/migrating-in-app-purchase-metadata-to-v2).
