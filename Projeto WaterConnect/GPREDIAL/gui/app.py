import sys

from PySide6.QtWidgets import QApplication

from gui import theme
from gui.main_window import MainWindow


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setStyle("Fusion")
    theme.aplicar_tema(None, app)  # o tema escolhido em Configurações (padrão: Verde Saneamento)
    window = MainWindow()
    window.showMaximized()
    if len(app.arguments()) > 1:
        window.load_file(app.arguments()[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
