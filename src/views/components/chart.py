from collections import deque

from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt, QTimer, Signal

from src.controller.event_bus import EventBus


class ChartWidget(QWidget):
    topic_value_received = Signal(str, object)

    def __init__(self, config=None, parent=None, event_bus=None):
        super().__init__(parent)
        self.config = config or {}
        self.event_bus = event_bus or EventBus()
        self.chart = QChart()
        self.view = QChartView(self.chart)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        self._chart_type = self.config.get("chart_type", "bar")
        self._title = self.config.get("title", "")
        self._categories = self.config.get("categories", [])
        self._data = []
        self._label_key = self.config.get("label_key", "Parameter")
        self._value_key = self.config.get("value_key", "Value")
        self._series_name = self.config.get("series_name", "Serie 1")
        self._buffer_size = max(1, int(self.config.get("buffer_size", 50)))
        self._line_buffer = deque(maxlen=self._buffer_size)
        self._topic_rows = {}
        self._rows = []
        self._dirty = False

        self.chart.setTitle(self._title)
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)

        self._render_timer = QTimer(self)
        self._render_timer.setInterval(100)  # 10 fps max
        self._render_timer.timeout.connect(self._flush_if_dirty)
        self._render_timer.start()

        self.topic_value_received.connect(self._apply_topic_update)
        self._load_from_config()

    def set_chart_type(self, chart_type: str):
        self._chart_type = chart_type
        self._rebuild_chart()

    def set_categories(self, categories):
        self._categories = categories
        self._rebuild_chart()

    def set_data(self, data):
        if self._chart_type == "lines":
            self._reset_line_buffer(data)
            self._rebuild_chart()
            return

        self._data = data
        self._rebuild_chart()

    def update(self, data=None):
        if self._chart_type == "lines" and data is not None:
            self._append_line_sample(data)
            self._rebuild_chart()
            return

        if data is not None:
            self.set_data(data)
            return

        self._rebuild_chart()

    def set_title(self, title: str):
        self._title = title
        self.chart.setTitle(title)

    def _load_from_config(self):
        rows = self.config.get("data", [])
        self._rows = [dict(row) for row in rows if isinstance(row, dict)]

        for index, row in enumerate(self._rows):
            topic = str(row.get("topic", "")).strip()
            if not topic:
                continue

            self._topic_rows[topic] = index
            self.event_bus.subscribe(
                topic,
                lambda value, topic_name=topic: self.topic_value_received.emit(topic_name, value),
            )

        if self._chart_type == "lines":
            self._reset_line_buffer(self._rows or rows)
            self._rebuild_chart()
            return

        if self._rows and not self._categories:
            self._categories = [str(row.get(self._label_key, "")) for row in self._rows]

        if self._rows and not self._data:
            values = []
            for row in self._rows:
                try:
                    values.append(float(row.get(self._value_key, 0)))
                except (TypeError, ValueError):
                    values.append(0)
            self._data = values

        self._rebuild_chart()

    def _flush_if_dirty(self):
        if not self._dirty:
            return
        self._dirty = False
        if self._chart_type == "lines":
            sample = {
                str(row.get(self._label_key, "")): float(row.get(self._value_key, 0))
                for row in self._rows
                if row.get(self._label_key)
            }
            if sample:
                self._line_buffer.append(sample)
        else:
            self._data = [float(row.get(self._value_key, 0)) for row in self._rows]
        self._rebuild_chart()

    def _apply_topic_update(self, topic, value):
        row_index = self._topic_rows.get(topic)
        if row_index is None:
            return

        numeric_value = self._to_float(value)
        if numeric_value is None:
            return

        self._rows[row_index][self._value_key] = numeric_value
        self._dirty = True

    def _to_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_line_sample(self, data):
        if data is None:
            return {}

        if isinstance(data, (int, float)):
            return {self._series_name: float(data)}

        if isinstance(data, dict):
            if self._label_key in data and self._value_key in data:
                value = self._to_float(data.get(self._value_key))
                if value is None:
                    return {}
                return {str(data.get(self._label_key, self._series_name)): value}

            sample = {}
            for label, value in data.items():
                numeric_value = self._to_float(value)
                if numeric_value is not None:
                    sample[str(label)] = numeric_value
            return sample

        if isinstance(data, (list, tuple)):
            if not data:
                return {}

            if all(isinstance(item, dict) for item in data):
                sample = {}
                for item in data:
                    if self._label_key not in item or self._value_key not in item:
                        continue
                    value = self._to_float(item.get(self._value_key))
                    if value is None:
                        continue
                    sample[str(item.get(self._label_key, self._series_name))] = value
                return sample

            numeric_values = []
            for item in data:
                numeric_value = self._to_float(item)
                if numeric_value is not None:
                    numeric_values.append(numeric_value)

            if not numeric_values:
                return {}

            labels = list(self._categories) if self._categories else []
            if labels and len(labels) == len(numeric_values):
                return {str(label): value for label, value in zip(labels, numeric_values)}

            if len(numeric_values) == 1:
                return {self._series_name: numeric_values[0]}

            return {
                f"{self._series_name} {index + 1}": value
                for index, value in enumerate(numeric_values)
            }

        return {}

    def _reset_line_buffer(self, data):
        self._line_buffer.clear()
        sample = self._normalize_line_sample(data)
        if sample:
            self._line_buffer.append(sample)
            self._categories = list(sample.keys())

    def _append_line_sample(self, data):
        sample = self._normalize_line_sample(data)
        if not sample:
            return

        for label in sample:
            if label not in self._categories:
                self._categories.append(label)

        self._line_buffer.append(sample)

    def _clear_chart(self):
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)

    def _build_line_chart(self):
        labels = list(self._categories)
        if not labels and self._line_buffer:
            ordered_labels = []
            for sample in self._line_buffer:
                for label in sample:
                    if label not in ordered_labels:
                        ordered_labels.append(label)
            labels = ordered_labels
            self._categories = ordered_labels

        series_map = {}
        all_values = []
        for label in labels:
            series = QLineSeries()
            series.setName(label)
            series_map[label] = series

        for index, sample in enumerate(self._line_buffer):
            for label, value in sample.items():
                series = series_map.get(label)
                if series is None:
                    series = QLineSeries()
                    series.setName(label)
                    series_map[label] = series
                series.append(index, value)
                all_values.append(value)

        for label in labels:
            series = series_map.get(label)
            if series is not None:
                self.chart.addSeries(series)

        if not self.chart.series():
            return

        sample_count = max(len(self._line_buffer), 1)
        x_axis = QValueAxis()
        x_axis.setRange(0, max(sample_count - 1, 1))
        x_axis.setLabelFormat("%d")
        x_axis.setTickCount(min(max(sample_count, 2), 10))

        y_axis = QValueAxis()
        if all_values:
            min_value = min(all_values)
            max_value = max(all_values)
            if min_value == max_value:
                padding = max(abs(max_value) * 0.1, 1)
            else:
                padding = max((max_value - min_value) * 0.1, 1)
            y_axis.setRange(min_value - padding, max_value + padding)
        else:
            y_axis.setRange(0, 10)

        self.chart.addAxis(x_axis, Qt.AlignBottom)
        self.chart.addAxis(y_axis, Qt.AlignLeft)
        for series in self.chart.series():
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

        self.chart.legend().setVisible(len(self.chart.series()) > 1)

    def _rebuild_chart(self):
        self._clear_chart()

        if self._chart_type == "lines":
            self._build_line_chart()
            return

        if self._chart_type == "pie":
            series = QPieSeries()
            for label, value in zip(self._categories, self._data):
                series.append(label, value)
            self.chart.addSeries(series)
            self.chart.legend().setVisible(True)
            return

        bar_set = QBarSet(self._series_name)
        for value in self._data:
            bar_set.append(value)

        if self._chart_type == "band":
            series = QHorizontalBarSeries()
        else:
            series = QBarSeries()

        series.append(bar_set)
        self.chart.addSeries(series)
        self.chart.legend().setVisible(False)

        category_axis = QBarCategoryAxis()
        category_axis.append(self._categories)

        value_axis = QValueAxis()
        max_value = max(self._data) if self._data else 10
        value_axis.setRange(0, max(max_value + 5, 10))
        value_axis.setLabelFormat("%d")

        self.chart.addAxis(category_axis, Qt.AlignBottom if self._chart_type == "bar" else Qt.AlignLeft)
        self.chart.addAxis(value_axis, Qt.AlignLeft if self._chart_type == "bar" else Qt.AlignBottom)

        series.attachAxis(category_axis)
        series.attachAxis(value_axis)