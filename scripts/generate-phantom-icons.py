from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SIZE = 1024

# Original Phantom Browser mark: an angular hood/portal with a spectral eye cutout.
canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(canvas)

# Rounded graphite tile leaves safe margin for Windows/macOS masks.
d.rounded_rectangle((70, 70, 954, 954), radius=210, fill=(8, 11, 13, 255))
d.rounded_rectangle((88, 88, 936, 936), radius=194, outline=(39, 54, 49, 255), width=5)

# Restrained green aura behind the symbol.
glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.polygon([(512, 194), (795, 349), (744, 708), (512, 845), (280, 708), (229, 349)], fill=(40, 255, 128, 115))
glow = glow.filter(ImageFilter.GaussianBlur(54))
canvas.alpha_composite(glow)
d = ImageDraw.Draw(canvas)

# Faceted phantom hood — readable even at 16 px.
d.polygon([(512, 174), (812, 347), (751, 722), (512, 858), (273, 722), (212, 347)], fill=(19, 26, 25, 255))
d.line([(512, 174), (812, 347), (751, 722), (512, 858), (273, 722), (212, 347), (512, 174)], fill=(57, 255, 139, 255), width=24, joint="curve")
d.polygon([(512, 174), (512, 858), (273, 722), (212, 347)], fill=(13, 18, 19, 235))
d.line([(512, 194), (512, 812)], fill=(40, 87, 65, 210), width=8)

# Browser-window / spectral-eye negative-space motif.
d.rounded_rectangle((330, 365, 694, 628), radius=72, fill=(5, 8, 9, 255), outline=(96, 122, 112, 255), width=10)
d.ellipse((379, 416, 645, 578), fill=(54, 255, 139, 255))
d.ellipse((449, 435, 575, 561), fill=(6, 10, 10, 255))
d.ellipse((482, 468, 526, 512), fill=(210, 255, 229, 255))
# Three browser controls become subtle fangs / status marks.
for x, color in [(382, (57, 255, 139, 255)), (420, (72, 92, 85, 255)), (458, (72, 92, 85, 255))]:
    d.ellipse((x, 386, x + 18, 404), fill=color)

# Export canonical assets.
build = ROOT / "build"
icons = build / "icons"
public = ROOT / "apps/desktop/src/renderer/public"
companion = ROOT / "apps/desktop/resources/companion"
for directory in (build, icons, public, companion):
    directory.mkdir(parents=True, exist_ok=True)

canvas.save(build / "icon.png")
for n in (16, 32, 48, 64, 128, 256, 512, 1024):
    resized = canvas.resize((n, n), Image.Resampling.LANCZOS)
    if n != 48:
        resized.save(icons / f"icon-{n}.png")

canvas.resize((357, 357), Image.Resampling.LANCZOS).save(public / "logo.png")
canvas.resize((357, 357), Image.Resampling.LANCZOS).save(public / "icon.png")
for n in (16, 48, 128):
    canvas.resize((n, n), Image.Resampling.LANCZOS).save(companion / f"icon{n}.png")

canvas.save(build / "icon.icns", format="ICNS", sizes=[(16,16), (32,32), (64,64), (128,128), (256,256), (512,512), (1024,1024)])
print("generated Phantom Browser icon family")
