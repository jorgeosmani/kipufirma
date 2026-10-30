"""Vista previa de páginas con colocación interactiva de la firma.

* Un **sello fantasma** (semitransparente, con QR y nombre) sigue al ratón y
  muestra exactamente dónde y cómo quedará la firma.
* **Clic** = la firma se asienta ahí, al instante (sin esperar análisis).
* **Arrastrar** = dibuja un recuadro de tamaño propio (si es muy pequeño se
  usa el tamaño configurado, para que el texto siga siendo legible).
* **Flechas** = mueven la firma colocada 1 pt (con Mayús, 10 pt) para un
  ajuste fino.

Las coordenadas se emiten en espacio visual (puntos, origen abajo-izquierda),
igual que el núcleo.
"""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from kipufirma.core.geometry import Rect

MARGIN_PT = 2.0          # mismo margen que PageGeom.clamp_visual


def bitmap_to_qimage(bmp) -> QImage:
    """Convierte el bitmap de PDFium en QImage sin depender de Pillow.
    Con ``rev_byteorder=True`` los bytes vienen como RGB/RGBX, que Qt lee tal cual."""
    fmt = {4: QImage.Format_RGBX8888, 3: QImage.Format_RGB888, 1: QImage.Format_Grayscale8}[bmp.n_channels]
    data = bytes(bmp.buffer)
    img = QImage(data, bmp.width, bmp.height, bmp.stride, fmt).copy()   # copy: se independiza del búfer
    bmp.close()
    return img


class StampItem(QGraphicsItem):
    """Maqueta del sello (QR + «Firmado electrónicamente por:» + nombre)."""

    # Patrón fijo de «módulos» para que la maqueta parezca un QR.
    _MODULES = [(r, c) for r in range(9) for c in range(9) if (r * 7 + c * 3 + r * c) % 5 in (0, 2)]

    def __init__(self, rect: QRectF, name: str, ghost: bool) -> None:
        super().__init__()
        self._rect = QRectF(rect)
        self.name = name or "SU NOMBRE"
        self.ghost = ghost
        self.setZValue(10 if ghost else 5)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setData(0, "ghost" if ghost else "box")

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect)
        self.update()

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-2, -2, 2, 2)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        r = self._rect
        p.setRenderHint(QPainter.Antialiasing)
        if self.ghost:
            p.setOpacity(0.75)
            p.setBrush(QColor(255, 255, 255, 215))
            p.setPen(QPen(QColor("#F2B705"), 1.6, Qt.DashLine))
        else:
            p.setBrush(QColor(255, 255, 255, 235))
            p.setPen(QPen(QColor("#1B8A5A"), 1.8))
        p.drawRect(r)
        side = min(r.height() - 2, r.width() * 0.4)
        if side > 4:
            qx, qy = r.left() + 1, r.top() + (r.height() - side) / 2
            cell = side / 9
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 20, 20))
            for (row, col) in self._MODULES:
                p.drawRect(QRectF(qx + col * cell, qy + row * cell, cell, cell))
            for (fr, fc) in ((0, 0), (0, 6), (6, 0)):      # cuadros de posición del QR
                p.drawRect(QRectF(qx + fc * cell, qy + fr * cell, cell * 3, cell * 3))
            tx = qx + side + max(2.0, r.height() * 0.08)
        else:
            tx = r.left() + 2
        tw = r.right() - tx - 1
        if tw < 6:
            return
        header = "Firmado electrónicamente por:"
        small = QFont("Courier New")
        px = max(int(r.height() * 0.14), 4)
        small.setPixelSize(px)
        while px > 4 and QFontMetricsF(small).horizontalAdvance(header) > tw:   # que quepa completo
            px -= 1
            small.setPixelSize(px)
        big = QFont("Courier New")
        big.setBold(True)
        big.setPixelSize(max(int(r.height() * 0.21), 6))
        p.setPen(QColor(20, 20, 20))
        p.setFont(small)
        head_h = small.pixelSize() * 1.3
        top = r.top() + r.height() * 0.12
        p.drawText(QRectF(tx, top, tw, head_h), Qt.AlignLeft | Qt.AlignVCenter, header)
        p.setFont(big)
        p.drawText(QRectF(tx, top + head_h, tw, r.bottom() - top - head_h - 1),
                   Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.name)


