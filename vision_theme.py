#!/usr/bin/env python3
"""Generate a Memory Cat theme from one pet photo with GPT Image."""

from __future__ import annotations

import argparse
import base64
import os
import shutil
import sys
import tempfile
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

from import_theme import cut_background, fit_square, save_theme_frames, segments


MODEL = "gpt-image-2"
IMAGE_SIZE = "1536x1024"
DEFAULT_QUALITY = "medium"
QUALITY_CHOICES = ("low", "medium", "high")
FRAMES_DIR = Path(__file__).with_name("frames")
MIN_DETECTED_STAGES = 4
MAX_DETECTED_STAGES = 8

SHEET_PROMPT = """\
Use the attached photo as the identity reference and create a horizontal sprite sheet.
Preserve the distinctive fur color, markings, face, and ear shape of THIS exact pet.
Depict the same cat or dog six times from left to right in a charming sticker/cartoon style.
Keep all six full-body characters in the same pose, scale family, viewing angle, and art style.
Make the body grow progressively fatter from left to right: character 1 is slim, character 2
is slightly plump, character 3 is chubby, character 4 is very chubby, character 5 is round,
and character 6 is extremely round. Use a pure white background and clear white space between
every character. Show exactly one horizontal row. no text, no labels, no watermark, no borders.
"""

RETRY_PROMPT = """\
exactly 6 clearly separated cats with wide white gaps between them. Keep every character fully
separate with no touching, overlap, props, shadows connecting characters, or extra figures.
"""

_GENERATION_QUALITY = ContextVar(
    "vision_theme_generation_quality", default=DEFAULT_QUALITY
)


class ThemeGenerationError(RuntimeError):
    """A user-facing failure while generating or processing a pet theme."""


def _one_line(value: object) -> str:
    return " ".join(str(value).split())


def generate_sheet(photo_path, retry_prompt=False) -> Image.Image:
    """Generate one horizontal pet sprite sheet from ``photo_path``."""
    photo = Path(photo_path).expanduser()
    if not photo.is_file():
        raise ThemeGenerationError(f"Pet photo not found: {photo}")

    load_dotenv(Path(__file__).with_name(".env"), override=False)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ThemeGenerationError(
            "OPENAI_API_KEY is missing; add it to the project's .env file."
        )

    prompt = SHEET_PROMPT
    if retry_prompt:
        prompt = f"{prompt}\n{RETRY_PROMPT}"

    try:
        client = OpenAI(api_key=api_key, timeout=180.0, max_retries=1)
        with photo.open("rb") as photo_file:
            response = client.images.edit(
                model=MODEL,
                image=photo_file,
                prompt=prompt,
                size=IMAGE_SIZE,
                quality=_GENERATION_QUALITY.get(),
                response_format="b64_json",
            )
        data = response.data or []
        encoded = data[0].b64_json if data else None
        if not encoded:
            raise ValueError("the API returned no image data")
        image_bytes = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(image_bytes)) as image:
            return image.copy()
    except ThemeGenerationError:
        raise
    except Exception as exc:
        raise ThemeGenerationError(
            f"OpenAI image generation failed: {_one_line(exc)}"
        ) from exc


def _theme_target(theme_name: str) -> Path:
    name = str(theme_name).strip()
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ThemeGenerationError(
            "Theme name must be one folder name without path separators."
        )
    target = FRAMES_DIR / name
    if target.is_symlink():
        raise ThemeGenerationError(
            f"Theme folder cannot be a symbolic link: {target}"
        )
    if target.exists():
        unexpected = [
            item
            for item in target.iterdir()
            if not (
                item.is_file()
                and item.name.startswith("_raw")
                and item.suffix.lower() == ".png"
            )
        ]
        if unexpected:
            raise ThemeGenerationError(
                f"Theme already exists and will not be overwritten: {target}"
            )
    return target


def _prepare_stages(sheet: Image.Image):
    with tempfile.TemporaryDirectory(prefix="memory-cat-sheet-") as temp_dir:
        sheet_path = Path(temp_dir) / "sheet.png"
        sheet.save(sheet_path, format="PNG")
        full, alpha = cut_background(sheet_path)
        detected = segments(alpha)

    stages = []
    for x0, x1 in detected:
        bounds = Image.fromarray(alpha[:, x0:x1]).getbbox()
        if bounds is None:
            continue
        _, y0, _, y1 = bounds
        stages.append(fit_square(full.crop((x0, y0, x1, y1))))
    return detected, stages


def _publish_theme(target: Path, sheet: Image.Image, stages) -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    staging_root = FRAMES_DIR / ".building"
    staging_root.mkdir(exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f"{target.name}-", dir=staging_root)
    )
    try:
        save_theme_frames(stages, staging)
        sheet.save(staging / "_raw.png", format="PNG")

        if target.exists():
            for previous in target.iterdir():
                destination = staging / previous.name
                if destination.exists():
                    destination = staging / f"_previous_{previous.name.lstrip('_')}"
                os.replace(previous, destination)
            target.rmdir()
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        try:
            staging_root.rmdir()
        except OSError:
            pass


def _save_failed_raws(target: Path, attempts) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if len(attempts) > 1:
        attempts[0].save(target / "_raw_attempt1.png", format="PNG")
    attempts[-1].save(target / "_raw.png", format="PNG")


def build_theme(photo_path, theme_name, quality=DEFAULT_QUALITY) -> dict:
    """Generate, validate, and publish one complete custom pet theme."""
    if quality not in QUALITY_CHOICES:
        raise ThemeGenerationError(
            f"Invalid quality '{quality}'; choose low, medium, or high."
        )
    target = _theme_target(theme_name)
    attempts = []
    detected_counts = []
    quality_token = _GENERATION_QUALITY.set(quality)
    try:
        for retry_prompt in (False, True):
            sheet = generate_sheet(photo_path, retry_prompt=retry_prompt)
            attempts.append(sheet)
            detected, stages = _prepare_stages(sheet)
            detected_count = len(detected)
            detected_counts.append(detected_count)
            if MIN_DETECTED_STAGES <= detected_count <= MAX_DETECTED_STAGES:
                _publish_theme(target, sheet, stages)
                return {
                    "detected_stages": detected_count,
                    "output_path": str(target),
                }
    finally:
        _GENERATION_QUALITY.reset(quality_token)

    _save_failed_raws(target, attempts)
    counts = ", ".join(str(count) for count in detected_counts)
    raise ThemeGenerationError(
        "Sprite segmentation failed after one retry: "
        f"detected {counts} stage(s), expected 4 to 8. "
        f"Raw image(s) were saved in {target}."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a 40-frame Memory Cat theme from one pet photo."
    )
    parser.add_argument("photo_path", help="Path to one cat or dog photo")
    parser.add_argument("theme_name", help="New theme folder name")
    parser.add_argument(
        "--quality",
        choices=QUALITY_CHOICES,
        default=DEFAULT_QUALITY,
        help="GPT Image quality (default: medium)",
    )
    args = parser.parse_args(argv)

    try:
        result = build_theme(args.photo_path, args.theme_name, args.quality)
    except (ThemeGenerationError, OSError, ValueError) as exc:
        print(f"Error: {_one_line(exc)}", file=sys.stderr)
        return 1

    print(
        f"Created theme '{args.theme_name}' with "
        f"{result['detected_stages']} detected stages: {result['output_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
