from PySide6 import QtWidgets, QtCore
from modules.vehicle_hub.service import VehicleHubService, Vehicle


class VehicleHubWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.service = VehicleHubService()

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # Přidat vozidlo
        add_button_layout = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("Přidat vozidlo")
        add_button.clicked.connect(self.add_vehicle)
        add_button_layout.addWidget(add_button)
        layout.addLayout(add_button_layout)

        # Seznam vozidel
        self.vehicle_table = QtWidgets.QTableWidget()
        self.vehicle_table.setRowCount(0)
        self.vehicle_table.setColumnCount(6)
        self.vehicle_table.setHorizontalHeaderLabels(["VIN", "SPZ", "Název", "Rok", "Motor"])
        layout.addWidget(self.vehicle_table)

        # Detaily vozidla
        self.detail_text = QtWidgets.QTextEdit()
        self.detail_text.setReadOnly(True)
        layout.addWidget(self.detail_text)

    def add_vehicle(self):
        dialog = QtWidgets.QDialog()
        form_layout = QtWidgets.QFormLayout()

        vin_input = QtWidgets.QLineEdit()
        plate_input = QtWidgets.QLineEdit()
        name_input = QtWidgets.QLineEdit()

        form_layout.addRow("VIN:", vin_input)
        form_layout.addRow("SPZ:", plate_input)
        form_layout.addRow("Název vozidla:", name_input)

        dialog.setLayout(form_layout)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            vehicle = Vehicle(vin=vin_input.text(), plate=plate_input.text(), name=name_input.text())
            self.service.add_vehicle(vehicle)
            self.refresh_table()

    def refresh_table(self):
        self.vehicle_table.setRowCount(0)
        for vehicle in self.service.get_all_vehicles():
            row_position = self.vehicle_table.rowCount()
            self.vehicle_table.insertRow(row_position)

            vin_item = QtWidgets.QTableWidgetItem(vehicle.vin)
            plate_item = QtWidgets.QTableWidgetItem(vehicle.plate)
            name_item = QtWidgets.QTableWidgetItem(vehicle.name)
            year_item = QtWidgets.QTableWidgetItem(str(vehicle.year))
            engine_item = QtWidgets.QTableWidgetItem(vehicle.engine or "")

            self.vehicle_table.setItem(row_position, 0, vin_item)
            self.vehicle_table.setItem(row_position, 1, plate_item)
            self.vehicle_table.setItem(row_position, 2, name_item)
            self.vehicle_table.setItem(row_position, 3, year_item)
            self.vehicle_table.setItem(row_position, 4, engine_item)

        selected_row = self.vehicle_table.currentRow()
        if selected_row != -1:
            vehicle = self.service.get_vehicle(self.vehicle_table.item(selected_row, 0).text())
            if vehicle:
                self.detail_text.setText(f"VIN: {vehicle.vin}\nSPZ: {vehicle.plate}\nNázev: {vehicle.name}\nRok: {str(vehicle.year)}\nMotor: {vehicle.engine or ''}")
