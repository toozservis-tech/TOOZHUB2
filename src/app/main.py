import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("TooZ Hub 2")
        self.setGeometry(100, 100, 1000, 700)

        # ---------- CENTRÁLNÍ WIDGET + HLAVNÍ LAYOUT ----------
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QHBoxLayout()
        central.setLayout(main_layout)

        # ---------- LEVÝ SIDEBAR ----------
        sidebar = QVBoxLayout()

        self.btn_ai = QPushButton("AI Asistent")
        self.btn_email = QPushButton("Email")
        self.btn_calendar = QPushButton("Kalendář")
        self.btn_pdf = QPushButton("PDF")
        self.btn_images = QPushButton("Obrázky")
        self.btn_voice = QPushButton("Hlas")
        self.btn_vehicle = QPushButton("Vehicle Hub")
        self.btn_settings = QPushButton("Nastavení")

        for btn in [
            self.btn_ai,
            self.btn_email,
            self.btn_calendar,
            self.btn_pdf,
            self.btn_images,
            self.btn_voice,
            self.btn_vehicle,
            self.btn_settings,
        ]:
            btn.setCursor(Qt.PointingHandCursor)
            sidebar.addWidget(btn)

        sidebar.addStretch()

        # ---------- PRAVÁ STRANA – QStackedWidget ----------
        self.stack = QStackedWidget()

        self.page_ai = self._make_placeholder_page("AI Asistent")
        self.page_email = self._make_placeholder_page("Email")
        self.page_calendar = self._make_placeholder_page("Kalendář")
        self.page_pdf = self._make_placeholder_page("PDF")
        self.page_images = self._make_placeholder_page("Obrázky")
        self.page_voice = self._make_placeholder_page("Hlas")
        self.page_vehicle = self._make_placeholder_page("Vehicle Hub")
        self.page_settings = self._make_placeholder_page("Nastavení")

        self.stack.addWidget(self.page_ai)        # index 0
        self.stack.addWidget(self.page_email)     # index 1
        self.stack.addWidget(self.page_calendar)  # index 2
        self.stack.addWidget(self.page_pdf)       # index 3
        self.stack.addWidget(self.page_images)    # index 4
        self.stack.addWidget(self.page_voice)     # index 5
        self.stack.addWidget(self.page_vehicle)   # index 6
        self.stack.addWidget(self.page_settings)  # index 7

        # ---------- PROPOJENÍ TLAČÍTEK NA STACK ----------
        self.btn_ai.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_email.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_calendar.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.btn_pdf.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.btn_images.clicked.connect(lambda: self.stack.setCurrentIndex(4))
        self.btn_voice.clicked.connect(lambda: self.stack.setCurrentIndex(5))
        self.btn_vehicle.clicked.connect(lambda: self.stack.setCurrentIndex(6))
        self.btn_settings.clicked.connect(lambda: self.stack.setCurrentIndex(7))

        # ---------- POSKLÁDÁNÍ DO MAIN LAYOUTU ----------
        main_layout.addLayout(sidebar, stretch=0)
        main_layout.addWidget(self.stack, stretch=1)

    @staticmethod
    def _make_placeholder_page(text: str) -> QWidget:
        """Jednoduchý placeholder pro moduly – jen label uprostřed."""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        page.setLayout(layout)
        return page


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

