"""Generate modern macOS-style and Windows icons for ffpy using PySide6.QtGui."""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from ffpy.gui.app import render_app_image  # noqa: E402


def build_ico(img_1024, out_ico_path):
    """Write multi-resolution Windows .ico file (16 to 256 px) using PNG payloads."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_data_list = []
    for s in sizes:
        scaled = img_1024.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        scaled.save(buf, "PNG")
        png_data_list.append((s, bytes(ba)))

    # ICONDIR header: idReserved (0), idType (1 = ICO), idCount (number of images)
    header = struct.pack("<HHH", 0, 1, len(png_data_list))
    offset = 6 + 16 * len(png_data_list)
    entries = []
    for s, data in png_data_list:
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        # ICONDIRENTRY: width, height, colors, reserved, planes, bpp, bytesInRes, offset
        entries.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
        offset += len(data)

    with open(out_ico_path, "wb") as f:
        f.write(header + b"".join(entries) + b"".join(d for _, d in png_data_list))


def build_icns(img_1024, out_icns_path):
    """Write macOS .icns file using iconutil and standard iconset resolutions."""
    iconutil = shutil.which("iconutil")
    if not iconutil:
        print("Warning: iconutil not found (only available on macOS). Skipping .icns creation.")
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_dir = os.path.join(tmpdir, "ffpy.iconset")
        os.makedirs(iconset_dir, exist_ok=True)
        specs = [
            ("icon_16x16.png", 16),
            ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32),
            ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512),
            ("icon_512x512@2x.png", 1024),
        ]
        for filename, s in specs:
            scaled = img_1024.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled.save(os.path.join(iconset_dir, filename), "PNG")

        cmd = [iconutil, "-c", "icns", "-o", out_icns_path, iconset_dir]
        subprocess.run(cmd, check=True)
    return True


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    _ = app  # Keep reference

    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(pkg_dir, "ffpy.ico")
    icns_path = os.path.join(pkg_dir, "ffpy.icns")
    preview_dir = os.path.join(ROOT, ".ai", "shots")
    preview_path = os.path.join(preview_dir, "icon_preview.png")
    os.makedirs(preview_dir, exist_ok=True)

    print("Rendering 1024x1024 master icon...")
    img_1024 = render_app_image(1024)

    print(f"Saving preview to {preview_path}...")
    img_1024.save(preview_path, "PNG")

    print(f"Generating Windows ICO at {ico_path}...")
    build_ico(img_1024, ico_path)

    print(f"Generating macOS ICNS at {icns_path}...")
    build_icns(img_1024, icns_path)

    print("Icon generation completed successfully.")


if __name__ == "__main__":
    main()
