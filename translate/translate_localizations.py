#!/usr/bin/env python3
"""
Fill Jlingo JSON localization maps for all supported app languages.

Examples:
  python3 scripts/generated/translate_localizations.py --source-lang fr french-b2/french-b2
  python3 scripts/generated/translate_localizations.py --source-lang es spanish-b1/spanish-b1 --overwrite
  python3 scripts/generated/translate_localizations.py --source-lang fr french-b2/french-b2 --dry-run

The script understands the app data files:
  vocabulary.json, phrases.json, verbs.json, grammar.json

It fills these map fields when present:
  translations, titles, explanations, examples[].translations
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


APP_LOCALES = [
    "en", "zh-Hans", "hi", "es", "ar", "fr", "bn", "pt", "ru", "ur", "id", "de",
    "ja", "sw", "mr", "te", "tr", "ta", "yue-Hant", "vi", "sh", "hu", "pl", "bg",
]

DEFAULT_FILENAMES = [
    "vocabulary.json",
    "phrases.json",
    "verbs.json",
    "grammar.json",
]

# Google Translate API language codes do not always match the app locale keys.
GOOGLE_CODES = {
    "zh-Hans": "zh-CN",
    "yue-Hant": "zh-TW",
    # Google no longer exposes Serbo-Croatian directly here. Croatian is the
    # closest Latin-script fallback for the app's historical "sh" key.
    "sh": "hr",
}


class TranslationError(RuntimeError):
    pass


def google_code(locale: str) -> str:
    return GOOGLE_CODES.get(locale, locale)


def normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TranslationError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TranslationError(f"invalid JSON in {path}: {exc}") from exc


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"invalid cache JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TranslationError(f"cache must be a JSON object: {path}")
    return {str(key): str(value) for key, value in raw.items()}


def write_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cache_key(source_lang: str, target_locale: str, text: str) -> str:
    return json.dumps([google_code(source_lang), google_code(target_locale), text], ensure_ascii=False)


def request_translation(text: str, source_lang: str, target_locale: str, retries: int = 4) -> str:
    source = google_code(source_lang)
    target = google_code(target_locale)
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    })
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    last_error: Exception | None = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
            if not translated:
                raise TranslationError(f"empty translation for {text!r} -> {target_locale}")
            time.sleep(0.06)
            return translated
        except Exception as exc:
            last_error = exc
            time.sleep(0.6 * (attempt + 1))

    raise TranslationError(f"translation failed for {text!r} -> {target_locale}: {last_error}")


def translate(
    text: str,
    source_lang: str,
    target_locale: str,
    cache: dict[str, str],
    dry_run: bool,
) -> str:
    if target_locale == source_lang:
        return text
    key = cache_key(source_lang, target_locale, text)
    if key in cache:
        return cache[key]
    if dry_run:
        return f"[{target_locale}] {text}"
    result = request_translation(text, source_lang, target_locale)
    cache[key] = result
    return result


def source_for_map(
    mapping: dict[str, Any],
    source_lang: str,
    source_text: str | None,
    fallback_locale: str,
) -> str:
    if source_text:
        return source_text
    source_value = normalize_text(mapping.get(source_lang))
    if source_value:
        return source_value
    fallback_value = normalize_text(mapping.get(fallback_locale))
    if fallback_value:
        return fallback_value
    english_value = normalize_text(mapping.get("en"))
    if english_value:
        return english_value
    raise TranslationError(f"cannot find source text in localization map: {mapping}")


def fill_map(
    mapping: dict[str, Any],
    source_lang: str,
    source_text: str | None,
    fallback_locale: str,
    cache: dict[str, str],
    overwrite: bool,
    dry_run: bool,
) -> int:
    source = source_for_map(mapping, source_lang, source_text, fallback_locale)
    changed = 0

    for locale in APP_LOCALES:
        current = normalize_text(mapping.get(locale))
        if current and not overwrite:
            continue
        value = source if locale == source_lang else translate(source, source_lang, locale, cache, dry_run)
        if mapping.get(locale) != value:
            mapping[locale] = value
            changed += 1

    ordered = {locale: mapping[locale] for locale in APP_LOCALES}
    mapping.clear()
    mapping.update(ordered)
    return changed


def process_item(
    item: dict[str, Any],
    source_lang: str,
    fallback_locale: str,
    cache: dict[str, str],
    overwrite: bool,
    dry_run: bool,
) -> int:
    changed = 0

    # For learner content, the foreign phrase/word is the cleanest source text.
    learner_source = normalize_text(item.get("foreign")) or normalize_text(item.get("infinitive")) or None
    if isinstance(item.get("translations"), dict):
        changed += fill_map(
            item["translations"],
            source_lang,
            learner_source,
            fallback_locale,
            cache,
            overwrite,
            dry_run,
        )

    # Grammar title/explanation maps often already contain the authored source
    # locale. Use that first, then fall back to English if needed.
    if isinstance(item.get("titles"), dict):
        changed += fill_map(
            item["titles"],
            source_lang,
            None,
            fallback_locale,
            cache,
            overwrite,
            dry_run,
        )
    if isinstance(item.get("explanations"), dict):
        changed += fill_map(
            item["explanations"],
            source_lang,
            None,
            fallback_locale,
            cache,
            overwrite,
            dry_run,
        )

    for example in item.get("examples", []):
        if not isinstance(example, dict) or not isinstance(example.get("translations"), dict):
            continue
        example_source = normalize_text(example.get("foreign")) or None
        changed += fill_map(
            example["translations"],
            source_lang,
            example_source,
            fallback_locale,
            cache,
            overwrite,
            dry_run,
        )

    return changed


def resolve_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(path / filename for filename in DEFAULT_FILENAMES)
        else:
            files.append(path)
    return files


def validate_locale_maps(data: Any, path: Path) -> list[str]:
    issues: list[str] = []

    def check_map(mapping: Any, label: str) -> None:
        if not isinstance(mapping, dict):
            issues.append(f"{label}: expected object")
            return
        missing = [locale for locale in APP_LOCALES if not normalize_text(mapping.get(locale))]
        extra = [locale for locale in mapping if locale not in APP_LOCALES]
        if missing:
            issues.append(f"{label}: missing {', '.join(missing)}")
        if extra:
            issues.append(f"{label}: extra {', '.join(extra)}")

    if not isinstance(data, list):
        return [f"{path}: top-level JSON must be a list"]

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            issues.append(f"{path}[{index}]: expected object")
            continue
        label = normalize_text(item.get("foreign")) or normalize_text(item.get("infinitive")) or f"item {index}"
        if "translations" in item:
            check_map(item["translations"], f"{path}[{index}] {label} translations")
        if "titles" in item:
            check_map(item["titles"], f"{path}[{index}] titles")
        if "explanations" in item:
            check_map(item["explanations"], f"{path}[{index}] explanations")
        for example_index, example in enumerate(item.get("examples", [])):
            if isinstance(example, dict) and "translations" in example:
                check_map(example["translations"], f"{path}[{index}].examples[{example_index}] translations")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate Jlingo JSON files into the 24 supported localization maps.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="App data directory or individual JSON file(s). A directory uses vocabulary/phrases/verbs/grammar JSON.",
    )
    parser.add_argument(
        "--source-lang",
        required=True,
        help="Source app locale / Google language code, e.g. fr, es, it, de, en.",
    )
    parser.add_argument(
        "--fallback-locale",
        default="en",
        help="Existing map locale to use when source text is not available. Default: en.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("scripts/generated/translation_cache.json"),
        help="Persistent JSON cache path. Default: scripts/generated/translation_cache.json.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing localized values. By default only missing/blank values are filled.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call the network or write files; report what would change.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_lang = args.source_lang
    fallback_locale = args.fallback_locale

    if source_lang not in APP_LOCALES and source_lang not in GOOGLE_CODES.values():
        print(f"warning: {source_lang!r} is not one of the app locales; using it as a Google source code", file=sys.stderr)

    files = resolve_files(args.paths)
    cache = read_cache(args.cache)
    total_changed = 0
    all_issues: list[str] = []

    for path in files:
        data = load_json(path)
        changed = 0
        if not isinstance(data, list):
            raise TranslationError(f"{path}: top-level JSON must be a list")
        for item in data:
            if isinstance(item, dict):
                changed += process_item(item, source_lang, fallback_locale, cache, args.overwrite, args.dry_run)

        issues = validate_locale_maps(data, path)
        all_issues.extend(issues)
        total_changed += changed

        if args.dry_run:
            print(f"would update {changed} values in {path}")
        else:
            save_json(path, data)
            print(f"updated {changed} values in {path}")

    if all_issues:
        print("\nvalidation issues:", file=sys.stderr)
        for issue in all_issues[:50]:
            print(f"  - {issue}", file=sys.stderr)
        if len(all_issues) > 50:
            print(f"  ... {len(all_issues) - 50} more", file=sys.stderr)
        return 1

    if not args.dry_run:
        write_cache(args.cache, cache)
        print(f"cache entries: {len(cache)} ({args.cache})")

    print(f"total changed values: {total_changed}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TranslationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
