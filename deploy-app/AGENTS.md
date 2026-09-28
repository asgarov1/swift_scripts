# deploy-app contributor guide

`deploy-app` prepares and submits arbitrary iOS projects to App Store Connect.
Treat its default invocation as a **convergent precheck/setup flow**, not as a
read-only validation step.

## Precheck contract

Running:

```sh
./deploy-app <app-project-path>
```

must, before Fastlane precheck runs, stage the complete project configuration
and ensure the App Store Connect resources needed for a first release exist.
That includes:

- all App Store metadata localizations, with
  `store-metadata/localizations.json` authoritative when present, including
  `en-US`;
- the default subscription group and configured monthly and quarterly
  subscriptions;
- the default lifetime non-consumable purchase; and
- initial prices for those products when no price has been configured.

The normal precheck command must not archive, upload, submit, release, or
otherwise publish an app. Those actions remain opt-in through the appropriate
explicit flags.

## Idempotence is required

Every operation in this flow must be safe to rerun after any partial failure.
Always look up an existing resource before creating it. If it exists, reuse it
and continue with any remaining setup (for example, a product that was created
before its price setup failed). Do not overwrite an existing product, price, or
localized value unless the project configuration explicitly identifies the
source as authoritative.

Use stable identifiers for lookups: product IDs for IAPs, reference names for
subscription groups, and locale codes for metadata. Product IDs sent to App
Store Connect may contain only ASCII letters, digits, underscores, and periods;
generated defaults must normalize bundle-identifier characters that are not
permitted.

Keep configuration staging deterministic so repeated calls do not create
unrelated diffs. Prefer API-key authentication and preserve the existing rule
that precheck never falls back to Apple ID web sessions.

## Follow Apple's API schema

Before adding or changing an App Store Connect API request, consult Apple's
current official schema for that exact endpoint and request body. Verify the
complete payload: required and allowed fields, attributes, relationship names,
resource `type` values, and inline resource IDs. Do not infer resource types
from endpoint versions or relationship names; for example, `inAppPurchaseV2`
uses the resource type `inAppPurchases`, not `inAppPurchasesV2`.

Treat the endpoint's schema as authoritative when prose examples disagree.
When fixing an API validation error, review the entire affected payload against
the schema and update relevant regression tests to cover the API contract,
rather than only the field identified by the first error. Local mocks and dry
runs do not prove that Apple will accept a request.

## Verification

After changing these scripts, run shell syntax checks, validate the generated
Fastfile with `ruby -c`, run `git diff --check`, and use a representative
project's `--dry-run` mode when the change affects staging or validation.
Never perform a live App Store Connect deployment merely to test a script
change unless the user explicitly requests it.

## Localized App Store copy

When creating or translating `store-metadata/localizations.json` (or the
equivalent `DEPLOY_ENV` metadata), preserve the source meaning but make each
localized value fit the applicable App Store Connect limit. Do not truncate
mid-word: rewrite concisely and then count the final translated value. These
limits apply independently to every locale:

| JSON / environment field | App Store Connect limit |
| --- | --- |
| `appInformation.name` / app name | 2–30 characters |
| `appInformation.subtitle` / `SUBTITLE` | 30 characters |
| `appInformation.description` / `DESCRIPTION` | 4,000 characters |
| `appInformation.keywords` / `KEYWORDS` | 100 UTF-8 bytes (not merely 100 characters) |
| `appInformation.promotionalText` / `PROMOTIONAL_TEXT` | 170 characters |
| `appInformation.releaseNotes` / `RELEASE_NOTES` | 4,000 characters |
| `subscriptionGroup.displayName` | 1–75 characters |
| `subscriptionGroup.customAppName` | 1–30 characters, or `null` |
| `subscriptions.<product-id>.displayName` | 2–30 characters |
| `subscriptions.<product-id>.description` | 45 characters |

The deployment helper currently validates only some of these fields (and
allows up to 35 characters for product display names). Treat the Apple limits
above as authoritative when authoring or translating text, so metadata is
valid before it reaches Fastlane or App Store Connect. Subscription-group
display names must also avoid control characters and markup. Keep keywords as
comma-separated search terms; each term must be more than two characters and
must not repeat the app or company name.
