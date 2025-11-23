import sys
from PySide6.QtWidgets import QApplication, QWidget, QLabel  # přidán import
from PySide6.QtCore import Qt

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("TooZ Hub 2")
        self.setGeometry(100, 100, 800, 600)

        layout = self.centralWidget().layout()
        placeholder = QLabel("Placeholder", self)
        layout.addWidget(placeholder)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
