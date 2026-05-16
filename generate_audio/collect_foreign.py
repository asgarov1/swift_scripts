#!/usr/bin/env python3
"""
Walk every `*.json` file in a given folder and collect the string value of
each `foreign` or `infinitive` key (at any nesting depth) into a single
`input.txt`, ready for feeding into `generate_audio_clips.py`.

Usage:

    python3 collect_foreign.py /path/to/app_folder
    python3 collect_foreign.py /path/to/app_folder --output input.txt

The walker descends into nested objects and arrays, so it also picks up
`foreign` values inside grammar examples or any other nested structure. The
output preserves first-seen order and deduplicates exact-match phrases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator

WHITESPACE_RE = re.compile(r"\s+")


def replace_verb_arrow(phrase: str) -> str:
    """Replace ` → ` with `...... ` when the RHS is a conjugation list.

    A conjugation entry looks like `infinitive → form1, form2, ...`. The
    comma-separated RHS distinguishes it from singular/plural noun pairs
    (`libro → libri`) and example sentences (`Vedo il film. → Lo vedo.`),
    which should keep the arrow.
    """
    if " → " not in phrase:
        return phrase
    lhs, _, rhs = phrase.partition(" → ")
    if "," not in rhs:
        return phrase
    return f"{lhs}...... {rhs}"


def expand_slashes(phrase: str) -> str:
    """Replace every `/` with a space so both gender/number forms are read out.

    `Mi sono perso/a.`              -> `Mi sono perso a.`
    `il professore / la professoressa` -> `il professore la professoressa`
    """
    return WHITESPACE_RE.sub(" ", phrase.replace("/", " ")).strip()


def iter_foreign(node: object) -> Iterator[str]:
    """Yield every `foreign` or `infinitive` string value found inside `node`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("foreign", "infinitive") and isinstance(value, str):
                yield expand_slashes(replace_verb_arrow(value))
            else:
                yield from iter_foreign(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_foreign(item)


def collect(folder: Path) -> tuple[list[str], list[Path]]:
    json_files = sorted(folder.rglob("*.json"))
    seen: set[str] = set()
    out: list[str] = []
    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"warning: {path}: {exc}", file=sys.stderr)
            continue
        for foreign in iter_foreign(data):
            phrase = foreign.strip()
            if not phrase or phrase in seen:
                continue
            seen.add(phrase)
            out.append(phrase)
    return out, json_files


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("folder", type=Path,
                   help="Folder to scan recursively for JSON files.")
    p.add_argument("--output", "-o", type=Path,
                   default=Path(__file__).resolve().parent / "input.txt",
                   help="Where to write the collected phrases.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.folder.is_dir():
        print(f"error: not a directory: {args.folder}", file=sys.stderr)
        return 1

    phrases, files = collect(args.folder)
    if not phrases:
        print(f"No `foreign` or `infinitive` keys found in {args.folder}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(phrases) + "\n", encoding="utf-8")
    print(f"Scanned {len(files)} JSON file(s); wrote {len(phrases)} phrases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
