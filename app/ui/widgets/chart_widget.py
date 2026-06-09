from __future__ import annotations

from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

rcParams["font.family"] = [
    "Hiragino Sans GB",
    "Heiti TC",
    "Songti SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
rcParams["axes.unicode_minus"] = False


class ChartWidget(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5, 2.8), dpi=100, constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.title = title
        self.set_series([], [])

    def set_series(self, labels: list[str], values: list[float | int]) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title(self.title, loc="left", fontsize=10, color="#1F2937")
        ax.set_facecolor("#FFFFFF")
        if values:
            ax.plot(range(len(values)), values, color="#2F67F6", marker="o", linewidth=2)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=8)
        else:
            ax.text(0.5, 0.5, "暂无历史数据", ha="center", va="center", color="#94A3B8")
            ax.set_xticks([])
            ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")
        ax.grid(alpha=0.15)
        self.canvas.draw_idle()
