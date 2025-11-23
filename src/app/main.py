import sys
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QStackedWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TooZ Hub 2")
        self.setGeometry(100, 100, 800, 600)

        # Vytvořit panelku
        sidebar_layout = QVBoxLayout()
        ai_button = QPushButton("AI Asistent")
        email_button = QPushButton("Email")
        calendar_button = QPushButton("Kalendář")
        pdf_button = QPushButton("PDF")
        images_button = QPushButton("Obrazy")
        voice_button = QPushButton("Hlasový asistent")
        vehicle_hub_button = QPushButton("Vozidlo Hub")
        settings_button = QPushButton("Nastavení")

        sidebar_layout.addWidget(ai_button)
        sidebar_layout.addWidget(email_button)
        sidebar_layout.addWidget(calendar_button)
        sidebar_layout.addWidget(pdf_button)
        sidebar_layout.addWidget(images_button)
        sidebar_layout.addWidget(voice_button)
        sidebar_layout.addWidget(vehicle_hub_button)
        sidebar_layout.addWidget(settings_button)

        # Vytvořit centrální widget
        stacked_widget = QStackedWidget()
        ai_placeholder = QWidget()
        email_placeholder = QWidget()
        calendar_placeholder = QWidget()
        pdf_placeholder = QWidget()
        images_placeholder = QWidget()
        voice_placeholder = QWidget()
        vehicle_hub_placeholder = QWidget()

        ai_label = QLabel("AI Asistent")
        email_label = QLabel("Email")
        calendar_label = QLabel("Kalendář")
        pdf_label = QLabel("PDF")
        images_label = QLabel("Obrazy")
        voice_label = QLabel("Hlasový asistent")
        vehicle_hub_label = QLabel("Vozidlo Hub")

        ai_placeholder.setLayout(QVBoxLayout().addWidget(ai_label))
        email_placeholder.setLayout(QVBoxLayout().addWidget(email_label))
        calendar_placeholder.setLayout(QVBoxLayout().addWidget(calendar_label))
        pdf_placeholder.setLayout(QVBoxLayout().addWidget(pdf_label))
        images_placeholder.setLayout(QVBoxLayout().addWidget(images_label))
        voice_placeholder.setLayout(QVBoxLayout().addWidget(voice_label))
        vehicle_hub_placeholder.setLayout(QVBoxLayout().addWidget(vehicle_hub_label))

        stacked_widget.addWidget(ai_placeholder)
        stacked_widget.addWidget(email_placeholder)
        stacked_widget.addWidget(calendar_placeholder)
        stacked_widget.addWidget(pdf_placeholder)
        stacked_widget.addWidget(images_placeholder)
        stacked_widget.addWidget(voice_placeholder)
        stacked_widget.addWidget(vehicle_hub_placeholder)

        # Rozložit widgety
        layout = self.centralWidget().layout()
        layout.addLayout(sidebar_layout, Qt.LeftDockWidgetArea)
        layout.addWidget(stacked_widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
