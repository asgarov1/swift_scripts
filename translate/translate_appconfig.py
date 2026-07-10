#!/usr/bin/env python3
"""
Fill missing AppConfig localization dictionaries in Swift app files.

Examples:
  python3 translate_appconfig.py --source-lang english ../../Swedish/swedish-a2/swedish-a2
  python3 translate_appconfig.py --source-lang en ../../Swedish/swedish-a2/swedish-a2/swedish_a2App.swift --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Keep this list in sync with JlingoLearningKit/Sources/JlingoLearningKit/Localization/AppLanguage.swift.
APP_LANGUAGES = [
    ("english", "en"),
    ("mandarinChinese", "zh-Hans"),
    ("hindi", "hi"),
    ("spanish", "es"),
    ("italian", "it"),
    ("arabic", "ar"),
    ("french", "fr"),
    ("finnish", "fi"),
    ("bengali", "bn"),
    ("portuguese", "pt"),
    ("russian", "ru"),
    ("urdu", "ur"),
    ("indonesian", "id"),
    ("german", "de"),
    ("japanese", "ja"),
    ("swahili", "sw"),
    ("marathi", "mr"),
    ("telugu", "te"),
    ("turkish", "tr"),
    ("tamil", "ta"),
    ("yueChinese", "yue-Hant"),
    ("vietnamese", "vi"),
    ("serboCroatian", "sh"),
    ("hungarian", "hu"),
    ("polish", "pl"),
    ("bulgarian", "bg"),
]

LOCALIZATION_FIELDS = [
    "appNameLocalizations",
    "appTaglineLocalizations",
    "languageNameLocalizations",
]

DEFAULT_VALUE_FIELDS = {
    "appNameLocalizations": "appName",
    "appTaglineLocalizations": "appTagline",
    "languageNameLocalizations": "languageName",
}

# Google Translate API language codes do not always match the app locale keys.
GOOGLE_CODES = {
    "zh-Hans": "zh-CN",
    "yue-Hant": "yue",
    # Google no longer exposes Serbo-Croatian directly here. Croatian is the
    # closest Latin-script fallback for the app's historical "sh" key.
    "sh": "hr",
}


@dataclass(frozen=True)
class AppLanguage:
    case_name: str
    raw_value: str

    @property
    def google_code(self) -> str:
        return GOOGLE_CODES.get(self.raw_value, self.raw_value)


SUPPORTED_LANGUAGES = [AppLanguage(case_name, raw_value) for case_name, raw_value in APP_LANGUAGES]
LANGUAGE_BY_CASE = {language.case_name: language for language in SUPPORTED_LANGUAGES}
LANGUAGE_BY_RAW = {language.raw_value: language for language in SUPPORTED_LANGUAGES}


class TranslationError(RuntimeError):
    pass


class TranslationProgress:
    def __init__(self, total: int) -> None:
        self.current = 0
        self.total = total

    def log(self, text: str, source: AppLanguage, target: AppLanguage) -> None:
        self.current += 1
        print(
            f"[{self.current}/{self.total}] translating {text!r} "
            f"from .{source.case_name} to .{target.case_name}",
            flush=True,
        )

    def log_result(self, result: str) -> None:
        print(f"[{self.current}/{self.total}]\tresult: {result!r}", flush=True)

    def log_error(
        self,
        text: str,
        source: AppLanguage,
        target: AppLanguage,
        attempt: int,
        retries: int,
        error: Exception,
    ) -> None:
        print(
            f"[{self.current}/{self.total}] ERROR translating {text!r} "
            f"from .{source.case_name} to .{target.case_name} "
            f"(attempt {attempt}/{retries}): {error}",
            file=sys.stderr,
            flush=True,
        )


def normalize_source_language(value: str) -> AppLanguage:
    trimmed = value.strip().lstrip(".")
    if trimmed in LANGUAGE_BY_CASE:
        return LANGUAGE_BY_CASE[trimmed]
    if trimmed in LANGUAGE_BY_RAW:
        return LANGUAGE_BY_RAW[trimmed]
    raise TranslationError(
        f"unsupported source language {value!r}; use an AppLanguage case "
        "such as 'english' or a raw value such as 'en'"
    )


def swift_unescape(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"').replace("\\\\", "\\")


def swift_escape(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


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


def write_text_atomic(path: Path, text: str) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)


def write_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def cache_key(source: AppLanguage, target: AppLanguage, text: str) -> str:
    return json.dumps([source.google_code, target.google_code, text], ensure_ascii=False)


def request_translation(
    text: str,
    source: AppLanguage,
    target: AppLanguage,
    progress: TranslationProgress,
    retries: int = 4,
) -> str:
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": source.google_code,
        "tl": target.google_code,
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
                raise TranslationError(f"empty translation for {text!r} -> .{target.case_name}")
            time.sleep(0.06)
            return translated
        except Exception as exc:
            last_error = exc
            progress.log_error(text, source, target, attempt + 1, retries, exc)
            time.sleep(0.6 * (attempt + 1))

    raise TranslationError(f"translation failed for {text!r} -> .{target.case_name}: {last_error}")


def translate(
    text: str,
    source: AppLanguage,
    target: AppLanguage,
    cache: dict[str, str],
    cache_path: Path,
    dry_run: bool,
    progress: TranslationProgress,
) -> str:
    if source == target:
        return text
    progress.log(text, source, target)
    key = cache_key(source, target, text)
    if key in cache:
        result = cache[key]
    elif dry_run:
        result = f"[.{target.case_name}] {text}"
    else:
        result = request_translation(text, source, target, progress)
        cache[key] = result
        write_cache(cache_path, cache)
    progress.log_result(result)
    return result


def find_matching_bracket(text: str, open_index: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
    raise TranslationError("unterminated Swift dictionary literal")


def find_dictionary(text: str, field_name: str) -> tuple[int, int, str] | None:
    match = re.search(rf"\b{re.escape(field_name)}\s*:\s*\[", text)
    if not match:
        return None
    open_index = text.rfind("[", match.start(), match.end())
    close_index = find_matching_bracket(text, open_index)
    return open_index, close_index + 1, text[open_index + 1:close_index]


def parse_dictionary(body: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for match in re.finditer(r"\.([A-Za-z][A-Za-z0-9_]*)\s*:\s*\"((?:\\.|[^\"\\])*)\"", body):
        entries[match.group(1)] = swift_unescape(match.group(2))
    return entries


def find_default_value(text: str, default_field: str) -> str | None:
    match = re.search(rf"\b{re.escape(default_field)}\s*:\s*\"((?:\\.|[^\"\\])*)\"", text)
    return swift_unescape(match.group(1)) if match else None


def leading_indentation_before(text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    line_prefix = text[line_start:index]
    return re.match(r"[ \t]*", line_prefix).group(0)


def format_dictionary(entries: dict[str, str], indentation: str) -> str:
    item_indent = indentation + "    "
    lines = ["["]
    for language in SUPPORTED_LANGUAGES:
        value = entries[language.case_name]
        lines.append(f'{item_indent}.{language.case_name}: "{swift_escape(value)}",')
    lines.append(f"{indentation}]")
    return "\n".join(lines)


def resolve_swift_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.swift")))
        else:
            files.append(path)
    return files


def process_file(
    path: Path,
    source: AppLanguage,
    cache: dict[str, str],
    cache_path: Path,
    overwrite: bool,
    dry_run: bool,
    progress: TranslationProgress,
) -> int:
    original = path.read_text(encoding="utf-8")
    updated = original
    changed = 0

    for field_name in LOCALIZATION_FIELDS:
        found = find_dictionary(updated, field_name)
        if not found:
            continue

        start, end, body = found
        entries = parse_dictionary(body)
        default_value = find_default_value(updated, DEFAULT_VALUE_FIELDS[field_name])
        source_text = normalize_text(entries.get(source.case_name)) or normalize_text(default_value)
        if not source_text:
            raise TranslationError(f"{path}: {field_name} has no source value for .{source.case_name}")

        entries[source.case_name] = source_text
        for language in SUPPORTED_LANGUAGES:
            current = normalize_text(entries.get(language.case_name))
            if current and not overwrite:
                continue
            value = translate(source_text, source, language, cache, cache_path, dry_run, progress)
            if entries.get(language.case_name) != value:
                entries[language.case_name] = value
                changed += 1

        indentation = leading_indentation_before(updated, start)
        updated = updated[:start] + format_dictionary(entries, indentation) + updated[end:]

    if changed and not dry_run:
        write_text_atomic(path, updated)
    return changed


def count_missing_in_file(path: Path, source: AppLanguage, overwrite: bool) -> int:
    text = path.read_text(encoding="utf-8")
    total = 0
    for field_name in LOCALIZATION_FIELDS:
        found = find_dictionary(text, field_name)
        if not found:
            continue
        _start, _end, body = found
        entries = parse_dictionary(body)
        if source.case_name not in entries and not find_default_value(text, DEFAULT_VALUE_FIELDS[field_name]):
            raise TranslationError(f"{path}: {field_name} has no source value for .{source.case_name}")
        total += sum(
            1
            for language in SUPPORTED_LANGUAGES
            if language != source and (overwrite or not normalize_text(entries.get(language.case_name)))
        )
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate missing AppConfig localization dictionaries in Swift files.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Swift App file(s) or directories containing Swift files.",
    )
    parser.add_argument(
        "--source-lang",
        required=True,
        help="Source AppLanguage case or raw value, e.g. english, en, french, fr.",
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
    source = normalize_source_language(args.source_lang)
    files = resolve_swift_files(args.paths)
    if not files:
        raise TranslationError("no Swift files found")

    cache = read_cache(args.cache)
    translation_total = sum(count_missing_in_file(path, source, args.overwrite) for path in files)
    progress = TranslationProgress(translation_total)

    total_changed = 0
    for path in files:
        changed = process_file(
            path,
            source,
            cache,
            args.cache,
            args.overwrite,
            args.dry_run,
            progress,
        )
        total_changed += changed
        action = "would update" if args.dry_run else "updated"
        print(f"{action} {changed} values in {path}")

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