class PreviewView(QGraphicsView):
    rectChosen = Signal(int, object)          # (página, Rect visual)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#5B6573"))
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._doc: pdfium.PdfDocument | None = None
        self.path: Path | None = None
        self.page_index = 0
        self.page_count = 0
        self._scale = 1.0
        self.page_w = 0.0
        self.page_h = 0.0
        self._boxes: list[tuple[int, Rect, str]] = []
        self._drag_start: QPointF | None = None
        self._drag_item = None
        self._ghost: StampItem | None = None
        self._last: tuple[int, Rect] | None = None
        self.stamp_size = (110.0, 36.0)
        self.signer_name = ""
        self.interactive = True
        self.setMinimumWidth(320)
        self._placeholder("Seleccione un documento para ver la vista previa")

    # --- documento ------------------------------------------------------
    def _placeholder(self, text: str) -> None:
        sc = self.scene()
        sc.clear()
        self._ghost = None
        item = sc.addSimpleText(text)
        item.setBrush(QColor("#E6EBF1"))
        sc.setSceneRect(item.boundingRect().adjusted(-40, -40, 40, 40))

    def set_document(self, path: Path | None, page_index: int | None = None) -> None:
        if path is not None and self._doc is not None and path == self.path:
            if page_index is not None and page_index != self.page_index:
                self.page_index = max(0, min(page_index, self.page_count - 1))
                self.render_page()
            return                                   # mismo documento: no se vuelve a abrir
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self.path = path
        self._last = None
        if path is None:
            self.page_count = 0
            self._placeholder("Seleccione un documento para ver la vista previa")
            return
        try:
            self._doc = pdfium.PdfDocument(str(path))
            self.page_count = len(self._doc)
        except Exception as e:
            self.page_count = 0
            self._placeholder(f"No se puede mostrar: {e}")
            return
        self.page_index = self.page_count - 1 if page_index is None else max(0, min(page_index, self.page_count - 1))
        self.render_page()

    def set_boxes(self, boxes: list[tuple[int, Rect, str]]) -> None:
        self._boxes = boxes
        self._draw_boxes()

    def go(self, delta: int) -> None:
        if self.page_count:
            self.page_index = max(0, min(self.page_index + delta, self.page_count - 1))
            self.render_page()

    def render_page(self) -> None:
        if self._doc is None:
            return
        page = self._doc[self.page_index]
        w, h = page.get_size()
        avail = max(self.viewport().width() - 24, 200)
        avail_h = max(self.viewport().height() - 24, 200)
        self._scale = max(min(avail / w, avail_h / h), 0.15)
        dpr = self.devicePixelRatioF()
        img = bitmap_to_qimage(page.render(scale=self._scale * dpr, rev_byteorder=True, prefer_bgrx=True))
        page.close()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        self.page_w, self.page_h = w, h
        sc = self.scene()
        sc.clear()
        self._ghost = None
        item = QGraphicsPixmapItem(pix)
        item.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        sc.addItem(item)
        sc.setSceneRect(QRectF(-8, -8, w * self._scale + 16, h * self._scale + 16))
        self._draw_boxes()

    # --- conversión ---------------------------------------------------------
    def _to_scene(self, r: Rect) -> QRectF:
        s = self._scale
        return QRectF(r.x0 * s, (self.page_h - r.y1) * s, r.width * s, r.height * s)

    def _to_visual(self, a: QPointF, b: QPointF) -> Rect:
        s = self._scale
        return Rect.from_points(a.x() / s, self.page_h - a.y() / s, b.x() / s, self.page_h - b.y() / s)

    def _clamp(self, r: Rect) -> Rect:
        dx = dy = 0.0
        if r.x1 > self.page_w - MARGIN_PT:
            dx = self.page_w - MARGIN_PT - r.x1
        if r.x0 + dx < MARGIN_PT:
            dx = MARGIN_PT - r.x0
        if r.y1 > self.page_h - MARGIN_PT:
            dy = self.page_h - MARGIN_PT - r.y1
        if r.y0 + dy < MARGIN_PT:
            dy = MARGIN_PT - r.y0
        return r.moved(dx, dy)

    def stamp_rect_at(self, scene_pos: QPointF) -> Rect:
        """Recuadro del sello centrado en el puntero (en puntos), dentro de la página."""
        w, h = self.stamp_size
        s = self._scale
        cx, cy = scene_pos.x() / s, self.page_h - scene_pos.y() / s
        return self._clamp(Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))

    def _draw_boxes(self) -> None:
        if self._doc is None:
            return
        sc = self.scene()
        for it in list(sc.items()):
            if it.data(0) == "box":
                sc.removeItem(it)
        for page, rect, _label in self._boxes:
            if page == self.page_index:
                sc.addItem(StampItem(self._to_scene(rect), self.signer_name, ghost=False))

    def show_placed(self, page: int, rect: Rect) -> None:
        """Dibuja de inmediato la firma recién colocada (sin esperar el análisis)."""
        self._last = (page, rect)
        self._boxes = [b for b in self._boxes if b[0] != page] + [(page, rect, "Firma")]
        self._draw_boxes()

    # --- fantasma -------------------------------------------------------------
    def _update_ghost(self, scene_pos: QPointF | None) -> None:
        if self._doc is None or not self.interactive or scene_pos is None:
            if self._ghost is not None:
                self._ghost.hide()
            return
        inside = -10 <= scene_pos.x() <= self.page_w * self._scale + 10 and \
            -10 <= scene_pos.y() <= self.page_h * self._scale + 10
        if not inside:
            if self._ghost is not None:
                self._ghost.hide()
            return
        rect = self._to_scene(self.stamp_rect_at(scene_pos))
        if self._ghost is None:
            self._ghost = StampItem(rect, self.signer_name, ghost=True)
            self.scene().addItem(self._ghost)
        self._ghost.name = self.signer_name or "SU NOMBRE"
        self._ghost.set_rect(rect)
        self._ghost.show()
        self.viewport().setCursor(Qt.CrossCursor)

    def leaveEvent(self, e) -> None:
        self._update_ghost(None)
        super().leaveEvent(e)

    # --- eventos -----------------------------------------------------------
    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self._doc is not None:
            self.render_page()

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.ControlModifier:
            return
        self.go(-1 if e.angleDelta().y() > 0 else 1)
        self.pageChanged()

    def pageChanged(self) -> None:
        """Gancho para que la ventana actualice la etiqueta de página."""

    def mousePressEvent(self, e) -> None:
        if self._doc is None or not self.interactive or e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        self.setFocus()
        self._drag_start = self.mapToScene(e.position().toPoint())

    def mouseMoveEvent(self, e) -> None:
        pos = self.mapToScene(e.position().toPoint())
        if self._drag_start is not None and (pos - self._drag_start).manhattanLength() >= 8:
            if self._ghost is not None:
                self._ghost.hide()
            if self._drag_item is None:
                self._drag_item = self.scene().addRect(QRectF(), QPen(QColor("#F2B705"), 2),
                                                       QBrush(QColor(242, 183, 5, 60)))
            self._drag_item.setRect(QRectF(self._drag_start, pos).normalized())
        elif self._drag_start is None:
            self._update_ghost(pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._drag_start is None:
            return super().mouseReleaseEvent(e)
        end = self.mapToScene(e.position().toPoint())
        start = self._drag_start
        self._drag_start = None
        if self._drag_item is not None:
            self.scene().removeItem(self._drag_item)
            self._drag_item = None
        if (end - start).manhattanLength() < 8:          # clic: exactamente donde estaba el fantasma
            rect = self.stamp_rect_at(end)
        else:
            rect = self._to_visual(start, end)
            w, h = self.stamp_size
            if rect.width < max(60.0, w * 0.5) or rect.height < max(20.0, h * 0.5):
                cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
                rect = Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            rect = self._clamp(rect)
        self.show_placed(self.page_index, rect)
        self.rectChosen.emit(self.page_index, rect)
        self._update_ghost(end)

    def keyPressEvent(self, e) -> None:
        if self._last is None or self._last[0] != self.page_index:
            return super().keyPressEvent(e)
        step = 10.0 if e.modifiers() & Qt.ShiftModifier else 1.0
        moves = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, step), Qt.Key_Down: (0, -step)}
        if e.key() not in moves:
            return super().keyPressEvent(e)
        dx, dy = moves[e.key()]
        rect = self._clamp(self._last[1].moved(dx, dy))
        self.show_placed(self.page_index, rect)
        self.rectChosen.emit(self.page_index, rect)
