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

## Verification

After changing these scripts, run shell syntax checks, validate the generated
Fastfile with `ruby -c`, run `git diff --check`, and use a representative
project's `--dry-run` mode when the change affects staging or validation.
Never perform a live App Store Connect deployment merely to test a script
change unless the user explicitly requests it.
