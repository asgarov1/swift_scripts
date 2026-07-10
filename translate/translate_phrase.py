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
    normalize_app_language,
    read_cache,
    normalize_source_language,
    translate,
    write_cache,
    SUPPORTED_LANGUAGES,
)


class PhraseProgress:
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self.current = 0

    def log(self, text: str, source: AppLanguage, target: AppLanguage) -> None:
        self.current += 1
        if not self.quiet:
            print(
                f"[{self.current}] translating {text!r} "
                f"from .{source.case_name} to .{target.case_name}",
                file=sys.stderr,
                flush=True,
            )

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
        "-t",
        "--target-lang",
        help="Translate only to this AppLanguage case or raw value, e.g. italian or it.",
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
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print per-language progress to stderr.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call the network; print placeholder translations.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Translation attempts per language. Default: 2.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8,
        help="Network timeout in seconds per translation attempt. Default: 8.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = args.text.strip()
    if not text:
        raise TranslationError("text cannot be empty")
    if args.retries < 1:
        raise TranslationError("--retries must be at least 1")
    if args.timeout <= 0:
        raise TranslationError("--timeout must be greater than 0")

    source = normalize_source_language(args.source_lang)
    target = normalize_app_language(args.target_lang, "target language") if args.target_lang else None
    cache = read_cache(args.cache)
    progress = PhraseProgress(args.quiet)

    results: dict[str, dict[str, str]] = {}
    if target:
        output_languages = [target]
    else:
        output_languages = [
            language
            for language in SUPPORTED_LANGUAGES
            if args.include_source or language != source
        ]

    for language in output_languages:
        translated = (
            text
            if language == source
            else translate(
                text,
                source,
                language,
                cache,
                args.cache,
                args.dry_run,
                progress,
                args.retries,
                args.timeout,
            )
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
