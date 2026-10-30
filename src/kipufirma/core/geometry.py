"""Geometría de página: rectángulos y conversión entre el espacio de usuario
del PDF (el que usa la firma) y el espacio *visual* (página tal como se ve,
ya girada según /Rotate, origen abajo-izquierda, en puntos).

Trabajar en espacio visual hace que "debajo de la palabra" o "esquina
inferior derecha" signifiquen lo que el usuario ve, aunque la página esté
girada 90/180/270 grados.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @staticmethod
    def from_points(ax: float, ay: float, bx: float, by: float) -> "Rect":
        return Rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def union(self, other: "Rect") -> "Rect":
        return Rect(min(self.x0, other.x0), min(self.y0, other.y0),
                    max(self.x1, other.x1), max(self.y1, other.y1))

    def moved(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def as_int_tuple(self) -> tuple[int, int, int, int]:
        return (round(self.x0), round(self.y0), round(self.x1), round(self.y1))


@dataclass(frozen=True)
class PageGeom:
    """Caja visible (CropBox) en espacio de usuario + rotación en grados."""
    left: float
    bottom: float
    right: float
    top: float
    rotation: int = 0

    @property
    def user_width(self) -> float:
        return self.right - self.left

    @property
    def user_height(self) -> float:
        return self.top - self.bottom

    @property
    def visual_size(self) -> tuple[float, float]:
        if self.rotation in (90, 270):
            return self.user_height, self.user_width
        return self.user_width, self.user_height

    def to_visual(self, x: float, y: float) -> tuple[float, float]:
        u, v = x - self.left, y - self.bottom
        w, h = self.user_width, self.user_height
        r = self.rotation % 360
        if r == 90:
            return v, w - u
        if r == 180:
            return w - u, h - v
        if r == 270:
            return h - v, u
        return u, v

    def to_user(self, X: float, Y: float) -> tuple[float, float]:
        w, h = self.user_width, self.user_height
        r = self.rotation % 360
        if r == 90:
            u, v = w - Y, X
        elif r == 180:
            u, v = w - X, h - Y
        elif r == 270:
            u, v = Y, h - X
        else:
            u, v = X, Y
        return u + self.left, v + self.bottom

    def rect_to_visual(self, r: Rect) -> Rect:
        a = self.to_visual(r.x0, r.y0)
        b = self.to_visual(r.x1, r.y1)
        return Rect.from_points(*a, *b)

    def rect_to_user(self, r: Rect) -> Rect:
        a = self.to_user(r.x0, r.y0)
        b = self.to_user(r.x1, r.y1)
        return Rect.from_points(*a, *b)

    def clamp_visual(self, r: Rect, margin: float = 2.0) -> Rect:
        """Desplaza (sin deformar) el rectángulo para que quede dentro de la página."""
        W, H = self.visual_size
        dx = dy = 0.0
        if r.x1 > W - margin:
            dx = (W - margin) - r.x1
        if r.x0 + dx < margin:
            dx = margin - r.x0
        if r.y1 > H - margin:
            dy = (H - margin) - r.y1
        if r.y0 + dy < margin:
            dy = margin - r.y0
        return r.moved(dx, dy)
