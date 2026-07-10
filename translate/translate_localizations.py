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
from typing import Any, Callable


APP_LOCALES = [
    "en", "zh-Hans", "hi", "es", "ar", "fr", "fi", "bn", "pt", "ru", "ur", "id", "de",
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
    "yue-Hant": "yue",
    # Google no longer exposes Serbo-Croatian directly here. Croatian is the
    # closest Latin-script fallback for the app's historical "sh" key.
    "sh": "hr",
}


class TranslationError(RuntimeError):
    pass


class TranslationProgress:
    def __init__(self, total: int) -> None:
        self.current = 0
        self.total = total

    def log(self, text: str, source_lang: str, target_locale: str) -> None:
        self.current += 1
        print(
            f"[{self.current}/{self.total}] translating {text!r} "
            f"from {source_lang} to {target_locale}",
            flush=True,
        )

    def log_result(self, result: str) -> None:
        print(
            f"[{self.current}/{self.total}]\tresult: {result!r}",
            flush=True,
        )

    def log_error(
        self,
        text: str,
        source_lang: str,
        target_locale: str,
        attempt: int,
        retries: int,
        error: Exception,
    ) -> None:
        print(
            f"[{self.current}/{self.total}] ERROR translating {text!r} "
            f"from {source_lang} to {target_locale} "
            f"(attempt {attempt}/{retries}): {error}",
            file=sys.stderr,
            flush=True,
        )


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
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)


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
    write_text_atomic(
        path,
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def cache_key(source_lang: str, target_locale: str, text: str) -> str:
    return json.dumps([google_code(source_lang), google_code(target_locale), text], ensure_ascii=False)


def request_translation(
    text: str,
    source_lang: str,
    target_locale: str,
    progress: TranslationProgress,
    retries: int = 4,
) -> str:
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
            progress.log_error(
                text,
                source_lang,
                target_locale,
                attempt + 1,
                retries,
                exc,
            )
            time.sleep(0.6 * (attempt + 1))

    raise TranslationError(f"translation failed for {text!r} -> {target_locale}: {last_error}")


def translate(
    text: str,
    source_lang: str,
    target_locale: str,
    cache: dict[str, str],
    cache_path: Path,
    dry_run: bool,
    progress: TranslationProgress,
) -> str:
    if target_locale == source_lang:
        return text
    progress.log(text, source_lang, target_locale)
    key = cache_key(source_lang, target_locale, text)
    if key in cache:
        result = cache[key]
    elif dry_run:
        result = f"[{target_locale}] {text}"
    else:
        result = request_translation(text, source_lang, target_locale, progress)
        cache[key] = result
        # Persist the result immediately. If the process stops before the content
        # file checkpoint, the next run can reuse this cached translation.
        write_cache(cache_path, cache)
    progress.log_result(result)
    return result


def source_for_map(
    mapping: dict[str, Any],
    source_lang: str,
    source_text: str | None,
    fallback_locale: str,
) -> str:
    source_value = normalize_text(mapping.get(source_lang))
    if source_value:
        return source_value
    if source_text:
        return source_text
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
    cache_path: Path,
    overwrite: bool,
    dry_run: bool,
    progress: TranslationProgress,
    checkpoint: Callable[[], None],
) -> int:
    source = source_for_map(mapping, source_lang, source_text, fallback_locale)
    changed = 0

    for locale in APP_LOCALES:
        current = normalize_text(mapping.get(locale))
        if current and not overwrite:
            continue
        value = (
            source
            if locale == source_lang
            else translate(
                source,
                source_lang,
                locale,
                cache,
                cache_path,
                dry_run,
                progress,
            )
        )
        if mapping.get(locale) != value:
            mapping[locale] = value
            changed += 1
            checkpoint()

    ordered = {locale: mapping[locale] for locale in APP_LOCALES}
    mapping.clear()
    mapping.update(ordered)
    return changed


def process_item(
    item: dict[str, Any],
    source_lang: str,
    fallback_locale: str,
    cache: dict[str, str],
    cache_path: Path,
    overwrite: bool,
    dry_run: bool,
    progress: TranslationProgress,
    checkpoint: Callable[[], None],
) -> int:
    changed = 0

    # For learner content, use an authored value for the requested source locale
    # when one exists. Otherwise, the foreign phrase/word is the cleanest source.
    learner_source = normalize_text(item.get("foreign")) or normalize_text(item.get("infinitive")) or None
    if isinstance(item.get("translations"), dict):
        changed += fill_map(
            item["translations"],
            source_lang,
            learner_source,
            fallback_locale,
            cache,
            cache_path,
            overwrite,
            dry_run,
            progress,
            checkpoint,
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
            cache_path,
            overwrite,
            dry_run,
            progress,
            checkpoint,
        )
    if isinstance(item.get("explanations"), dict):
        changed += fill_map(
            item["explanations"],
            source_lang,
            None,
            fallback_locale,
            cache,
            cache_path,
            overwrite,
            dry_run,
            progress,
            checkpoint,
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
            cache_path,
            overwrite,
            dry_run,
            progress,
            checkpoint,
        )

    return changed


def count_map_translations(
    mapping: dict[str, Any],
    source_lang: str,
    overwrite: bool,
) -> int:
    return sum(
        1
        for locale in APP_LOCALES
        if locale != source_lang
        and (overwrite or not normalize_text(mapping.get(locale)))
    )


def count_item_translations(
    item: dict[str, Any],
    source_lang: str,
    overwrite: bool,
) -> int:
    total = 0
    for field in ("translations", "titles", "explanations"):
        mapping = item.get(field)
        if isinstance(mapping, dict):
            total += count_map_translations(mapping, source_lang, overwrite)
    for example in item.get("examples", []):
        if isinstance(example, dict) and isinstance(example.get("translations"), dict):
            total += count_map_translations(example["translations"], source_lang, overwrite)
    return total


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
        description="Translate Jlingo JSON files into the supported localization maps.",
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
    loaded_files = [(path, load_json(path)) for path in files]
    for path, data in loaded_files:
        if not isinstance(data, list):
            raise TranslationError(f"{path}: top-level JSON must be a list")

    translation_total = sum(
        count_item_translations(item, source_lang, args.overwrite)
        for _path, data in loaded_files
        for item in data
        if isinstance(item, dict)
    )
    progress = TranslationProgress(translation_total)

    total_changed = 0
    all_issues: list[str] = []

    for path, data in loaded_files:
        changed = 0

        def checkpoint() -> None:
            if not args.dry_run:
                save_json(path, data)

        for item in data:
            if isinstance(item, dict):
                changed += process_item(
                    item,
                    source_lang,
                    fallback_locale,
                    cache,
                    args.cache,
                    args.overwrite,
                    args.dry_run,
                    progress,
                    checkpoint,
                )

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
