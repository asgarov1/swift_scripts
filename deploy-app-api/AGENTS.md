# API-only App Store deployment

`deploy_app_store.py` is a standalone, standard-library Python deployment client for App Store Connect. It **must never** use Fastlane, Transporter, `altool`, Apple-ID sessions, or scraping. Authentication is ES256 JWT made from an App Store Connect `.p8` key; every remote mutation is an App Store Connect REST API call.

## Contract

- Invoke it with a required deployment-root argument: `./deploy_app_store.py /path/to/app-assets`. Configuration is the sibling `deployment.json` (shared across all apps; `--config` overrides) deep-merged with `<root>/deployment.json` (per-app values: bundle ID, SKU, version, build number/paths/scheme, purchase product IDs; `--project-config` overrides). Keep anything identical across apps in the shared file and only per-app values in the project file. The root is never read from or overridden by JSON.
- `localizations.json` is authoritative for per-locale App Info and App Store version text, plus each product's `subscriptions` mapping. Existing remote values are patched only when their requested value differs.
- For every Jlingo language app, use the same canonical App Store name in every locale: `Jlingo ${language} ${level}` (for example, `Jlingo German A1`). Keep the language name in English and do not translate `appInformation.name` per locale.
- It reuses the existing App Store Connect app record and creates/reuses its draft version, metadata localizations, screenshot/preview sets, subscription groups, subscriptions, non-subscription IAPs, product versions, localizations, pricing, and build association. Apple’s current public Apps API does not create an app record, so that one-time portal action is an explicit prerequisite.
- Assets are content-addressed locally (SHA-256) and compared to remote name/size/checksum fields where Apple exposes them. The state journal makes retries resume incomplete upload reservations. Never delete existing remote media automatically.
- All API traffic has bounded exponential retry for connection failures, 429, and 5xx. Every durable operation logs a numbered `STEP n` line. It is safe to rerun after interruption.
- The script expects an already signed `.ipa`; it uploads that IPA through the current `buildUploads` REST resources. It does not build or sign an app.

## App Store text limits (localizations.json)

App Store Connect rejects over-long localized text. Every value in an app's `store-metadata/localizations.json` must fit these limits **in every locale** (count characters, not bytes; Japanese/Chinese/Arabic count the same way):

| Field | Max |
|---|---|
| `appInformation.name`, `appInformation.subtitle` | 30 |
| `appInformation.keywords` (comma-separated, no spaces after commas) | 100 |
| promotional text | 170 |
| `description`, `whatsNew` | 4000 |
| `subscriptionGroup.displayName` | 75 |
| `subscriptionGroup.customAppName` | 30 |
| subscription `displayName` | 30 |
| subscription `description` | 55 |
| in-app purchase (e.g. `…premium.lifetime`) `displayName` | 30 |
| in-app purchase `description` | 45 |

Rules:

- **Never truncate or cut text**, and never add `…`. When a value is too long, rewrite it as a shorter, natural sentence that keeps the same meaning (drop filler such as "complete"/"full"/"durante", use shorter synonyms or structure).
- Keep a product's text parallel across its tiers within a locale (monthly / 3 months / lifetime use the same pattern).
- Write each language natively; don't shorten one locale by making it less accurate than the others.
- After editing, check lengths for all locales (e.g. a short `python3` loop over the JSON), not just the one that failed.
- Edit the JSON as text (targeted replacements) so its existing formatting is preserved.
- `deploy-app-api/deploy_app_store.py` enforces these limits in `FIELD_LIMITS` before any API call and stops with a list of offending values; it never shortens text itself. If Apple reports a different maximum (`too long. Max number of characters is N`), update `FIELD_LIMITS` and the table here.

## Configuration and safety

Start with `./deploy_app_store.py --write-example deployment.json` and `--write-project-example <root>/deployment.json`, then validate with `--dry-run`. Keep the API key outside source control and set restrictive file permissions.

The tool does not submit the App Store version for review by default. Set `submitForReview: true` only after all review, export-compliance, privacy, agreements, tax, banking, and age-rating requirements are truthfully satisfied. Apple does not expose every legal/privacy workflow in this API, so the script explicitly reports these prerequisites instead of inventing answers.

When adding endpoints, verify resource types, endpoint paths, request fields, and lifecycle state in Apple's current App Store Connect OpenAPI reference. In particular, current product localizations use v2 endpoints and draft `inAppPurchaseVersions`, `subscriptionVersions`, and `subscriptionGroupVersions` resources.

## Verification

Run `python3 -m py_compile deploy_app_store.py`, `./deploy_app_store.py --write-example /tmp/example.json --write-project-example /tmp/project.json`, and `./deploy_app_store.py --config /tmp/example.json --project-config /tmp/project.json --dry-run /tmp`. Do not test against production App Store Connect unless expressly requested.
