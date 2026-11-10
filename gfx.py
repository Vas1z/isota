"""Загрузка PNG для клиента с fallback через Pillow."""

from pathlib import Path
from typing import Optional

import pygame


def load_png(path) -> Optional[pygame.Surface]:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        try:
            from PIL import Image

            with Image.open(path) as pil_image:
                pil_image = pil_image.convert("RGBA")
                size = pil_image.size
                data = pil_image.tobytes()
            return pygame.image.fromstring(data, size, "RGBA").convert_alpha()
        except Exception:
            return None


def crop_alpha(image: Optional[pygame.Surface]) -> Optional[pygame.Surface]:
    if image is None:
        return None
    bounds = image.get_bounding_rect()
    if bounds.w > 0 and bounds.h > 0:
        return image.subsurface(bounds).copy()
    return image


def load_sprite(path, *, crop: bool = True) -> Optional[pygame.Surface]:
    image = load_png(path)
    return crop_alpha(image) if crop else image
