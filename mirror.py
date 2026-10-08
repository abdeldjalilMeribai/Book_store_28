from pathlib import Path
from PIL import Image, ImageOps

IMG = Path("static/img")
for name in ["hero-1.jpg", "hero-1-sm.jpg", "about.jpg", "deco-admin.jpg"]:
    src = IMG / name
    dst = src.with_name(src.stem + "-ar" + src.suffix)
    with Image.open(src) as im:
        ImageOps.mirror(im.convert("RGB")).save(dst, quality=88, optimize=True, progressive=True)
    print("créé :", dst)