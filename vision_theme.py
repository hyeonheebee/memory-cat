#!/usr/bin/env python3
"""Generate a Memory Cat theme from one pet photo with GPT Image."""

from __future__ import annotations

import argparse
import base64
import contextlib
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
# 이미지 API 가 직접 받는 포맷. HEIC 는 여기 없어서 변환이 필요하다.
API_IMAGE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})
MIN_DETECTED_STAGES = 6
MAX_DETECTED_STAGES = 6

SHEET_PROMPT = """\
Use the attached photo as the identity reference and create a horizontal sprite sheet.
Preserve the distinctive fur color, markings, face, and ear shape of THIS exact pet.
Depict the same pet six times from left to right as a soft 3D toy figurine: smooth matte
vinyl surface, large simplified rounded forms, NO individual fur strands and no fine line
hatching, soft studio lighting with gentle rim light and soft shading on the body itself.
Chibi proportions: oversized round head, very large glossy dark eyes with two white
catchlights, tiny rounded paws, short stubby legs, small soft blush on the cheeks.
Keep the same character identity, three-quarter front-facing angle, and art style in all six.
Make the body grow fatter AND the pose grow lazier from left to right:
1 slim, sitting upright and tall, bright wide open eyes;
2 slightly plump, sitting, soft closed smile;
3 chubby, sitting low with legs tucked in, relaxed eyes;
4 very chubby, crouching down, half-closed sleepy eyes;
5 round, lying down as a flat loaf with front paws tucked, eyes nearly shut;
6 extremely round, melting flat and wide on the ground like a pancake, eyes fully closed in
a happy curve.
Each character must be clearly bigger and lower to the ground than the previous one, so the
silhouette changes from tall and narrow to short and wide.
Give every character a soft contour slightly darker than the background so the silhouette
stays readable even for white or cream fur.
Draw the characters large so they fill most of the image height.
Use a pure white background. Leave a wide empty white gap between neighboring
characters, at least half a character wide, so that no two characters ever touch or overlap.
Show exactly one horizontal row of exactly six characters, evenly spaced. no text, no labels, no watermark, no borders, no cast
shadow on the ground, nothing connecting two characters.
"""

RETRY_PROMPT = """\
exactly 6 clearly separated characters in one horizontal row, with wide pure white gaps
between them. Keep every character fully separate: no touching, no overlap, no props, no
ground shadow, no reflection, no extra figures, no partial characters cropped at the left or
right edge. The background must be uniform pure white #FFFFFF with no gradient, no texture,
and no off-white tint anywhere.
"""

def _expected_stages() -> str:
    """기대 단계 수를 상수에서 만들어 낸다. 메시지에 숫자를 따로 적으면 상수와 어긋난다."""
    if MIN_DETECTED_STAGES == MAX_DETECTED_STAGES:
        return f"exactly {MIN_DETECTED_STAGES}"
    return f"{MIN_DETECTED_STAGES} to {MAX_DETECTED_STAGES}"


_GENERATION_QUALITY = ContextVar(
    "vision_theme_generation_quality", default=DEFAULT_QUALITY
)


class ThemeGenerationError(RuntimeError):
    """A user-facing failure while generating or processing a pet theme."""


def _one_line(value: object) -> str:
    return " ".join(str(value).split())


def _is_api_ready(photo: Path) -> bool:
    """이미지 API 가 그대로 받아주는 포맷인지 내용으로 확인한다.

    확장자가 아니라 실제 포맷을 본다. 아이폰에서 내보낸 사진은 이름만
    ``.jpg`` 이고 내용은 HEIC 인 경우가 있다.
    """
    try:
        with Image.open(photo) as image:
            return image.format in API_IMAGE_FORMATS
    except Exception:
        return False


def _rewrite_as_jpeg(photo: Path, destination: Path) -> None:
    """macOS 이미지 디코더를 빌려 HEIC 등을 JPEG 로 옮긴다.

    Pillow 는 HEIC 를 열지 못하는데 아이폰 사진은 기본이 HEIC 다. macOS 는
    ImageIO 로 이미 읽을 수 있으므로, 새 의존성을 더하지 않고 AppKit 을
    가져다 쓴다. ``brain._trash_via_foundation`` 과 같은 지연 import 방식.
    """
    if sys.platform != "darwin":
        raise ThemeGenerationError(
            "This photo format can only be converted on macOS; "
            "use a PNG, JPEG, or WebP file instead."
        )

    from AppKit import (
        NSBitmapImageFileTypeJPEG,
        NSBitmapImageRep,
        NSImage,
        NSImageCompressionFactor,
    )

    image = NSImage.alloc().initWithContentsOfFile_(str(photo))
    if image is None:
        raise ThemeGenerationError(
            f"Could not read the photo: {photo.name}. "
            "Try a PNG, JPEG, or WebP file."
        )
    representation = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    data = None
    if representation is not None:
        data = representation.representationUsingType_properties_(
            NSBitmapImageFileTypeJPEG, {NSImageCompressionFactor: 0.9}
        )
    if not data:
        raise ThemeGenerationError(
            f"Could not convert the photo: {photo.name}. "
            "Try a PNG, JPEG, or WebP file."
        )
    destination.write_bytes(bytes(data))


@contextlib.contextmanager
def api_ready_photo(photo: Path):
    """업로드에 쓸 경로를 넘긴다. 필요할 때만 변환본을 만든다.

    이미 지원 포맷이면 원본을 그대로 올려 재인코딩 손실을 피한다.
    """
    if _is_api_ready(photo):
        yield photo
        return

    with tempfile.TemporaryDirectory(prefix="memory-cat-photo-") as temp_dir:
        converted = Path(temp_dir) / f"{photo.stem or 'photo'}.jpg"
        _rewrite_as_jpeg(photo, converted)
        yield converted


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
        with api_ready_photo(photo) as upload, upload.open("rb") as photo_file:
            response = client.images.edit(
                model=MODEL,
                image=photo_file,
                prompt=prompt,
                size=IMAGE_SIZE,
                quality=_GENERATION_QUALITY.get(),
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
        f"detected {counts} stage(s), expected {_expected_stages()}. "
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
