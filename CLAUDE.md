# CLAUDE.md

## Testing

- Never run tests (unit, integration, or end-to-end) to validate your changes unless the user explicitly asks you to, or running them is strictly required to complete the task.
- Don't run test suites as a routine "verification" step after making edits.

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
