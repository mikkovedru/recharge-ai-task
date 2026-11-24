"""Packaged Recharge AI-task artwork shared by the tray and GTK windows."""
from pathlib import Path

REPOSITORY_URL = "https://github.com/mikkovedru/recharge-ai-task"

ASSETS = Path(__file__).resolve().parent / "assets"


def asset_path(name: str) -> Path:
    return ASSETS / name


def tray_image(*, running: bool = False):
    """Use the approved logo with an opaque border and a status strip."""
    from PIL import Image, ImageDraw

    scale = 4
    image = Image.new("RGBA", (64 * scale, 64 * scale), "#101820")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2*scale, 2*scale, 61*scale, 61*scale), fill="white")
    # Use the space above the status strip for the logo. A few pixels of
    # extra margin here noticeably reduce the mark at 16–24 px panel sizes.
    with Image.open(asset_path("logo-symbol.png")) as artwork:
        logo = artwork.convert("RGBA").resize((58*scale, 58*scale), Image.Resampling.LANCZOS)
    image.alpha_composite(logo, (3*scale, scale))
    draw.rectangle((5*scale, 59*scale, 58*scale, 62*scale),
                   fill="#00df70" if running else "#ffcc00")
    return image.resize((64, 64), Image.Resampling.LANCZOS)


def set_window_icon(window) -> None:
    from gi.repository import GdkPixbuf
    window.set_icon_list([
        GdkPixbuf.Pixbuf.new_from_file(str(asset_path(f"icon-{size}.png")))
        for size in (16, 24, 32, 48, 64, 128, 256)
    ])
