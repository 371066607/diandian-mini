from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    started = Signal()
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        self._safe_emit(self.signals.started)
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # pragma: no cover - UI thread bridge
            self._safe_emit(self.signals.error, str(exc))
        else:
            self._safe_emit(self.signals.finished, result)

    @staticmethod
    def _safe_emit(signal, *args) -> None:
        # During application shutdown the receiver/signals C++ object may already be
        # gone; emitting then raises RuntimeError. Swallow it so closing the window
        # never prints a teardown traceback.
        try:
            signal.emit(*args)
        except RuntimeError:  # pragma: no cover - shutdown race
            pass
