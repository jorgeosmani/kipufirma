"""Ventana principal de KipuFirma."""
from __future__ import annotations

import copy
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kipufirma import APP_NAME, AUTHOR, AUTHOR_EMAILS, COPYRIGHT_YEAR, __version__
from kipufirma.core.batch import Preview, prepare_session
from kipufirma.core.certificate import AttemptLimiter, check_usable, file_sha256, is_in_cloud_folder, load_credential
from kipufirma.core.config import Settings, load_settings, save_settings
from kipufirma.core.errors import KipuError, TooManyAttemptsError, WrongPasswordError
from kipufirma.core.placement import FixedRule, ManualBox
from kipufirma.core.secrets import SecretBuffer
from kipufirma.core.trust import TrustStore
from kipufirma.core.verify import verify_pdf_bytes
from kipufirma.gui.dialogs import PasswordDialog, ResultsDialog, open_in_explorer
from kipufirma.gui.preview import PreviewView
from kipufirma.gui.theme import ERR, OK, WARN, apply_theme
from kipufirma.gui.workers import BatchWorker, FuncWorker, ResolveWorker
from kipufirma.paths import log_dir, resource_path

log = logging.getLogger(__name__)
PT_PER_MM = 72 / 25.4


def mm(pt: float) -> float:
    return round(pt / PT_PER_MM, 1)


def pt(mm_value: float) -> float:
    return mm_value * PT_PER_MM


def combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    c = QComboBox()
    for value, label in items:
        c.addItem(label, value)
    idx = c.findData(current)
    c.setCurrentIndex(max(idx, 0))
    return c


def set_combo(c: QComboBox, value: str) -> None:
    c.blockSignals(True)
    c.setCurrentIndex(max(c.findData(value), 0))
    c.blockSignals(False)


def spin_mm(value_pt: float, lo: float = 0, hi: float = 500) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(1)
    s.setSuffix(" mm")
    s.setValue(mm(value_pt))
    return s


def card(widget_layout) -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    f.setLayout(widget_layout)
    return f


