from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "phantom-logo-source.png"


def fitted_logo(size: int, padding_ratio: float = 0.08) -> Image.Image:
    """Fit tk's canonical transparent logo into a square icon canvas."""
    source = Image.open(SOURCE).convert("RGBA")
    alpha = source.getchannel("A")
    # Ignore near-transparent glow pixels when finding the visual bounds, while
    # retaining them in the crop itself through a small expansion.
    solid_bbox = alpha.point([0 if value < 32 else 255 for value in range(256)]).getbbox()
    if solid_bbox is None:
        raise ValueError(f"Logo source has no visible pixels: {SOURCE}")

    left, top, right, bottom = solid_bbox
    expand = max(2, round(max(source.size) * 0.02))
    crop_box = (
        max(0, left - expand),
        max(0, top - expand),
        min(source.width, right + expand),
        min(source.height, bottom + expand),
    )
    mark = source.crop(crop_box)

    padding = max(1, round(size * padding_ratio))
    available = size - 2 * padding
    scale = min(available / mark.width, available / mark.height)
    rendered_size = (
        max(1, round(mark.width * scale)),
        max(1, round(mark.height * scale)),
    )
    mark = mark.resize(rendered_size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - mark.width) // 2
    y = (size - mark.height) // 2
    canvas.alpha_composite(mark, (x, y))
    return canvas


def main() -> None:
    build = ROOT / "build"
    icons = build / "icons"
    public = ROOT / "apps/desktop/src/renderer/public"
    companion = ROOT / "apps/desktop/resources/companion"
    for directory in (build, icons, public, companion):
        directory.mkdir(parents=True, exist_ok=True)

    canonical = fitted_logo(1024)
    canonical.save(build / "icon.png")
    for size in (16, 32, 64, 128, 256, 512, 1024):
        fitted_logo(size).save(icons / f"icon-{size}.png")

    fitted_logo(357, 0.05).save(public / "logo.png")
    fitted_logo(357, 0.05).save(public / "icon.png")
    for size in (16, 48, 128):
        fitted_logo(size).save(companion / f"icon{size}.png")

    canonical.save(
        build / "icon.icns",
        format="ICNS",
        sizes=[
            (16, 16),
            (32, 32),
            (64, 64),
            (128, 128),
            (256, 256),
            (512, 512),
            (1024, 1024),
        ],
    )
    print(f"generated Phantom Browser icon family from {SOURCE}")


if __name__ == "__main__":
    main()
