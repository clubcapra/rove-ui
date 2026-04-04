import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem


class Table(QWidget):
    def __init__(self, header=None, data=None):
        super().__init__()
        self.setMinimumSize(400, 300)
        self.header = header
        self.data = data




    def build(self):
        header = self.header or ["Nom", "Valeur"]
        rows = self.data or []

        table = QTableWidget(len(rows), len(header))
        table.setHorizontalHeaderLabels(header)

        self.data = rows or [
            ("label 1", "value 1"),
            ("label 2", "value 2"),
            ("label 3", "value 3"),
            ("label 4", "value 4"),
        ]

        for row, row_data in enumerate(self.data or []):
            for col, column_name in enumerate(header):
                if isinstance(row_data, dict):
                    value = row_data.get(column_name, "")
                    unit = row_data.get("unit", "") if col == len(header) - 1 else ""
                    cell_text = f"{value}{unit}" if unit and value != "" else str(value)
                else:
                    cell_text = str(row_data[col])
                table.setItem(row, col, QTableWidgetItem(cell_text))

        layout = QVBoxLayout(self)
        layout.addWidget(table)

    def update(self, data=None):
        self.data = data or self.data
        self.build()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Table(["ODrive", "Température", "Voltage"], [("ODrive 1", "75°C", "20V"), ("ODrive 2", "45°C", "18V"), ("ODrive 3", "15°C", "22V"), ("ODrive 4", "90°C", "19V")])
    w.build()
    w.show()
    sys.exit(app.exec())