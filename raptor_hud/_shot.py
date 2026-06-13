"""Службовий скрипт: рендерить вікно з фіксованими даними і зберігає PNG."""
import os, sys, tempfile
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from raptor_hud.main import MainWindow

def run(out_path: str):
    app = QApplication(sys.argv)
    win = MainWindow(rtsp=None, mavlink=None)
    win.resize(1280, 720)
    win.show()
    def grab():
        win.grab().save(out_path)
        app.quit()
    QTimer.singleShot(700, grab)
    app.exec()
    print("saved", out_path)

if __name__ == "__main__":
    default = os.path.join(tempfile.gettempdir(), "raptor_shot.png")
    run(sys.argv[1] if len(sys.argv) > 1 else default)
