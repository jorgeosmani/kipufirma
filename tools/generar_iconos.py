#!/usr/bin/env python3
"""Genera el ícono de la aplicación (PNG + ICO multi-resolución) con Pillow.
Motivo: un quipu (kipu) andino —cuerdas con nudos— y un trazo de firma."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=(31, 78, 121, 255))
    d.rounded_rectangle((40, 40, S - 40, 300), radius=210, fill=(42, 98, 153, 255))
    d.rectangle((40, 220, S - 40, 300), fill=(42, 98, 153, 255))
    gold = (242, 183, 5, 255)
    d.line((190, 250, 834, 250), fill=gold, width=34)              # cuerda principal
    for i, x in enumerate((270, 400, 530, 660)):                    # cuerdas colgantes con nudos
        d.line((x, 250, x, 470 + 40 * (i % 2)), fill=gold, width=24)
        for k in range(2 + i % 2):
            y = 320 + k * 70
            d.ellipse((x - 30, y - 30, x + 30, y + 30), fill=gold)
    white = (255, 255, 255, 255)
    pts = [(170, 760), (260, 640), (330, 760), (420, 600), (500, 770), (600, 640), (700, 720), (850, 560)]
    d.line(pts, fill=white, width=46, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - 23, p[1] - 23, p[0] + 23, p[1] + 23), fill=white)
    d.line((170, 850, 854, 850), fill=(255, 255, 255, 170), width=14)
    return img


def main() -> None:
    img = draw()
    icons = ROOT / "src" / "kipufirma" / "resources" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(icons / "kipufirma.png")
    pack = ROOT / "packaging"
    pack.mkdir(exist_ok=True)
    img.save(pack / "kipufirma.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Íconos generados")


if __name__ == "__main__":
    main()
