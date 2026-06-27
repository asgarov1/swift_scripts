# Translate Localizations

Use this folder to fill missing localization maps in the app JSON files:

- `vocabulary.json`
- `phrases.json`
- `verbs.json`
- `grammar.json`

## Makefile Usage

From this directory, run:

```sh
make start <path_to_folder> <source_language>
```

Example:

```sh
make start ../../french-b2/french-b2 fr
```

The first argument is the folder that contains the JSON files. The second
argument is the source language code, such as `fr`, `es`, `it`, `de`, or `en`.

Pass optional script flags with `ARGS`:

```sh
make start ../../french-b2/french-b2 fr ARGS='--dry-run'
make start ../../spanish-b1/spanish-b1 es ARGS='--overwrite'
```

## Direct Script Usage

You can also call the script directly:

```sh
python3 translate_localizations.py --source-lang fr ../../french-b2/french-b2
```

Useful options:

- `--dry-run`: report what would change without writing files or calling the network.
- `--overwrite`: replace existing localized values instead of only filling blanks.
- `--fallback-locale en`: choose the existing map locale used when source text is missing.
- `--cache <path>`: choose where to store the translation cache.
