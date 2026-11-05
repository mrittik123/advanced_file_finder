"""Draws assets/app.ico (magnifier over a folder). Run once; the .ico is committed.  Needs Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=110, fill=(31, 41, 55, 255))
    # folder
    d.rounded_rectangle((70, 150, 350, 215), radius=22, fill=(245, 190, 60, 255))
    d.rounded_rectangle((70, 185, 442, 400), radius=30, fill=(252, 211, 77, 255))
    # magnifier
    d.ellipse((250, 215, 410, 375), outline=(37, 99, 235, 255), width=26, fill=(219, 234, 254, 200))
    d.line((390, 355, 455, 430), fill=(37, 99, 235, 255), width=34)
    return img


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    img = draw()
    img.save(out / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.resize((256, 256)).save(out / "app.png")
    print("wrote", out / "app.ico")
