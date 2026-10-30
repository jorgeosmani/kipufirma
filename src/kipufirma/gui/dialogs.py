"""Diálogos: contraseña, resultados del lote y confirmaciones."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kipufirma.core.batch import STATUS_ERROR, STATUS_OK, STATUS_SKIP, DocResult, export_report
from kipufirma.gui.theme import ERR, OK, WARN


def caps_lock_on() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        except Exception:
            return False
    return False


def open_in_explorer(path: Path) -> None:
    path = Path(path)
    try:
        if sys.platform == "win32":
            if path.is_file():
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 (carpeta local del usuario)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path if path.is_dir() else path.parent)], check=False)
        else:
            subprocess.run(["xdg-open", str(path if path.is_dir() else path.parent)], check=False)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("No se pudo abrir el explorador: %s", e)


class PasswordDialog(QDialog):
    """Pide SOLO la contraseña. Muestra a quién pertenece el certificado para
    que el usuario confirme que firma con la identidad correcta."""

    def __init__(self, holder: str, detail: str, n_docs: int, on_submit=None, parent=None) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self.setWindowTitle("Contraseña del certificado")
        self.setModal(True)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        title = QLabel(f"<b>Firmar {n_docs} documento(s)</b>" if n_docs else "<b>Desbloquear certificado</b>")
        title.setObjectName("Title")
        lay.addWidget(title)
        who = QLabel(f"Firmante: <b>{holder or 'certificado configurado'}</b><br><span style='color:#7A8594'>{detail}</span>")
        who.setTextFormat(Qt.RichText)
        who.setWordWrap(True)
        lay.addWidget(who)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("Contraseña del archivo .p12")
        self.edit.setAttribute(Qt.WA_InputMethodEnabled, False)
        self.edit.setContextMenuPolicy(Qt.NoContextMenu)        # sin copiar/pegar desde menú
        self.edit.textChanged.connect(self._clear_error)
        self.toggle = QPushButton("Mostrar")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(lambda on: (self.edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                                                self.toggle.setText("Ocultar" if on else "Mostrar")))
        row.addWidget(self.edit, 1)
        row.addWidget(self.toggle)
        lay.addLayout(row)
        self.caps = QLabel("⚠ Bloq Mayús está activado")
        self.caps.setStyleSheet(f"color:{WARN}")
        self.caps.hide()
        lay.addWidget(self.caps)
        self.error = QLabel()
        self.error.setStyleSheet(f"color:{ERR}")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)
        note = QLabel("La contraseña no se guarda. Se borra de la memoria al terminar.")
        note.setObjectName("Muted")
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Firmar" if n_docs else "Aceptar")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._timer = QTimer(self, interval=400, timeout=lambda: self.caps.setVisible(caps_lock_on()))
        self._timer.start()
        self.edit.setFocus()

    def _clear_error(self) -> None:
        self.error.hide()

    def show_error(self, msg: str) -> None:
        self.error.setText(msg)
        self.error.show()
        self.edit.selectAll()
        self.edit.setFocus()

    def _accept(self) -> None:
        if not self.edit.text():
            self.show_error("Escriba la contraseña.")
            return
        if self._on_submit is not None:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                msg = self._on_submit(self.take_password())
            finally:
                QApplication.restoreOverrideCursor()
            if msg:
                self.show_error(msg)
                return
        self.accept()

    def take_password(self) -> str:
        """Entrega la contraseña y vacía el campo (se reduce su permanencia)."""
        pw = self.edit.text()
        self.edit.clear()
        return pw


class ResultsDialog(QDialog):
    def __init__(self, results: list[DocResult], signer: str, open_folder: bool, parent=None) -> None:
        super().__init__(parent)
        self.results, self.signer = results, signer
        self.setWindowTitle("Resultado de la firma")
        self.resize(900, 460)
        lay = QVBoxLayout(self)
        ok = sum(r.status not in (STATUS_ERROR, STATUS_SKIP) for r in results)
        err = sum(r.status == STATUS_ERROR for r in results)
        skip = sum(r.status == STATUS_SKIP for r in results)
        head = QLabel(f"<b>{ok}</b> firmado(s) · <b>{err}</b> con error · <b>{skip}</b> omitido(s)")
        head.setObjectName("Title")
        lay.addWidget(head)
        t = QTableWidget(len(results), 4)
        t.setHorizontalHeaderLabels(["Documento", "Estado", "Ubicación", "Detalle"])
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        for i, r in enumerate(results):
            color = {STATUS_OK: OK, STATUS_ERROR: ERR, STATUS_SKIP: "#7A8594"}.get(r.status, WARN)
            vals = [r.source.name, r.status, r.placement, " · ".join([r.message] + r.warnings).strip(" ·")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(str(r.output or r.source) if j == 0 else v)
                if j == 1:
                    it.setForeground(QColor(color))
                t.setItem(i, j, it)
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        t.resizeColumnsToContents()
        t.cellDoubleClicked.connect(lambda row, _c: results[row].output and open_in_explorer(results[row].output))
        lay.addWidget(t)
        row = QHBoxLayout()
        b_open = QPushButton("Abrir carpeta de salida")
        outs = [r.output for r in results if r.output]
        b_open.setEnabled(bool(outs))
        b_open.clicked.connect(lambda: open_in_explorer(outs[0].parent))
        b_rep = QPushButton("Exportar informe (CSV)…")
        b_rep.clicked.connect(self._export)
        b_close = QPushButton("Cerrar")
        b_close.setObjectName("Primary")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_open)
        row.addWidget(b_rep)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addLayout(row)
        if open_folder and outs:
            QTimer.singleShot(300, lambda: open_in_explorer(outs[0].parent))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Guardar informe", "informe-firmas.csv", "CSV (*.csv)")
        if path:
            export_report(self.results, Path(path), self.signer)
