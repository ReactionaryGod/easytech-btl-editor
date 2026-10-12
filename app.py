"""EasyTech BTL Editor - start with:  python app.py [map.btl]  (or run.bat on Windows)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from wc4btl.ui.mainwindow import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EasyTech BTL Editor")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".btl"):
        w.open_map(os.path.abspath(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
