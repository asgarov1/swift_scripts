#!/usr/bin/env python3
"""
Translate an English word or phrase into all supported AppLanguage localizations.

Examples:
  python3 translate_phrase.py "good morning"
  python3 translate_phrase.py --source-lang en "good morning"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from translate_appconfig import (
    AppLanguage,
    TranslationError,
    read_cache,
    normalize_source_language,
    translate,
    write_cache,
    SUPPORTED_LANGUAGES,
)


class QuietProgress:
    def log(self, text: str, source: AppLanguage, target: AppLanguage) -> None:
        return None

    def log_result(self, result: str) -> None:
        return None

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
            f"ERROR translating {text!r} from .{source.case_name} "
            f"to .{target.case_name} (attempt {attempt}/{retries}): {error}",
            file=sys.stderr,
            flush=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate a word or phrase into every supported AppLanguage localization.",
    )
    parser.add_argument(
        "text",
        help="English word or phrase to translate. Quote it when calling the script directly.",
    )
    parser.add_argument(
        "--source-lang",
        default="english",
        help="Source AppLanguage case or raw value. Default: english.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("scripts/generated/translation_cache.json"),
        help="Persistent JSON cache path. Default: scripts/generated/translation_cache.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON object keyed by AppLanguage case instead of aligned text.",
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Include the source language in the printed results.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = args.text.strip()
    if not text:
        raise TranslationError("text cannot be empty")

    source = normalize_source_language(args.source_lang)
    cache = read_cache(args.cache)
    progress = QuietProgress()

    results: dict[str, dict[str, str]] = {}
    output_languages = [
        language
        for language in SUPPORTED_LANGUAGES
        if args.include_source or language != source
    ]

    for language in output_languages:
        translated = (
            text
            if language == source
            else translate(text, source, language, cache, args.cache, False, progress)
        )
        results[language.case_name] = {
            "locale": language.raw_value,
            "text": translated,
        }

    write_cache(args.cache, cache)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    longest_name = max(len(language.case_name) for language in output_languages)
    longest_locale = max(len(language.raw_value) for language in output_languages)
    for language in output_languages:
        result = results[language.case_name]
        print(
            f"{language.case_name.ljust(longest_name)} "
            f"({result['locale'].ljust(longest_locale)}): {result['text']}"
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TranslationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
