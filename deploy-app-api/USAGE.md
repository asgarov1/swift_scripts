# Using `deploy-app-api` with `spanish-a1`

Run the deployment from any directory with:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deploy_app_store.py \
  /Users/asgarov1/Projects/swift/Spanish/spanish-a1
```

Or, from the deployer directory:

```sh
cd /Users/asgarov1/Projects/swift/scripts/deploy-app-api
./deploy_app_store.py /Users/asgarov1/Projects/swift/Spanish/spanish-a1
```

The command automatically merges:

- the shared configuration at `/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deployment.json`; and
- the Spanish A1 configuration at `/Users/asgarov1/Projects/swift/Spanish/spanish-a1/deployment.json`.

Paths in the project configuration, including the Xcode project, IPA, store metadata, screenshots, and previews, are resolved relative to `/Users/asgarov1/Projects/swift/Spanish/spanish-a1`.

The Spanish A1 configuration has `build.createIpa` enabled through the shared configuration. If App Store Connect does not already contain the configured version/build, the command archives and exports the app with Xcode before uploading it. The deployer reconciles the App Store metadata, media, products, and build, but does not submit the version for App Review.

## Optional creative assets

If `/Users/asgarov1/Projects/swift/Spanish/spanish-a1/app-store-assets` exists, the deployer automatically uses its `manifest.json`. To use the shared Spanish assets instead:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deploy_app_store.py \
  /Users/asgarov1/Projects/swift/Spanish/spanish-a1 \
  --app-store-assets /Users/asgarov1/Projects/swift/Spanish/app-store-assets
```

The explicit path overrides the project-local directory. Videos and PNG alternatives are uploaded to Asset Library, and videos are assigned to localized Header and Search Results slots in the editable version. This does not submit or publish them. With no explicit path and no project-local directory, creative uploads are skipped.

## Optional checks

Build and verify the configured IPA without contacting App Store Connect:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deploy_app_store.py \
  --build-only \
  /Users/asgarov1/Projects/swift/Spanish/spanish-a1
```

Preview App Store Connect mutations without applying them:

```sh
/Users/asgarov1/Projects/swift/scripts/deploy-app-api/deploy_app_store.py \
  --dry-run \
  /Users/asgarov1/Projects/swift/Spanish/spanish-a1
```

`--dry-run` still reads App Store Connect and may create the signed IPA locally when the configured build is not already uploaded; it only suppresses remote mutations and uploads.

The deployer is safe to rerun after an interruption. It resumes or skips work that is already complete.
