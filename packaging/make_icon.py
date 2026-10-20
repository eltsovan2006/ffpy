"""Write packaging/ffpy.ico from the icon drawn in ffpy.gui.app (run once)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv)
from ffpy.gui.app import app_icon  # noqa: E402

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffpy.ico")
ok = app_icon().pixmap(QSize(256, 256)).save(out, "ICO")
print(out, ok)
