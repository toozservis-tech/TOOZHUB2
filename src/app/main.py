from PySide6 import QtWidgets, QtCore
from modules.vehicle_hub.controller import VehicleHubWidget  # přidán import

# ... (ostatní kód zůstává stejný)

class MainWindow(QtWidgets.QMainWindow):
    # ... (ostatní kód zůstává stejný)

    def __init__(self) -> None:
        super().__init__()

        # ... (ostatní kód zůstává stejný)

        self.page_vehicle = VehicleHubWidget()

        # ... (ostatní kód zůstává stejný)
