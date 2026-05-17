#!/usr/bin/env python3
"""
Generate pronunciation audio clips for every line in `input.txt` using
Microsoft's edge-tts (offline, no API key required).

Usage:

    pip install edge-tts
    python3 generate_audio_clips.py --lang it
    python3 generate_audio_clips.py --lang de
    python3 generate_audio_clips.py --voice it-IT-IsabellaNeural

Pass `--lang` (one of `de`, `es`, `fr`, `it`) to pick a voice
for that language. `--voice` overrides the per-language default if set.

By default the script reads `input.txt` next to itself and writes clips into
`output/` next to itself. Override either with `--input` / `--out`.

Each non-empty line of `input.txt` is treated as one phrase. The output
filename is the phrase with runs of whitespace replaced by `_`, plus the
chosen extension (default `.mp3`). Case and punctuation are preserved, which
matches the lookup convention used by `PronunciationPlayer` in
JlingoLearningKit.

Lines containing `/` mark an alternative gender/number form (e.g.
`Mi sono perso/a.` or `il professore / la professoressa`). The `/` is
replaced with a space before synthesis and filename derivation, so both
forms are read aloud and survive in the clip name.

This script is a thin variant of `blindfoldChess/generate_audio_clips.py` —
it shares the TTS plumbing but reads its manifest from a text file rather
than building it from move/template tables.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Iterable

# Friendly female voices per language. All have the "Friendly, Positive" style
# in Microsoft's edge-tts voice catalog.
#
# ┌────────┬──────────────────────┬────────┬────────────────────┐
# │  Lang  │        Voice         │ Gender │       Style        │
# ├────────┼──────────────────────┼────────┼────────────────────┤
# │  de    │ de-DE-KatjaNeural    │ Female │ Friendly, Positive │
# │  es    │ es-ES-ElviraNeural   │ Female │ Friendly, Positive │
# │  fr    │ fr-FR-DeniseNeural   │ Female │ Friendly, Positive │
# │  it    │ it-IT-ElsaNeural     │ Female │ Friendly, Positive │
# └────────┴──────────────────────┴────────┴────────────────────┘

LANG_VOICES: dict[str, str] = {
    "de": "de-DE-AmalaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "it": "it-IT-ElsaNeural",
}

DEFAULT_LANG = "it"
DEFAULT_RATE = "-8%"      # slightly slower — easier for learners to follow
DEFAULT_VOLUME = "+5%"
DEFAULT_PITCH = "-2Hz"
DEFAULT_EXT = "mp3"

WHITESPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]")

# Matches a verb conjugation line: an Italian infinitive (-are/-ere/-ire),
# a separator (`→` or `...`), then six comma-separated conjugated forms.
# Example: `capire...... capisco, capisci, capisce, capiamo, capite, capiscono`
VERB_CONJUGATION_RE = re.compile(
    r"^\s*(\S+(?:are|ere|ire))\s*(?:\.{2,}|→)\s*"
    r"[^\s,]+(?:\s*,\s*[^\s,]+){5}\s*$"
)


def expand_slashes(phrase: str) -> str:
    """Replace `/` with a space so both gender/number forms are kept.

    - `Mi sono perso/a.`          -> `Mi sono perso a.`
    - `Sono andato/a al mercato.` -> `Sono andato a al mercato.`
    - `il professore / la professoressa` -> `il professore la professoressa`
    """
    return WHITESPACE_RE.sub(" ", phrase.replace("/", " ")).strip()


def filename_base(foreign: str) -> str:
    """Lowercase, strip every punctuation character, collapse whitespace to `_`.

    Filenames contain only letters (including accented Italian letters like
    `à`/`è`), digits, and underscores — everything else (`.`, `,`, `!`, `?`,
    `'`, `→`, …) is dropped. Lookups must use the same convention.
    """
    cleaned = PUNCT_RE.sub("", foreign.lower())
    return WHITESPACE_RE.sub("_", cleaned.strip())


def verb_infinitive(line: str) -> str | None:
    """Return the infinitive if `line` is a six-form verb conjugation, else None.

    Conjugation lines are saved as `<infinitive>.mp3` so the clip name matches
    the dictionary entry, while the synthesised audio still reads out the full
    paradigm.
    """
    m = VERB_CONJUGATION_RE.match(line)
    return m.group(1).lower() if m else None


def read_input(path: Path) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = expand_slashes(line)
            if not line or line in seen:
                continue
            seen.add(line)
            phrases.append(line)
    return phrases


async def synthesize_one(text: str, out_path: Path, voice: str,
                         rate: str, volume: str, pitch: str) -> None:
    # Imported lazily so `--dry-run` works without the dependency installed.
    import edge_tts  # type: ignore

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
    )
    await communicate.save(str(out_path))


async def run(args: argparse.Namespace) -> int:
    phrases = read_input(args.input)
    if not phrases:
        print(f"No phrases found in {args.input}", file=sys.stderr)
        return 1

    voice = args.voice or LANG_VOICES[args.lang]

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = args.ext.lstrip(".")
    generated = 0
    skipped_existing = 0
    failed: list[str] = []

    print(f"Manifest: {len(phrases)} phrases -> {out_dir} (.{ext}, lang={args.lang}, voice={voice})")

    for phrase in phrases:
        # Verb-conjugation detection is Italian-specific (matches -are/-ere/-ire).
        infinitive = verb_infinitive(phrase) if args.lang == "it" else None
        base = infinitive if infinitive else filename_base(phrase)
        if not base:
            continue
        out_path = out_dir / f"{base}.{ext}"
        if out_path.exists() and not args.overwrite:
            skipped_existing += 1
            continue
        if args.dry_run:
            print(f"  + dry  {base}.{ext}  <- {phrase!r}")
            continue
        print(f"  + make {base}.{ext}  <- {phrase!r}")
        try:
            await synthesize_one(
                text=phrase,
                out_path=out_path,
                voice=voice,
                rate=args.rate,
                volume=args.volume,
                pitch=args.pitch,
            )
            generated += 1
        except Exception as exc:  # pragma: no cover
            print(f"    ! failed: {exc}", file=sys.stderr)
            failed.append(phrase)
            if out_path.exists():
                out_path.unlink()  # don't leave partial files

    print(
        f"Done. generated={generated} "
        f"skipped_existing={skipped_existing} "
        f"failed={len(failed)}"
    )
    if failed:
        print("Failed phrases:")
        for f in failed:
            print(f"  - {f!r}")
        return 2
    return 0


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir / "input.txt"

    # NB: use argparse's `%(default)s` rather than f-strings — defaults contain
    # literal `%` (e.g. "-8%") which Python's argparse formats eagerly.
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", type=Path, default=default_input,
                   help="Path to the text file of phrases (one per line).")
    p.add_argument("--out", type=Path, default=script_dir / "output",
                   help="Output directory for the generated audio clips.")
    p.add_argument("--lang", choices=sorted(LANG_VOICES), default=DEFAULT_LANG,
                   help="Target language; picks a friendly female voice. "
                        "One of: " + ", ".join(
                            f"{c}={v}" for c, v in sorted(LANG_VOICES.items())
                        ) + ".")
    p.add_argument("--voice", default=None,
                   help="edge-tts voice id. Overrides --lang when set. "
                        "See `edge-tts --list-voices`.")
    p.add_argument("--rate", default=DEFAULT_RATE,
                   help="Speech rate adjustment.")
    p.add_argument("--volume", default=DEFAULT_VOLUME,
                   help="Volume adjustment.")
    p.add_argument("--pitch", default=DEFAULT_PITCH,
                   help="Pitch adjustment.")
    p.add_argument("--ext", default=DEFAULT_EXT,
                   help="File extension to write (mp3 is what edge-tts produces).")
    p.add_argument("--overwrite", action="store_true",
                   help="Re-generate even if the clip file already exists.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the planned filenames without calling edge-tts.")
    return p.parse_args(list(argv) if argv is not None else None)


def main() -> int:
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
