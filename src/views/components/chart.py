from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCharts import (
    QChart, QChartView, QBarSeries, QHorizontalBarSeries,
    QBarSet, QPieSeries, QBarCategoryAxis, QValueAxis
)
from PySide6.QtCore import Qt


class ChartWidget(QWidget):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.chart = QChart()
        self.view = QChartView(self.chart)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        self._chart_type = self.config.get("chart_type", "bar")
        self._title = self.config.get("title", "")
        self._categories = self.config.get("categories", [])
        self._data = []

        self.chart.setTitle(self._title)

    def set_chart_type(self, chart_type: str):
        self._chart_type = chart_type
        self._rebuild_chart()

    def set_categories(self, categories):
        self._categories = categories
        self._rebuild_chart()

    def set_data(self, data):
        self._data = data
        self._rebuild_chart()

    def set_title(self, title: str):
        self._title = title
        self.chart.setTitle(title)

    def _clear_chart(self):
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)

    def _rebuild_chart(self):
        self._clear_chart()

        if self._chart_type == "pie":
            series = QPieSeries()
            for label, value in zip(self._categories, self._data):
                series.append(label, value)
            self.chart.addSeries(series)
            self.chart.legend().setVisible(True)
            return

        bar_set = QBarSet("Série 1")
        for value in self._data:
            bar_set.append(value)

        if self._chart_type == "band":
            series = QHorizontalBarSeries()
        else:
            series = QBarSeries()

        series.append(bar_set)
        self.chart.addSeries(series)

        category_axis = QBarCategoryAxis()
        category_axis.append(self._categories)

        value_axis = QValueAxis()
        value_axis.setRange(0, max(self._data) if self._data else 10)

        self.chart.addAxis(category_axis, Qt.AlignBottom if self._chart_type == "bar" else Qt.AlignLeft)
        self.chart.addAxis(value_axis, Qt.AlignLeft if self._chart_type == "bar" else Qt.AlignBottom)

        series.attachAxis(category_axis)
        series.attachAxis(value_axis)