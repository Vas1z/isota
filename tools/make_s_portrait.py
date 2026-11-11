"""Рисует портрет S — теневого демона в духе Shadow Fiend, но оригинальный."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "heroes" / "s.png"

S = 3  # суперсэмплинг
W = 512 * S
INK = (22, 16, 26)
BODY = (58, 48, 66)
BODY_DARK = (38, 30, 46)
BODY_LIGHT = (100, 84, 112)
HORN = (52, 44, 56)
HORN_LIGHT = (98, 84, 100)
RED = (210, 52, 64)
ORANGE = (255, 142, 78)
SOUL = (255, 182, 128)
MEMBRANE = (124, 38, 58)


def sc(*values):
    return tuple(int(v * S) for v in values)


def sw(value: float) -> int:
    return max(1, int(value * S))


def mir(points):
    """Отражает точки относительно центра 256."""
    return [(512 - x, y) for x, y in points]


def poly(d, points, fill, width=5):
    d.polygon([sc(*p) for p in points], fill=fill, outline=INK, width=sw(width))


def main() -> None:
    img = Image.new("RGBA", (W, W), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)

    # Тень под демоном.
    d.ellipse(sc(158, 440, 370, 482), fill=(226, 224, 230, 255))

    # Крылья за спиной.
    left_wing = [(198, 258), (148, 206), (66, 138), (84, 214), (112, 226),
                 (52, 288), (108, 300), (72, 374), (144, 338), (158, 392),
                 (196, 318)]
    right_wing = mir(left_wing)
    poly(d, left_wing, BODY_DARK, 6)
    poly(d, right_wing, BODY_DARK, 6)

    # Перепонки крыльев.
    left_membrane = [(180, 264), (104, 210), (112, 250), (86, 292),
                     (126, 306), (112, 350), (166, 326)]
    poly(d, left_membrane, MEMBRANE, 3)
    poly(d, mir(left_membrane), MEMBRANE, 3)

    # Хвост.
    d.line(sc(300, 410, 372, 452, 404, 420), fill=INK, width=sw(12))
    d.line(sc(300, 410, 372, 452, 404, 420), fill=BODY, width=sw(6))
    poly(d, [(404, 420), (432, 432), (414, 446), (394, 434)], RED, 3)

    # Тело.
    body = [(196, 250), (316, 250), (340, 324), (322, 438), (190, 438), (172, 324)]
    poly(d, body, BODY, 6)
    d.polygon([sc(204, 274), sc(308, 274), sc(316, 414), sc(196, 414)],
              fill=BODY_DARK)

    # Нагрудный разлом с огнём.
    poly(d, [(238, 288), (274, 288), (286, 316), (270, 352), (242, 352),
             (226, 316)], (72, 22, 30), 3)
    poly(d, [(244, 300), (268, 300), (274, 318), (260, 338), (248, 326),
             (238, 314)], RED, 2)

    # Плечи и шипы.
    poly(d, [(176, 246), (136, 232), (112, 250), (168, 274)], BODY, 4)
    poly(d, [(336, 246), (376, 232), (400, 250), (344, 274)], BODY, 4)
    poly(d, [(122, 248), (100, 222), (146, 238)], HORN, 3)
    poly(d, [(390, 248), (412, 222), (366, 238)], HORN, 3)

    # Руки и когти.
    poly(d, [(178, 272), (132, 312), (118, 382), (158, 408), (180, 350)], BODY, 5)
    poly(d, [(334, 272), (380, 312), (394, 382), (354, 408), (332, 350)], BODY, 5)
    for side in (-1, 1):
        bx = 138 if side < 0 else 374
        for offset in (-16, 0, 16):
            d.line(sc(bx, 400, bx + side * 18, 438 + offset // 3),
                   fill=INK, width=sw(7))
            d.line(sc(bx, 400, bx + side * 18, 438 + offset // 3),
                   fill=HORN_LIGHT, width=sw(3))

    # Голова.
    d.ellipse(sc(184, 88, 328, 256), fill=BODY, outline=INK, width=sw(6))
    d.ellipse(sc(202, 112, 310, 246), fill=(76, 62, 84))

    # Уши.
    poly(d, [(186, 146), (150, 124), (176, 180)], BODY, 4)
    poly(d, [(326, 146), (362, 124), (336, 180)], BODY, 4)

    # Рога.
    left_horn = [(204, 120), (178, 104), (146, 58), (130, 24), (152, 30),
                 (178, 68), (200, 88), (220, 104)]
    poly(d, left_horn, HORN, 5)
    poly(d, mir(left_horn), HORN, 5)
    d.line(sc(190, 96, 150, 42), fill=HORN_LIGHT, width=sw(5))
    d.line(sc(322, 96, 362, 42), fill=HORN_LIGHT, width=sw(5))

    # Глаза.
    for eye in ((218, 158, 252, 184), (260, 158, 294, 184)):
        d.ellipse(sc(*eye), fill=(34, 6, 12))
        d.ellipse(sc(eye[0] + 6, eye[1] + 6, eye[0] + 20, eye[1] + 18), fill=RED)
        d.ellipse(sc(eye[0] + 9, eye[1] + 8, eye[0] + 14, eye[1] + 13), fill=(255, 220, 180))

    # Ухмылка и клыки.
    d.arc(sc(230, 194, 282, 234), start=8, end=172, fill=INK, width=sw(5))
    d.polygon([sc(238, 206), sc(246, 220), sc(252, 206)], fill=(232, 224, 214))
    d.polygon([sc(262, 206), sc(270, 220), sc(276, 206)], fill=(232, 224, 214))

    # Свечение глаз и груди.
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for cx, cy in ((237, 171), (279, 171)):
        gd.ellipse(sc(cx - 28, cy - 28, cx + 28, cy + 28), fill=(255, 90, 60, 130))
    gd.ellipse(sc(226, 286, 286, 354), fill=(255, 100, 60, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(sw(13)))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    # Парящие души.
    for cx, cy, r in ((146, 128, 11), (372, 126, 9), (396, 208, 7),
                      (120, 214, 7), (256, 64, 6)):
        d.ellipse(sc(cx - r, cy - r, cx + r, cy + r), fill=SOUL,
                  outline=(170, 58, 44), width=sw(3))
        d.ellipse(sc(cx - r // 2, cy - r // 2, cx + r // 4, cy + r // 4),
                  fill=(255, 244, 222))

    img = img.resize((512, 512), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