def collect_pdfs(paths: list[Path], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            out += sorted(x for x in it if x.is_file() and x.suffix.lower() == ".pdf"
                          and not x.name.startswith(".kipu-"))
        elif p.is_file() and p.suffix.lower() == ".pdf":
            out.append(p)
    return out


# =============================================================================
# Página FIRMAR
# =============================================================================
class SignPage(QWidget):
    COLS = ["Documento", "Págs.", "Ubicación prevista", "Estado"]

    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        self.docs: list[dict] = []            # {path, preview, manual, status}
        self._generation = 0
        self._resolver: ResolveWorker | None = None
        self._resolve_timer = QTimer(self, singleShot=True, interval=350, timeout=self._resolve_all)
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self.main.save)
        self.setAcceptDrops(True)
        self._build()
        self._load_form()

    # ---------------------------------------------------------------- UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)

        banner = QHBoxLayout()
        self.cert_label = QLabel()
        self.cert_label.setTextFormat(Qt.RichText)
        b_cert = QPushButton("Certificado…")
        b_cert.clicked.connect(lambda: self.main.goto(2))
        banner.addWidget(self.cert_label, 1)
        banner.addWidget(b_cert)
        bf = QFrame()
        bf.setObjectName("CertBanner")
        bf.setLayout(banner)
        root.addWidget(bf)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # --- documentos
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        tb = QHBoxLayout()
        for text, slot in (("Agregar PDF…", self._add_files), ("Agregar carpeta…", self._add_folder),
                           ("Quitar", self._remove_selected), ("Limpiar", self._clear)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addStretch(1)
        ll.addLayout(tb)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemSelectionChanged.connect(self._on_select)
        ll.addWidget(self.table, 1)
        self.drop_hint = QLabel("Arrastre aquí archivos PDF o carpetas")
        self.drop_hint.setObjectName("Muted")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        ll.addWidget(self.drop_hint)
        split.addWidget(left)

        # --- vista previa
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.b_prev = QPushButton("◀")
        self.b_next = QPushButton("▶")
        self.page_label = QLabel("—")
        self.draw_target = combo([("todos", "Al hacer clic: posición para TODOS"),
                                  ("este", "Al hacer clic: solo ESTE documento")], "todos")
        self.b_prev.clicked.connect(lambda: self._go(-1))
        self.b_next.clicked.connect(lambda: self._go(1))
        nav.addWidget(self.b_prev)
        nav.addWidget(self.page_label)
        nav.addWidget(self.b_next)
        nav.addStretch(1)
        nav.addWidget(self.draw_target)
        ml.addLayout(nav)
        self.preview = PreviewView()
        self.preview.rectChosen.connect(self._on_rect_chosen)
        self.preview.pageChanged = self._update_preview_boxes
        ml.addWidget(self.preview, 1)
        hint = QLabel("Mueva el ratón: el sello muestra dónde quedará. Clic para colocarlo. "
                      "Flechas: ajuste fino (Mayús = 10×). Rueda: cambiar de página.")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        ml.addWidget(hint)
        split.addWidget(mid)

        # --- opciones
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        opts = QWidget()
        ol = QVBoxLayout(opts)
        ol.setContentsMargins(4, 0, 4, 0)

        g_mode = QGroupBox("¿Dónde va la firma?")
        gl = QVBoxLayout(g_mode)
        self.rb_fixed = QRadioButton("Misma posición en todos los documentos")
        self.rb_keyword = QRadioButton("Buscar palabra clave en cada documento")
        self.rb_invisible = QRadioButton("Firma invisible (sin sello)")
        self.mode_group = QButtonGroup(self)
        for i, rb in enumerate((self.rb_fixed, self.rb_keyword, self.rb_invisible)):
            self.mode_group.addButton(rb, i)
            gl.addWidget(rb)
        self.mode_group.idToggled.connect(self._form_changed)
        ol.addWidget(g_mode)

        self.g_fixed = QGroupBox("Posición fija")
        fl = QFormLayout(self.g_fixed)
        self.f_page = combo([("ultima", "Última página"), ("primera", "Primera página"),
                             ("numero", "Página número…"), ("todas", "Todas las páginas")], "ultima")
        self.f_page_n = QSpinBox()
        self.f_page_n.setRange(1, 9999)
        self.f_anchor = combo([("inf-der", "Esquina inferior derecha"), ("inf-izq", "Esquina inferior izquierda"),
                               ("sup-der", "Esquina superior derecha"), ("sup-izq", "Esquina superior izquierda")], "inf-der")
        self.f_dx = spin_mm(0)
        self.f_dy = spin_mm(0)
        fl.addRow("Página", self.f_page)
        fl.addRow("Número", self.f_page_n)
        fl.addRow("Referencia", self.f_anchor)
        fl.addRow("Distancia horizontal", self.f_dx)
        fl.addRow("Distancia vertical", self.f_dy)
        ol.addWidget(self.g_fixed)

        self.g_kw = QGroupBox("Palabra clave")
        kl = QFormLayout(self.g_kw)
        self.k_words = QPlainTextEdit()
        self.k_words.setPlaceholderText("Una por línea, en orden de prioridad.\nEj.: Firma del docente\nFirma:")
        self.k_words.setFixedHeight(72)
        self.k_pos = combo([("debajo", "Debajo del texto"), ("encima", "Encima del texto"),
                            ("derecha", "A la derecha"), ("izquierda", "A la izquierda"),
                            ("sobre", "Sobre el texto")], "debajo")
        self.k_align = combo([("izquierda", "Alineada a la izquierda"), ("centro", "Centrada"),
                              ("derecha", "Alineada a la derecha")], "izquierda")
        self.k_occ = combo([("ultima", "Última aparición"), ("primera", "Primera aparición"),
                            ("todas", "Todas (una firma por aparición)")], "ultima")
        self.k_gap = spin_mm(0, 0, 50)
        self.k_fb = combo([("fija", "Usar la posición fija"), ("invisible", "Firmar invisible"),
                           ("omitir", "No firmar ese documento")], "fija")
        kl.addRow("Buscar", self.k_words)
        kl.addRow("Ubicar", self.k_pos)
        kl.addRow("Alineación", self.k_align)
        kl.addRow("Si aparece varias veces", self.k_occ)
        kl.addRow("Separación", self.k_gap)
        kl.addRow("Si no se encuentra", self.k_fb)
        ol.addWidget(self.g_kw)

        g_stamp = QGroupBox("Sello y datos de la firma")
        sl = QFormLayout(g_stamp)
        self.s_preset = combo([("", "Personalizado"), ("firmaec", "Como FirmaEC (39 × 13 mm)"),
                               ("std", "Mediano (60 × 19 mm)"), ("grande", "Grande (80 × 26 mm)")], "")
        self.s_w = spin_mm(0, 10, 200)
        self.s_h = spin_mm(0, 5, 140)
        self.s_reason = QLineEdit()
        self.s_reason.setMaxLength(120)
        self.s_loc = QLineEdit()
        self.s_loc.setMaxLength(120)
        sl.addRow("Tamaño", self.s_preset)
        sl.addRow("Ancho", self.s_w)
        sl.addRow("Alto", self.s_h)
        sl.addRow("Razón", self.s_reason)
        sl.addRow("Localización", self.s_loc)
        ol.addWidget(g_stamp)

        g_out = QGroupBox("Guardar firmados en")
        ul = QVBoxLayout(g_out)
        self.o_mode = combo([("subcarpeta", "Subcarpeta «firmados» junto a cada original"),
                             ("junto", "La misma carpeta del original"),
                             ("carpeta", "Una carpeta específica…")], "subcarpeta")
        self.o_folder = QLabel()
        self.o_folder.setObjectName("Muted")
        self.o_folder.setWordWrap(True)
        ul.addWidget(self.o_mode)
        ul.addWidget(self.o_folder)
        ol.addWidget(g_out)
        ol.addStretch(1)
        scroll.setWidget(opts)
        scroll.setMinimumWidth(370)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        split.addWidget(scroll)
        split.setSizes([480, 520, 380])

        bottom = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        self.b_sign = QPushButton("Firmar documentos")
        self.b_sign.setObjectName("Primary")
        self.b_sign.clicked.connect(self._sign)
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(self.b_sign)
        root.addLayout(bottom)

        for w in (self.f_page, self.f_anchor, self.k_pos, self.k_align, self.k_occ, self.k_fb):
            w.currentIndexChanged.connect(self._form_changed)
        for w in (self.f_page_n, self.f_dx, self.f_dy, self.k_gap, self.s_w, self.s_h):
            w.valueChanged.connect(self._form_changed)
        self.k_words.textChanged.connect(self._form_changed)
        self.s_reason.textChanged.connect(self._form_changed)
        self.s_loc.textChanged.connect(self._form_changed)
        self.s_preset.currentIndexChanged.connect(self._apply_preset)
        self.o_mode.currentIndexChanged.connect(self._output_changed)

    # ------------------------------------------------------- formulario
    def _load_form(self) -> None:
        s = self.main.settings
        r = s.placement
        widgets = [self.s_preset, self.mode_group, self.f_page, self.f_page_n, self.f_anchor, self.f_dx, self.f_dy,
                   self.k_words, self.k_pos, self.k_align, self.k_occ, self.k_gap, self.k_fb,
                   self.s_w, self.s_h, self.s_reason, self.s_loc, self.o_mode]
        for w in widgets:
            w.blockSignals(True)
        {"fija": self.rb_fixed, "palabra": self.rb_keyword, "invisible": self.rb_invisible}[r.mode].setChecked(True)
        set_combo(self.f_page, r.fixed.page_mode)
        self.f_page_n.setValue(int(r.fixed.page_number))
        set_combo(self.f_anchor, r.fixed.anchor)
        self.f_dx.setValue(mm(r.fixed.dx))
        self.f_dy.setValue(mm(r.fixed.dy))
        self.k_words.setPlainText("\n".join(r.keyword.keywords))
        set_combo(self.k_pos, r.keyword.position)
        set_combo(self.k_align, r.keyword.align)
        set_combo(self.k_occ, r.keyword.occurrence)
        self.k_gap.setValue(mm(r.keyword.gap))
        set_combo(self.k_fb, r.keyword.fallback)
        self.s_w.setValue(mm(r.size.width))
        self.s_h.setValue(mm(r.size.height))
        self.s_reason.setText(s.signing.reason)
        self.s_loc.setText(s.signing.location)
        set_combo(self.o_mode, s.output.mode)
        sizes = {"firmaec": (38.8, 12.7), "std": (60.0, 19.0), "grande": (80.0, 26.0)}
        cur = (mm(r.size.width), mm(r.size.height))
        set_combo(self.s_preset, next((k for k, v in sizes.items() if abs(v[0] - cur[0]) < 0.3
                                       and abs(v[1] - cur[1]) < 0.3), ""))
        self.preview.stamp_size = (r.size.width, r.size.height)
        self.preview.signer_name = s.certificate.holder
        for w in widgets:
            w.blockSignals(False)
        self._update_visibility()
        self._update_output_label()
        self.refresh_cert_banner()

    def _update_visibility(self) -> None:
        mode = self.mode_group.checkedId()
        self.g_fixed.setEnabled(mode == 0 or (mode == 1 and self.k_fb.currentData() == "fija"))
        self.g_kw.setVisible(mode == 1)
        self.f_page_n.setEnabled(self.f_page.currentData() == "numero")
        self.preview.interactive = mode != 2 or self.draw_target.currentData() == "este"

    def _form_changed(self, *_a) -> None:
        s = self.main.settings
        r = s.placement
        r.mode = ["fija", "palabra", "invisible"][max(self.mode_group.checkedId(), 0)]
        r.fixed.page_mode = self.f_page.currentData()
        r.fixed.page_number = self.f_page_n.value()
        r.fixed.anchor = self.f_anchor.currentData()
        r.fixed.dx, r.fixed.dy = pt(self.f_dx.value()), pt(self.f_dy.value())
        r.keyword.keywords = [k.strip() for k in self.k_words.toPlainText().splitlines() if k.strip()] or [""]
        r.keyword.position = self.k_pos.currentData()
        r.keyword.align = self.k_align.currentData()
        r.keyword.occurrence = self.k_occ.currentData()
        r.keyword.gap = pt(self.k_gap.value())
        r.keyword.fallback = self.k_fb.currentData()
        r.size.width, r.size.height = pt(self.s_w.value()), pt(self.s_h.value())
        s.signing.reason = self.s_reason.text().strip()
        s.signing.location = self.s_loc.text().strip()
        self.preview.stamp_size = (r.size.width, r.size.height)
        self._update_visibility()
        self._save_timer.start()
        self._resolve_timer.start()

    def _apply_preset(self) -> None:
        sizes = {"std": (60, 19), "firmaec": (38.8, 12.7), "grande": (80, 26)}
        v = self.s_preset.currentData()
        if v in sizes:
            self.s_w.setValue(sizes[v][0])
            self.s_h.setValue(sizes[v][1])

    def _output_changed(self) -> None:
        o = self.main.settings.output
        mode = self.o_mode.currentData()
        if mode == "carpeta":
            folder = QFileDialog.getExistingDirectory(self, "Carpeta para los documentos firmados", o.folder)
            if not folder:
                set_combo(self.o_mode, o.mode)
                return
            o.folder = folder
        o.mode = mode
        self._update_output_label()
        self.main.save()

    def _update_output_label(self) -> None:
        o = self.main.settings.output
        self.o_folder.setText(o.folder if o.mode == "carpeta" else f"Nombre: documento{o.suffix}.pdf")

    def refresh_cert_banner(self) -> None:
        c = self.main.settings.certificate
        if c.path and Path(c.path).exists():
            who = c.holder or Path(c.path).name
            extra = f" · {c.ca_name}" if c.ca_name else ""
            if c.not_after:
                extra += f" · vence {datetime.fromisoformat(c.not_after).astimezone():%d/%m/%Y}"
            self.cert_label.setText(f"🔐 <b>{who}</b><span style='color:#7A8594'>{extra}</span>")
        elif c.path:
            self.cert_label.setText(f"<span style='color:{ERR}'>⚠ No se encuentra el certificado en {c.path}</span>")
        else:
            self.cert_label.setText(f"<span style='color:{WARN}'>⚠ Aún no ha seleccionado su certificado .p12</span>")

    # ------------------------------------------------------- documentos
    def add_paths(self, paths: list[Path]) -> None:
        files = collect_pdfs(paths, self.main.settings.ui.recursive_folders)
        known = {d["path"] for d in self.docs}
        added = 0
        for f in files:
            f = f.resolve()
            if f not in known:
                self.docs.append({"path": f, "preview": None, "manual": None, "status": "Pendiente"})
                known.add(f)
                added += 1
        if files:
            self.main.settings.ui.last_documents_dir = str(files[0].parent)
        self._refresh_table()
        if added and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._resolve_all()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar documentos PDF",
                                                self.main.settings.ui.last_documents_dir, "PDF (*.pdf)")
        self.add_paths([Path(f) for f in files])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", self.main.settings.ui.last_documents_dir)
        if d:
            self.add_paths([Path(d)])

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.docs.pop(r)
        self._refresh_table()
        self._on_select()

    def _clear(self) -> None:
        self.docs.clear()
        self._refresh_table()
        self.preview.set_document(None)

    def _refresh_table(self) -> None:
        current = self.table.currentRow()
        self.table.blockSignals(True)            # no recargar la vista previa al refrescar
        self.table.setRowCount(len(self.docs))
        for i, d in enumerate(self.docs):
            p: Preview | None = d["preview"]
            pages = str(p.report.page_count) if p and p.report.page_count else "…"
            if p is None:
                where, color = "Calculando…", None
            elif p.error:
                where, color = p.error, ERR
            else:
                res = p.resolution
                where = res.summary
                color = WARN if (res.skipped or res.source == "alternativa") else None
                if p.report.threats:
                    where += " · ⚠ contenido activo"
                    color = WARN
            vals = [d["path"].name + ("  ✎" if d["manual"] else ""), pages, where, d["status"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(str(d["path"]) if j == 0 else v)
                if j == 2 and color:
                    it.setForeground(QColor(color))
                if j == 3:
                    it.setForeground(QColor({"Firmado": OK, "Error": ERR}.get(v.split()[0], "#7A8594")))
                self.table.setItem(i, j, it)
        if 0 <= current < len(self.docs):
            self.table.selectRow(current)
        self.table.blockSignals(False)
        n = len(self.docs)
        single = n <= 1
        self.rb_fixed.setText("Elegir el lugar con un clic en la página" if single
                              else "Misma posición en todos los documentos")
        self.rb_keyword.setText("Buscar una palabra clave en el documento" if single
                                else "Buscar palabra clave en cada documento")
        self.g_fixed.setTitle("Ajuste fino de la posición (opcional)" if single else "Posición fija")
        self.draw_target.setVisible(not single)
        if single:
            set_combo(self.draw_target, "todos")
        self.drop_hint.setVisible(n == 0)
        self.b_sign.setText(f"Firmar {n} documento(s)" if n else "Firmar documentos")
        self.b_sign.setEnabled(n > 0)
        skipped = sum(1 for d in self.docs if d["preview"] and d["preview"].resolution
                      and d["preview"].resolution.skipped)
        self.summary.setText(f"{n} documento(s) en la lista" + (f" · {skipped} se omitirán" if skipped else ""))

    def _context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        d = self.docs[row]
        m = QMenu(self)
        a_clear = QAction("Quitar ubicación manual", self, enabled=bool(d["manual"]))
        a_clear.triggered.connect(lambda: self._set_manual(row, None))
        a_open = QAction("Mostrar en carpeta", self)
        a_open.triggered.connect(lambda: open_in_explorer(d["path"]))
        m.addAction(a_clear)
        m.addAction(a_open)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _set_manual(self, row: int, boxes) -> None:
        self.docs[row]["manual"] = boxes
        self.docs[row]["preview"] = None
        self._refresh_table()
        self._resolve_all()

    # ------------------------------------------------------- vista previa
    def _current(self) -> dict | None:
        r = self.table.currentRow()
        return self.docs[r] if 0 <= r < len(self.docs) else None

    def _on_select(self) -> None:
        d = self._current()
        if d is None:
            self.preview.set_document(None)
            self.page_label.setText("—")
            return
        target = None
        p = d["preview"]
        if p and p.resolution and p.resolution.boxes:
            target = p.resolution.boxes[0].page_index
        self.preview.set_document(d["path"], target)
        self._update_preview_boxes()

    def _go(self, delta: int) -> None:
        self.preview.go(delta)
        self._update_preview_boxes()

    def _update_preview_boxes(self) -> None:
        d = self._current()
        boxes = []
        if d and d["preview"] and d["preview"].resolution:
            boxes = [(b.page_index, b.visual_rect, "Firma") for b in d["preview"].resolution.boxes]
        self.preview.set_boxes(boxes)
        if self.preview.page_count:
            self.page_label.setText(f"Página {self.preview.page_index + 1} de {self.preview.page_count}")

    def _on_rect_chosen(self, page: int, rect) -> None:
        d = self._current()
        if d is None:
            return
        if self.draw_target.currentData() == "este":
            row = self.table.currentRow()
            self.docs[row]["manual"] = [ManualBox(page, rect)]
            self._refresh_table()
            self._resolve_all()
            return
        r = self.main.settings.placement
        count = self.preview.page_count
        mode = r.fixed.page_mode
        if not ((page == count - 1 and mode in ("ultima", "todas")) or (page == 0 and mode in ("primera", "todas"))):
            mode = "ultima" if page == count - 1 else "primera" if page == 0 else "numero"
        r.fixed = FixedRule.from_visual_rect(rect, self.preview.page_w, self.preview.page_h, mode, page + 1)
        r.size.width, r.size.height = rect.width, rect.height
        if r.mode != "fija":
            r.mode = "fija"
        self._load_form()
        self._form_changed()
        self.preview.show_placed(page, rect)        # se ve al instante

    def _resolve_all(self) -> None:
        if not self.docs:
            return
        if self._resolver is not None:
            self._resolver.stop()
        self._generation += 1
        items = [(d["path"], d["manual"]) for d in self.docs]
        w = ResolveWorker(self._generation, items, copy.deepcopy(self.main.settings), self)
        w.resolved.connect(self._on_resolved)
        self._resolver = w
        w.start()

    def _on_resolved(self, gen: int, path: str, preview: Preview) -> None:
        if gen != self._generation:
            return
        for i, d in enumerate(self.docs):
            if str(d["path"]) == path:
                d["preview"] = preview
                if i == self.table.currentRow():
                    self._update_preview_boxes()
        self._refresh_table()

    # ------------------------------------------------------- arrastrar y soltar
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        self.add_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    # ------------------------------------------------------- firmar
    def _sign(self) -> None:
        self.main.sign_documents(self.docs)

    def mark_results(self, results) -> None:
        by = {r.source.resolve(): r for r in results}
        for d in self.docs:
            r = by.get(d["path"])
            if r:
                d["status"] = r.status
        self._refresh_table()


# =============================================================================
# Página VERIFICAR
# =============================================================================
class VerifyPage(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        t = QLabel("Verificar firmas")
        t.setObjectName("Title")
        lay.addWidget(t)
        info = QLabel("Comprueba la integridad de las firmas y si fueron emitidas por una Entidad de Certificación "
                      "reconocida en Ecuador. Para efectos legales, valide también en el validador oficial FirmaEC.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        row = QHBoxLayout()
        b = QPushButton("Agregar PDF firmados…")
        b.clicked.connect(self._add)
        self.online = QCheckBox("Consultar revocación en línea")
        b_web = QPushButton("Abrir validador oficial")
        b_web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.firmadigital.gob.ec/")))
        row.addWidget(b)
        row.addWidget(self.online)
        row.addStretch(1)
        row.addWidget(b_web)
        lay.addLayout(row)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Documento", "Firmante", "Entidad", "Fecha de firma", "Resultado", "Detalle"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        self._workers: list[FuncWorker] = []

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        self.verify([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    def _add(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "PDF firmados", "", "PDF (*.pdf)")
        self.verify([Path(f) for f in files])

    def verify(self, paths: list[Path]) -> None:
        files = collect_pdfs(paths, True)
        trust, online = self.main.trust, self.online.isChecked()

        def job():
            return [(f, verify_pdf_bytes(f.read_bytes(), trust, online)) for f in files]

        w = FuncWorker(job, parent=self)
        w.done.connect(self._show)
        self._workers.append(w)
        self.main.statusBar().showMessage("Verificando…")
        w.start()

    def _show(self, result, error) -> None:
        self.main.statusBar().clearMessage()
        if error:
            QMessageBox.warning(self, APP_NAME, f"No se pudo verificar: {error}")
            return
        for f, reps in result:
            rows = reps or [None]
            for r in rows:
                i = self.table.rowCount()
                self.table.insertRow(i)
                if r is None:
                    vals, color = [f.name, "—", "—", "—", "Sin firmas", ""], WARN
                else:
                    ok = r.ok and r.trusted
                    res = "Válida" if ok else ("Íntegra, entidad no reconocida" if r.ok else "INVÁLIDA")
                    color = OK if ok else (WARN if r.ok else ERR)
                    when = r.signing_time.astimezone().strftime("%d/%m/%Y %H:%M") if r.signing_time else "—"
                    det = []
                    if r.has_timestamp:
                        det.append("con sello de tiempo")
                    if not r.covers_whole_document:
                        det.append("hay cambios posteriores (p. ej. otras firmas)")
                    det += r.errors
                    vals = [f.name, r.signer_name, r.ca_name, when, res, "; ".join(det)]
                for j, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    if j == 4:
                        it.setForeground(QColor(color))
                    self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()


# =============================================================================
# Página MI CERTIFICADO
# =============================================================================
class CertificatePage(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        t = QLabel("Mi certificado de firma electrónica")
        t.setObjectName("Title")
        lay.addWidget(t)
        g = QGridLayout()
        self.fields: dict[str, QLabel] = {}
        for i, (k, label) in enumerate([("path", "Archivo"), ("holder", "Titular"), ("ca", "Entidad emisora"),
                                        ("validity", "Vence"), ("thumb", "Huella SHA-256"), ("state", "Estado")]):
            g.addWidget(QLabel(f"<b>{label}</b>"), i, 0, Qt.AlignTop)
            v = QLabel("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(v, i, 1)
            self.fields[k] = v
        g.setColumnStretch(1, 1)
        lay.addWidget(card(g))
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color:{WARN}")
        lay.addWidget(self.warn)
        row = QHBoxLayout()
        b_sel = QPushButton("Seleccionar archivo .p12 / .pfx…")
        b_sel.setObjectName("Primary")
        b_sel.clicked.connect(self._select)
        b_chk = QPushButton("Comprobar ahora…")
        b_chk.clicked.connect(self._check)
        b_forget = QPushButton("Olvidar certificado")
        b_forget.clicked.connect(self._forget)
        row.addWidget(b_sel)
        row.addWidget(b_chk)
        row.addStretch(1)
        row.addWidget(b_forget)
        lay.addLayout(row)
        note = QLabel(
            "• Solo se recuerda la <b>ubicación</b> del archivo y su huella digital; la contraseña nunca se guarda.<br>"
            "• Si el archivo .p12 cambia (por ejemplo, al renovar el certificado) se le avisará antes de firmar.<br>"
            "• Recomendación: mantenga el .p12 en su equipo (no en carpetas sincronizadas con la nube) y con una "
            "copia de respaldo cifrada.")
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        note.setObjectName("Muted")
        lay.addWidget(note)
        lay.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        c = self.main.settings.certificate
        f = self.fields
        f["path"].setText(c.path or "—")
        f["holder"].setText(c.holder or ("(se mostrará al comprobar el certificado)" if c.path else "—"))
        f["ca"].setText(c.ca_name or "—")
        if c.not_after:
            na = datetime.fromisoformat(c.not_after)
            days = (na - datetime.now(na.tzinfo)).days
            color = ERR if days < 0 else WARN if days <= 30 else OK
            f["validity"].setText(f"{na.astimezone():%d/%m/%Y} <span style='color:{color}'>({days} días)</span>")
        else:
            f["validity"].setText("—")
        f["thumb"].setText(c.thumbprint or "—")
        exists = bool(c.path) and Path(c.path).exists()
        f["state"].setText("Listo para firmar" if exists and c.thumbprint else
                           "Archivo no encontrado" if c.path and not exists else
                           "Pendiente de comprobar" if c.path else "Sin configurar")
        msgs = []
        if c.path and self.main.settings.security.warn_cloud_folder and is_in_cloud_folder(Path(c.path)):
            msgs.append("⚠ El certificado está en una carpeta sincronizada con la nube. Es más seguro moverlo a una "
                        "carpeta local del equipo.")
        self.warn.setText("<br>".join(msgs))
        self.main.sign_page.refresh_cert_banner() if hasattr(self.main, "sign_page") else None

    def _select(self) -> None:
        start = str(Path(self.main.settings.certificate.path).parent) if self.main.settings.certificate.path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar certificado", start,
                                              "Certificado PKCS#12 (*.p12 *.pfx)")
        if not path:
            return
        c = self.main.settings.certificate
        c.path = path
        c.file_sha256 = file_sha256(Path(path))
        c.thumbprint = c.holder = c.ca_name = c.not_after = ""
        self.main.save()
        self.refresh()
        self._check()

    def _check(self) -> None:
        cred = self.main.unlock_certificate(n_docs=0)
        if cred is None:
            return
        try:
            warnings = check_usable(cred, require_trusted_chain=False)
            chain_ok = cred.chain is not None and cred.chain.trusted
            text = ("Cadena de confianza verificada hasta una Entidad de Certificación reconocida."
                    if chain_ok else "⚠ No se pudo verificar la cadena hasta una Entidad reconocida.")
            QMessageBox.information(self, APP_NAME, "\n\n".join([f"Certificado de {cred.info.signer.display_name}",
                                                               text] + warnings))
        except KipuError as e:
            QMessageBox.warning(self, APP_NAME, f"El certificado no se puede usar para firmar:\n\n{e}")
        finally:
            cred.destroy()
        self.refresh()

    def _forget(self) -> None:
        if QMessageBox.question(self, APP_NAME, "¿Olvidar la ubicación del certificado? El archivo no se borra.") \
                == QMessageBox.Yes:
            self.main.settings.certificate = type(self.main.settings.certificate)()
            self.main.save()
            self.refresh()


# =============================================================================
# Página AJUSTES
# =============================================================================
class SettingsPage(QWidget):
    def __init__(self, main: "MainWindow") -> None:
        super().__init__()
        self.main = main
        s = main.settings
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        t = QLabel("Ajustes")
        t.setObjectName("Title")
        outer.addWidget(t)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)

        g1 = QGroupBox("Formato de firma")
        f1 = QFormLayout(g1)
        self.subfilter = combo([("adbe", "Compatible FirmaEC (adbe.pkcs7.detached)"),
                                ("pades", "PAdES ETSI (ETSI.CAdES.detached)")], s.signing.subfilter)
        self.md = combo([("sha512", "SHA-512 (como FirmaEC)"), ("sha384", "SHA-384"), ("sha256", "SHA-256")],
                        s.signing.md_algorithm)
        f1.addRow("Tipo", self.subfilter)
        f1.addRow("Resumen", self.md)
        lay.addWidget(g1)

        g2 = QGroupBox("Contenido del sello")
        f2 = QFormLayout(g2)
        self.header = QLineEdit(s.signing.header_text)
        self.footer = QLineEdit(s.signing.footer_text)
        self.qr = QCheckBox("Incluir código QR con los datos de la firma")
        self.qr.setChecked(s.signing.show_qr)
        self.date = QCheckBox("Mostrar fecha y hora en el sello")
        self.date.setChecked(s.signing.show_date_in_stamp)
        f2.addRow("Encabezado", self.header)
        f2.addRow("Pie", self.footer)
        f2.addRow(self.qr)
        f2.addRow(self.date)
        lay.addWidget(g2)

        g3 = QGroupBox("Seguridad")
        f3 = QFormLayout(g3)
        self.rev = combo([("advertir", "Comprobar y advertir si no hay conexión"),
                          ("estricta", "Estricta: no firmar sin confirmar que no está revocado"),
                          ("desactivada", "No comprobar")], s.security.revocation_policy)
        self.threat = combo([("advertir", "Firmar y advertir"), ("bloquear", "No firmar")], s.security.pdf_threat_policy)
        self.trusted = QCheckBox("Exigir certificado de una Entidad de Certificación reconocida en Ecuador")
        self.trusted.setChecked(s.security.require_trusted_ca)
        self.clock = QCheckBox("Verificar que el reloj del equipo esté en hora")
        self.clock.setChecked(s.security.check_clock)
        self.cloud = QCheckBox("Advertir si el certificado está en una carpeta en la nube")
        self.cloud.setChecked(s.security.warn_cloud_folder)
        f3.addRow("Revocación (OCSP/CRL)", self.rev)
        f3.addRow("PDF con contenido activo", self.threat)
        f3.addRow(self.trusted)
        f3.addRow(self.clock)
        f3.addRow(self.cloud)
        lay.addWidget(g3)

        g4 = QGroupBox("Sello de tiempo (opcional, RFC 3161)")
        f4 = QFormLayout(g4)
        self.tsa = QLineEdit(s.signing.tsa_url)
        self.tsa.setPlaceholderText("https://… (vacío = sin sello de tiempo)")
        self.tsa_user = QLineEdit(s.signing.tsa_user)
        self.tsa_pw = QLineEdit(s.signing.tsa_password)
        self.tsa_pw.setEchoMode(QLineEdit.Password)
        f4.addRow("URL del servidor", self.tsa)
        f4.addRow("Usuario", self.tsa_user)
        f4.addRow("Contraseña", self.tsa_pw)
        tsa_note = QLabel("Use solo servidores de su Entidad de Certificación o autorizados. "
                          "La contraseña se protege con Windows (DPAPI).")
        tsa_note.setWordWrap(True)
        tsa_note.setObjectName("Muted")
        f4.addRow(tsa_note)
        lay.addWidget(g4)

        g5 = QGroupBox("Otros")
        f5 = QFormLayout(g5)
        self.theme = combo([("sistema", "Según Windows"), ("claro", "Claro"), ("oscuro", "Oscuro")], s.ui.theme)
        self.recursive = QCheckBox("Al agregar carpetas, incluir subcarpetas")
        self.recursive.setChecked(s.ui.recursive_folders)
        self.open_out = QCheckBox("Abrir la carpeta de salida al terminar")
        self.open_out.setChecked(s.output.open_folder_when_done)
        self.suffix = QLineEdit(s.output.suffix)
        f5.addRow("Tema", self.theme)
        f5.addRow("Sufijo del archivo firmado", self.suffix)
        f5.addRow(self.recursive)
        f5.addRow(self.open_out)
        b_logs = QPushButton("Abrir carpeta de registros")
        b_logs.clicked.connect(lambda: open_in_explorer(log_dir()))
        f5.addRow(b_logs)
        lay.addWidget(g5)
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        for w in (self.subfilter, self.md, self.rev, self.threat, self.theme):
            w.currentIndexChanged.connect(self._apply)
        for w in (self.qr, self.date, self.trusted, self.clock, self.cloud, self.recursive, self.open_out):
            w.toggled.connect(self._apply)
        for w in (self.header, self.footer, self.tsa, self.tsa_user, self.tsa_pw, self.suffix):
            w.editingFinished.connect(self._apply)

    def _apply(self, *_a) -> None:
        s = self.main.settings
        s.signing.subfilter = self.subfilter.currentData()
        s.signing.md_algorithm = self.md.currentData()
        s.signing.header_text = self.header.text()
        s.signing.footer_text = self.footer.text()
        s.signing.show_qr = self.qr.isChecked()
        s.signing.show_date_in_stamp = self.date.isChecked()
        s.signing.tsa_url = self.tsa.text().strip()
        s.signing.tsa_user = self.tsa_user.text().strip()
        s.set_tsa_password(self.tsa_pw.text())
        s.security.revocation_policy = self.rev.currentData()
        s.security.pdf_threat_policy = self.threat.currentData()
        s.security.require_trusted_ca = self.trusted.isChecked()
        s.security.check_clock = self.clock.isChecked()
        s.security.warn_cloud_folder = self.cloud.isChecked()
        theme_changed = s.ui.theme != self.theme.currentData()
        s.ui.theme = self.theme.currentData()
        s.ui.recursive_folders = self.recursive.isChecked()
        s.output.open_folder_when_done = self.open_out.isChecked()
        suffix = self.suffix.text().strip()
        s.output.suffix = suffix if suffix or s.output.mode != "junto" else "-firmado"
        self.main.save()
        if theme_changed:
            from PySide6.QtWidgets import QApplication
            apply_theme(QApplication.instance(), s.ui.theme)


# =============================================================================
# Página ACERCA DE
# =============================================================================
class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        text = QLabel(f"""
        <h2>{APP_NAME} {__version__}</h2>
        <p>Firmador electrónico de documentos PDF para Ecuador, de código abierto (AGPL-3.0-or-later).</p>
        <p><b>Desarrollado por:</b> {AUTHOR}<br>
        <b>Contacto:</b> {" · ".join(f'<a href="mailto:{e}">{e}</a>' for e in AUTHOR_EMAILS)}<br>
        © {COPYRIGHT_YEAR} {AUTHOR}</p>
        <p>Genera firmas PAdES con certificados emitidos por Entidades de Certificación acreditadas en
        Ecuador, compatibles con el validador oficial <a href="https://www.firmadigital.gob.ec">FirmaEC</a>.</p>
        <p><b>Basado en el análisis de FirmaEC</b> (Ministerio de Telecomunicaciones y de la Sociedad de la
        Información, MINTEL), software libre bajo GPL-3.0/AGPL-3.0. {APP_NAME} no es un producto oficial
        del Gobierno del Ecuador.</p>
        <p><b>Aviso legal:</b> la validez jurídica de la firma depende de que su certificado esté vigente, no
        revocado, emitido por una entidad acreditada y bajo su control exclusivo. Antes de usar en producción,
        valide una muestra de documentos en el validador oficial.</p>
        <p>Componentes: pyHanko (MIT), pypdfium2/PDFium (Apache-2.0/BSD), Qt for Python (LGPL-3.0),
        cryptography (Apache-2.0/BSD), qrcode (BSD).</p>
        """)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        text.setTextFormat(Qt.RichText)
        lay.addWidget(text)
        lay.addStretch(1)


# =============================================================================
# Ventana principal
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or load_settings()
        self.trust = TrustStore.default()
        self.limiter = AttemptLimiter()
        self._batch: BatchWorker | None = None
        self.setWindowTitle(f"{APP_NAME} — Firma electrónica")
        icon = resource_path("icons", "kipufirma.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1360, 820)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QVBoxLayout()
        side.setSpacing(0)
        brand = QLabel(f"✒ {APP_NAME}")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setFixedWidth(200)
        for label in ("Firmar", "Verificar", "Mi certificado", "Ajustes", "Acerca de"):
            QListWidgetItem(label, self.nav)
        side.addWidget(self.nav, 1)
        h.addLayout(side)

        self.stack = QStackedWidget()
        self.sign_page = SignPage(self)
        self.verify_page = VerifyPage(self)
        self.cert_page = CertificatePage(self)
        self.settings_page = SettingsPage(self)
        for p in (self.sign_page, self.verify_page, self.cert_page, self.settings_page, AboutPage()):
            self.stack.addWidget(p)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0 if self.settings.certificate.path else 2)
        self.statusBar().showMessage(f"{len(self.trust)} certificados de Entidades de Certificación cargados", 6000)

    # ------------------------------------------------------------------
    def goto(self, index: int) -> None:
        self.nav.setCurrentRow(index)

    def save(self) -> None:
        try:
            save_settings(self.settings)
        except Exception as e:
            log.error("No se pudo guardar la configuración: %s", e)

    def open_files(self, paths: list[str]) -> None:
        files = [Path(p) for p in paths if p]
        if files:
            self.goto(0)
            self.sign_page.add_paths(files)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    def _certificate_ready(self) -> Path | None:
        c = self.settings.certificate
        if not c.path:
            QMessageBox.information(self, APP_NAME, "Primero seleccione su certificado (.p12 o .pfx).")
            self.goto(2)
            return None
        p = Path(c.path)
        if not p.exists():
            QMessageBox.warning(self, APP_NAME, f"No se encontró el certificado en:\n{p}\n\nSelecciónelo nuevamente.")
            self.goto(2)
            return None
        current = file_sha256(p)
        if c.file_sha256 and current != c.file_sha256:
            ans = QMessageBox.warning(
                self, APP_NAME,
                "El archivo del certificado CAMBIÓ desde la última vez que se usó.\n\n"
                "Esto es normal si renovó su certificado. Si no lo hizo, alguien pudo reemplazarlo.\n\n"
                "¿Desea continuar? Se le mostrará el titular antes de firmar.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return None
            c.thumbprint = ""
        c.file_sha256 = current
        return p

    def unlock_certificate(self, n_docs: int):
        """Pide la contraseña (solo eso) y devuelve la credencial cargada."""
        path = self._certificate_ready()
        if path is None:
            return None
        c = self.settings.certificate
        detail = f"{c.ca_name} · {Path(c.path).name}" if c.ca_name else Path(c.path).name
        holder = {"cred": None}

        def submit(password: str) -> str | None:
            try:
                self.limiter.check()
                cred = load_credential(path, SecretBuffer(password), self.trust)
            except WrongPasswordError as e:
                self.limiter.failure()
                left = max(self.limiter.FREE_ATTEMPTS - self.limiter.failures, 0)
                return f"{e} " + (f"Le quedan {left} intento(s) antes de una espera." if left else "")
            except TooManyAttemptsError as e:
                return str(e)
            except KipuError as e:
                return str(e)
            finally:
                password = ""  # noqa: F841 (se descarta la referencia local)
            self.limiter.success()
            holder["cred"] = cred
            return None

        dlg = PasswordDialog(c.holder, detail, n_docs, on_submit=submit, parent=self)
        if dlg.exec() != PasswordDialog.Accepted or holder["cred"] is None:
            return None
        cred = holder["cred"]
        info = cred.info
        if c.thumbprint and c.thumbprint != info.thumbprint:
            QMessageBox.information(self, APP_NAME, f"Se usará un certificado distinto al anterior:\n{info.summary()}")
        c.thumbprint, c.holder, c.ca_name = info.thumbprint, info.signer.display_name, info.ca_name
        c.not_after = info.not_after.isoformat()
        self.save()
        self.cert_page.refresh()
        return cred

    def sign_documents(self, docs: list[dict]) -> None:
        if self._batch is not None and self._batch.isRunning():
            return
        files = [d["path"] for d in docs]
        if not files:
            return
        try:
            self.settings.placement.validate()
        except KipuError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        cred = self.unlock_certificate(len(files))
        if cred is None:
            return
        settings = copy.deepcopy(self.settings)
        manual = {d["path"]: d["manual"] for d in docs if d["manual"]}

        busy = QProgressDialog("Verificando el certificado (vigencia, entidad, revocación)…", None, 0, 0, self)
        busy.setWindowTitle(APP_NAME)
        busy.setWindowModality(Qt.WindowModal)
        busy.setMinimumDuration(0)
        busy.show()
        prep = FuncWorker(prepare_session, cred, settings, parent=self)

        def after_prepare(warnings, error) -> None:
            busy.close()
            if error is not None:
                cred.destroy()
                QMessageBox.critical(self, APP_NAME, f"No se puede firmar:\n\n{error}")
                return
            if warnings:
                ans = QMessageBox.warning(self, APP_NAME, "Avisos antes de firmar:\n\n• " + "\n• ".join(warnings)
                                          + "\n\n¿Desea continuar?", QMessageBox.Yes | QMessageBox.No)
                if ans != QMessageBox.Yes:
                    cred.destroy()
                    return
            self._run_batch(files, cred, settings, manual)

        prep.done.connect(after_prepare)
        prep.start()
        self._prep = prep

    def _run_batch(self, files, cred, settings, manual) -> None:
        dlg = QProgressDialog("Firmando…", "Cancelar", 0, len(files), self)
        dlg.setWindowTitle(APP_NAME)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        w = BatchWorker(files, cred, settings, self.trust, manual, self)
        dlg.canceled.connect(w.cancel.set)

        def on_progress(i, total, f, r) -> None:
            dlg.setValue(i)
            dlg.setLabelText(f"Firmando {min(i + 1, total)} de {total}\n{Path(f).name}")

        def on_done(results) -> None:
            cred.destroy()
            dlg.close()
            self.sign_page.mark_results(results)
            ResultsDialog(results, cred.info.signer.display_name, settings.output.open_folder_when_done
                          and any(r.output for r in results), self).exec()

        def on_fail(e) -> None:
            cred.destroy()
            dlg.close()
            QMessageBox.critical(self, APP_NAME, f"Error inesperado: {e}")

        w.progress.connect(on_progress)
        w.finished_ok.connect(on_done)
        w.failed.connect(on_fail)
        self._batch = w
        dlg.show()
        w.start()

    def closeEvent(self, e) -> None:
        if self._batch is not None and self._batch.isRunning():
            if QMessageBox.question(self, APP_NAME, "Hay una firma en curso. ¿Cancelar y salir?") != QMessageBox.Yes:
                e.ignore()
                return
            self._batch.cancel.set()
            self._batch.wait(10000)
        self.save()
        super().closeEvent(e)
