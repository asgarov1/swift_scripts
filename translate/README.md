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

When the requested source locale already exists in a localization map, that
authored value is used as the translation source. For example, this uses the
existing English translations—not the learner-language `foreign` values—as
the source for every missing localization:

```sh
make start ../../Swedish/swedish-a1/swedish-a1 en
```

If the requested source locale is missing, learner content falls back to its
`foreign` or `infinitive` value. Grammar titles and explanations fall back to
the locale selected by `--fallback-locale` (English by default).

Each translation is printed with its overall progress, source text, source
locale, and target locale:

```text
[144/250] translating 'Hello' from en to de
[144/250]	result: 'Hallo'
```

Successful translations are checkpointed immediately to both the cache and the
input JSON file using atomic writes. If the process is interrupted, run the
same command again; it skips populated localizations and continues with those
that are still missing. Translation retry errors are printed to standard error
with the same progress counter.

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
