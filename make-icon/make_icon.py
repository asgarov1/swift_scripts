#!/Users/asgarov1/Projects/swift/scripts/make-icon/venv/bin/python3
"""Render text over an image and install the result as an iconset in Assets.xcassets.

Example:
    python3 scripts/make_icon.py \
        --input spanish-a1/Flag-Spain_1024.jpeg \
        --icon-set AppIcon \
        --color white \
        --opacity 0.8 \
        --text '{"text":"A1","x":512,"y":820,"font":"/path/to/font.ttf","font_size":260,"anchor":"mm"}' \
        --text '{"text":"ES","x":512,"y":260,"font":"/path/to/another-font.otf","font_size":200,"color":"#FFCC00","opacity":0.5}'

Or with a JSON file containing a list of the same objects:
    python3 scripts/make_icon.py -i flag.jpg --config icon_text.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

DEFAULT_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
]
DARKEN_FACTOR = 0.55
CSV_FIELDS = (
    "text",
    "x",
    "y",
    "font",
    "font_size",
    "color",
    "anchor",
    "weight",
    "angle",
    "opacity",
)
MIN_MAKE_CSV_FIELDS = 8
DEFAULT_ICON_SIZE = 1024


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    if path and not Path(path).is_file():
        raise FileNotFoundError(f"Font file not found: {path}")
    candidates = [path] if path else DEFAULT_FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def adjust_color_brightness(color: str | tuple | list, factor: float) -> tuple[int, int, int, int]:
    if isinstance(color, (tuple, list)):
        red, green, blue, *alpha = color
        return (
            int(red * factor),
            int(green * factor),
            int(blue * factor),
            int(alpha[0]) if alpha else 255,
        )
    red, green, blue, alpha = ImageColor.getcolor(color, "RGBA")
    return (int(red * factor), int(green * factor), int(blue * factor), alpha)


def parse_opacity(value: object) -> float:
    """Return an opacity multiplier in the inclusive range 0.0 to 1.0."""
    try:
        opacity = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Opacity must be a number from 0.0 to 1.0, got {value!r}") from exc
    if not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
        raise ValueError(f"Opacity must be from 0.0 to 1.0, got {value!r}")
    return opacity


def apply_opacity(color: str | tuple | list, opacity: float) -> tuple[int, int, int, int]:
    """Apply opacity while preserving any alpha already present in the color."""
    if isinstance(color, (tuple, list)):
        red, green, blue, *alpha = color
        color_alpha = int(alpha[0]) if alpha else 255
    else:
        red, green, blue, color_alpha = ImageColor.getcolor(color, "RGBA")
    return (int(red), int(green), int(blue), round(color_alpha * opacity))


def draw_text(
    draw: ImageDraw.ImageDraw,
    spec: dict,
    default_color: str,
    default_weight: int,
    default_opacity: float,
    color_transform: Callable[[str | tuple | list], str | tuple | list] | None = None,
) -> None:
    text = spec["text"]
    x = int(spec.get("x", 0))
    y = int(spec.get("y", 0))
    font = load_font(spec.get("font"), int(spec.get("font_size", 72)))
    fill = spec.get("color", default_color)
    if color_transform:
        fill = color_transform(fill)
    opacity = parse_opacity(spec.get("opacity", default_opacity))
    fill = apply_opacity(fill, opacity)
    # "weight" thickens the glyph in its own fill color. "stroke_width" is a
    # legacy alias. If "stroke_color" is set, it's treated as a real outline.
    weight = int(spec.get("weight", spec.get("stroke_width", default_weight)))
    kwargs = dict(font=font, fill=fill, anchor=spec.get("anchor", "la"))
    if weight > 0:
        kwargs["stroke_width"] = weight
        stroke_fill = spec.get("stroke_color", fill)
        if color_transform and "stroke_color" in spec:
            stroke_fill = color_transform(stroke_fill)
        if "stroke_color" in spec:
            stroke_fill = apply_opacity(stroke_fill, opacity)
        kwargs["stroke_fill"] = stroke_fill
    draw.text((x, y), text, **kwargs)


def text_angle(spec: dict) -> float:
    """Return clockwise text rotation degrees for a text spec."""
    raw = spec.get("angle", spec.get("degrees", 0))
    if raw in ("", None):
        return 0.0
    return float(raw)


def darken(base: Image.Image, factor: float = DARKEN_FACTOR) -> Image.Image:
    """Darken the image for the dark-mode icon variant."""
    alpha = base.split()[-1]
    out = ImageEnhance.Brightness(base.convert("RGB")).enhance(factor).convert("RGBA")
    out.putalpha(alpha)
    return out


def grayscale(base: Image.Image) -> Image.Image:
    """Convert to grayscale for the tinted icon variant. iOS applies the user's
    chosen tint color over the luminance values."""
    alpha = base.split()[-1]
    out = ImageOps.grayscale(base.convert("RGB")).convert("RGBA")
    out.putalpha(alpha)
    return out


def normalize_icon_image(input_path: Path, canvas_size: int) -> Image.Image:
    """Scale and center-crop the source image to the square icon canvas."""
    img = Image.open(input_path).convert("RGBA")
    target_size = (canvas_size, canvas_size)
    if img.size == target_size:
        return img
    return ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def has_shadow(spec: dict) -> bool:
    return any(key in spec for key in ("shadow", "shadow_color", "shadow_blur", "shadow_dx", "shadow_dy"))


def draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    spec: dict,
    default_weight: int,
    color_transform: Callable[[str | tuple | list], str | tuple | list] | None = None,
) -> None:
    shadow_color = spec.get("shadow_color", "black")
    if color_transform:
        shadow_color = color_transform(shadow_color)
    shadow_opacity = parse_opacity(spec.get("shadow_opacity", 0.35))
    fill = apply_opacity(shadow_color, shadow_opacity)
    x = int(spec.get("x", 0)) + int(spec.get("shadow_dx", 0))
    y = int(spec.get("y", 0)) + int(spec.get("shadow_dy", 10))
    font = load_font(spec.get("font"), int(spec.get("font_size", 72)))
    kwargs = dict(font=font, fill=fill, anchor=spec.get("anchor", "la"))
    weight = int(spec.get("weight", spec.get("stroke_width", 0)))
    if weight > 0:
        kwargs["stroke_width"] = weight
        kwargs["stroke_fill"] = fill
    draw.text((x, y), spec["text"], **kwargs)


def render_text_overlay(
    size: tuple[int, int],
    specs: list[dict],
    default_color: str,
    default_weight: int,
    default_opacity: float,
    color_transform: Callable[[str | tuple | list], str | tuple | list] | None = None,
) -> Image.Image:
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    for spec in specs:
        item = Image.new("RGBA", size, (0, 0, 0, 0))
        if has_shadow(spec):
            shadow_layer = Image.new("RGBA", size, (0, 0, 0, 0))
            draw_shadow_text(ImageDraw.Draw(shadow_layer), spec, default_weight, color_transform)
            blur = float(spec.get("shadow_blur", 12))
            if blur > 0:
                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
            item = Image.alpha_composite(item, shadow_layer)
        draw_text(ImageDraw.Draw(item), spec, default_color, default_weight, default_opacity, color_transform)
        angle = text_angle(spec)
        if angle:
            item = item.rotate(
                -angle,
                resample=Image.Resampling.BICUBIC,
                center=(int(spec.get("x", 0)), int(spec.get("y", 0))),
            )
        overlay = Image.alpha_composite(overlay, item)
    return overlay


def render_variants(
    input_path: Path,
    specs: list[dict],
    canvas_size: int,
    default_color: str,
    default_weight: int,
    default_opacity: float,
) -> dict[str, Image.Image]:
    img = normalize_icon_image(input_path, canvas_size)
    overlay = render_text_overlay(img.size, specs, default_color, default_weight, default_opacity)
    dark_overlay = render_text_overlay(
        img.size,
        specs,
        default_color,
        default_weight,
        default_opacity,
        lambda color: adjust_color_brightness(color, DARKEN_FACTOR),
    )
    return {
        "light": Image.alpha_composite(img, overlay),
        "dark": Image.alpha_composite(darken(img), dark_overlay),
        "tinted": Image.alpha_composite(grayscale(img), overlay),
    }


def write_icons(
    variants: dict[str, Image.Image], assets_dir: Path, icon_set: str, fallback_dir: Path
) -> Path:
    """Write the three icon variants. If ``assets_dir`` is a real .xcassets
    directory, install them as an iconset (with Contents.json). Otherwise drop
    the PNGs into ``fallback_dir`` with no Contents.json."""
    filenames = {
        "light": f"{icon_set}.png",
        "dark": f"{icon_set}-Dark.png",
        "tinted": f"{icon_set}-Tinted.png",
    }

    if assets_dir.is_dir():
        out_dir = assets_dir / f"{icon_set}.appiconset"
        out_dir.mkdir(parents=True, exist_ok=True)
        contents = {
            "images": [
                {
                    "filename": filenames["light"],
                    "idiom": "universal",
                    "platform": "ios",
                    "size": "1024x1024",
                },
                {
                    "appearances": [{"appearance": "luminosity", "value": "dark"}],
                    "filename": filenames["dark"],
                    "idiom": "universal",
                    "platform": "ios",
                    "size": "1024x1024",
                },
                {
                    "appearances": [{"appearance": "luminosity", "value": "tinted"}],
                    "filename": filenames["tinted"],
                    "idiom": "universal",
                    "platform": "ios",
                    "size": "1024x1024",
                },
            ],
            "info": {"author": "xcode", "version": 1},
        }
        (out_dir / "Contents.json").write_text(json.dumps(contents, indent=2) + "\n")
    else:
        out_dir = fallback_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    for key in ("light", "dark", "tinted"):
        variants[key].convert("RGB").save(out_dir / filenames[key], format="PNG")
    return out_dir


def collect_specs(args: argparse.Namespace) -> list[dict]:
    specs: list[dict] = []
    if args.config:
        data = json.loads(Path(args.config).read_text())
        if not isinstance(data, list):
            raise ValueError("--config must point to a JSON list of text specs")
        specs.extend(data)
    for raw in args.text or []:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            specs.extend(parsed)
        else:
            specs.append(parsed)
    for raw in args.csv or []:
        specs.append(parse_csv_spec(raw))
    if args.csv_goals:
        specs.extend(parse_csv_goal_specs(args.csv_goals))
    return specs


def parse_csv_spec(raw: str) -> dict:
    values = next(csv.reader([raw], skipinitialspace=True))
    if len(values) > len(CSV_FIELDS):
        raise ValueError(
            f"CSV text spec has {len(values)} fields; expected at most {len(CSV_FIELDS)}: {raw}"
        )
    spec = {field: value for field, value in zip(CSV_FIELDS, values) if value != ""}
    if not spec.get("text"):
        raise ValueError(f"CSV text spec must start with text: {raw}")
    return spec


def parse_csv_goal_specs(raw: str) -> list[dict]:
    """Rebuild CSV specs after make splits goals that contain spaces."""
    specs: list[dict] = []
    parts: list[str] = []
    for token in raw.split():
        parts.append(token)
        candidate = " ".join(parts)
        if len(next(csv.reader([candidate], skipinitialspace=True))) >= MIN_MAKE_CSV_FIELDS:
            specs.append(parse_csv_spec(candidate))
            parts = []
    if parts:
        specs.append(parse_csv_spec(" ".join(parts)))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", "-i", required=True, type=Path, help="Source image.")
    parser.add_argument(
        "--assets",
        type=Path,
        default=Path("spanish-a1/Assets.xcassets"),
        help="Path to the .xcassets directory.",
    )
    parser.add_argument("--icon-set", default="AppIcon", help="Iconset name (without .appiconset).")
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_ICON_SIZE,
        help="Output square size in pixels.",
    )
    parser.add_argument(
        "--color",
        default="white",
        help="Default text fill color (name or #RRGGBB). Per-text 'color' in a spec overrides.",
    )
    parser.add_argument(
        "--weight",
        type=int,
        default=0,
        help="Default glyph thickness in pixels (0 = regular). Per-text 'weight' in a spec overrides.",
    )
    parser.add_argument(
        "--opacity",
        type=parse_opacity,
        default=1.0,
        help="Default text opacity from 0.0 to 1.0. Per-text 'opacity' in a spec overrides.",
    )
    parser.add_argument(
        "--text",
        action="append",
        help='Inline text spec as JSON object, or a JSON array of specs. Repeatable.',
    )
    parser.add_argument(
        "--csv",
        action="append",
        help="Comma-separated text,x,y,font,font_size,color,anchor,weight,angle,opacity spec. Repeatable.",
    )
    parser.add_argument(
        "--csv-goals",
        help="Raw Makefile goal text containing one or more comma-separated specs.",
    )
    parser.add_argument("--config", type=Path, help="JSON file with a list of text specs.")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input image not found: {args.input}", file=sys.stderr)
        return 1

    specs = collect_specs(args)

    variants = render_variants(
        args.input, specs, args.size, args.color, args.weight, args.opacity
    )
    out_dir = write_icons(variants, args.assets, args.icon_set, fallback_dir=Path.cwd())
    if args.assets.is_dir():
        print(f"Wrote iconset: {out_dir}")
    else:
        print(f"Assets.xcassets not found at {args.assets} — wrote PNGs to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
