"""Trabajo en segundo plano (la interfaz nunca se congela)."""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from kipufirma.core.batch import preview_document, run_batch


class FuncWorker(QThread):
    done = Signal(object, object)               # (resultado, excepción)

    def __init__(self, fn, *args, parent=None) -> None:
        super().__init__(parent)
        self._fn, self._args = fn, args

    def run(self) -> None:
        try:
            self.done.emit(self._fn(*self._args), None)
        except Exception as e:  # se reenvía a la interfaz
            traceback.print_exc()
            self.done.emit(None, e)


class ResolveWorker(QThread):
    """Calcula la ubicación prevista de cada documento."""
    resolved = Signal(int, str, object)          # (generación, ruta, Preview)

    def __init__(self, generation: int, items: list[tuple[Path, list | None]], settings, parent=None) -> None:
        super().__init__(parent)
        self.generation, self.items, self.settings = generation, items, settings
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        for path, manual in self.items:
            if self._stop.is_set():
                return
            self.resolved.emit(self.generation, str(path), preview_document(path, self.settings, manual))


class BatchWorker(QThread):
    progress = Signal(int, int, str, object)
    finished_ok = Signal(object)
    failed = Signal(object)

    def __init__(self, files, cred, settings, trust, manual, parent=None) -> None:
        super().__init__(parent)
        self.files, self.cred, self.settings, self.trust, self.manual = files, cred, settings, trust, manual
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            res = run_batch(self.files, self.cred, self.settings, self.trust, self.manual,
                            progress=lambda i, t, f, r: self.progress.emit(i, t, str(f), r),
                            cancel=self.cancel)
            self.finished_ok.emit(res)
        except Exception as e:
            self.failed.emit(e)
