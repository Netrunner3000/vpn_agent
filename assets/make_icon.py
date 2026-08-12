"""One-off generator for the app icon (run manually, not at app runtime).

A shield with a keyhole on a cyan gradient: the app builds the thing that
protects the connection, and holds the only key to it.

    python assets/make_icon.py

Drawn with QPainter rather than PIL so icon generation needs nothing the app
does not already depend on. Each size is rendered natively instead of being
downsampled from one master, which keeps the shield edge and the keyhole crisp
at 16px — where a downsampled keyhole turns into a grey smudge.
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
)

ASSETS = Path(__file__).resolve().parent
ICONSET = ASSETS / "icon.iconset"

CYAN_TOP = QColor("#00e5ff")
BLUE_BOTTOM = QColor("#0b4f8a")
INK = QColor("#0b1418")

SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def shield_path(size: int) -> QPainterPath:
    """A classic shield: straight shoulders, curved flanks, a point at the base."""
    centre = size / 2
    top = size * 0.20
    bottom = size * 0.84
    half = size * 0.255
    shoulder = size * 0.46

    path = QPainterPath()
    path.moveTo(centre - half, top)
    path.lineTo(centre + half, top)
    path.lineTo(centre + half, shoulder)
    # Flanks sweep inward to the point rather than meeting at an angle.
    path.quadTo(QPointF(centre + half, bottom - size * 0.10), QPointF(centre, bottom))
    path.quadTo(QPointF(centre - half, bottom - size * 0.10), QPointF(centre - half, shoulder))
    path.closeSubpath()
    return path


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Dark rounded tile, so the cyan shield has something to sit against in
    # both the light and dark Dock.
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    painter.fillPath(tile, QBrush(INK))

    gradient = QLinearGradient(0, size * 0.18, 0, size * 0.86)
    gradient.setColorAt(0.0, CYAN_TOP)
    gradient.setColorAt(1.0, BLUE_BOTTOM)
    painter.fillPath(shield_path(size), QBrush(gradient))

    # Keyhole, punched out so the dark tile shows through. Circle plus a
    # tapering stem — recognisable down to 16px, where a drawn key is not.
    centre = size / 2
    hole_y = size * 0.435
    radius = size * 0.077
    stem_half_top = size * 0.043
    stem_half_bottom = size * 0.026
    stem_bottom = size * 0.635

    keyhole = QPainterPath()
    keyhole.addEllipse(QPointF(centre, hole_y), radius, radius)

    stem = QPainterPath()
    stem.moveTo(centre - stem_half_top, hole_y)
    stem.lineTo(centre + stem_half_top, hole_y)
    stem.lineTo(centre + stem_half_bottom, stem_bottom)
    stem.lineTo(centre - stem_half_bottom, stem_bottom)
    stem.closeSubpath()

    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    painter.fillPath(keyhole.united(stem), QBrush(QColor(0, 0, 0)))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    painter.end()
    return image


def main() -> int:
    QGuiApplication([])  # QImage/QPainter need an application instance.
    ICONSET.mkdir(exist_ok=True)

    for name, px in SIZES.items():
        if not draw_icon(px).save(str(ICONSET / name)):
            print(f"Failed to write {name}", file=sys.stderr)
            return 1

    icns = ASSETS / "icon.icns"
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    print(f"Wrote {len(SIZES)} PNGs to {ICONSET}")
    print(f"Wrote {icns} ({icns.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
