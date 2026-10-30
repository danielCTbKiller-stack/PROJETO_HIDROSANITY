import sys

from PySide6.QtWidgets import QApplication

from gui import theme
from gui.main_window import MainWindow


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setStyle("Fusion")
    app.setPalette(theme.paleta())
    app.setFont(theme.fonte("corpo", 9))
    app.setStyleSheet(theme.qss())
    window = MainWindow()
    window.showMaximized()
    if len(app.arguments()) > 1:
        window.load_file(app.arguments()[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
