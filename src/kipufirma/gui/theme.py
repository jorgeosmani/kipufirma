"""Tema visual: estilo Fusion con paleta clara/oscura y hoja de estilos."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

PRIMARY = "#1F4E79"
PRIMARY_HOVER = "#2A6299"
ACCENT = "#F2B705"
OK = "#2E7D32"
WARN = "#B26A00"
ERR = "#C62828"


def is_dark(theme: str) -> bool:
    if theme == "oscuro":
        return True
    if theme == "claro":
        return False
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app: QApplication, theme: str = "sistema") -> None:
    app.setStyle("Fusion")
    dark = is_dark(theme)
    p = QPalette()
    if dark:
        base, alt, text, window, mid = "#1E1F22", "#26282C", "#E8EAED", "#18191C", "#3A3D42"
    else:
        base, alt, text, window, mid = "#FFFFFF", "#F4F6F9", "#1C2430", "#EEF1F5", "#C9D1DC"
    p.setColor(QPalette.Window, QColor(window))
    p.setColor(QPalette.WindowText, QColor(text))
    p.setColor(QPalette.Base, QColor(base))
    p.setColor(QPalette.AlternateBase, QColor(alt))
    p.setColor(QPalette.Text, QColor(text))
    p.setColor(QPalette.Button, QColor(alt))
    p.setColor(QPalette.ButtonText, QColor(text))
    p.setColor(QPalette.Highlight, QColor(PRIMARY))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ToolTipBase, QColor(base))
    p.setColor(QPalette.ToolTipText, QColor(text))
    p.setColor(QPalette.PlaceholderText, QColor("#8A94A3"))
    p.setColor(QPalette.Mid, QColor(mid))
    app.setPalette(p)
    sidebar = "#14324F" if not dark else "#101215"
    app.setStyleSheet(f"""
        QWidget {{ font-size: 10pt; }}
        #Sidebar {{ background: {sidebar}; border: none; color: #DDE6F0; padding-top: 8px; outline: 0; }}
        #Sidebar::item {{ padding: 12px 16px; border-left: 3px solid transparent; }}
        #Sidebar::item:selected {{ background: rgba(255,255,255,0.10); border-left: 3px solid {ACCENT}; color: white; }}
        #Sidebar::item:hover {{ background: rgba(255,255,255,0.06); }}
        #Brand {{ background: {sidebar}; color: white; font-size: 15pt; font-weight: 700; padding: 16px; }}
        #Card {{ background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }}
        #CertBanner {{ background: palette(base); border: 1px solid palette(mid); border-radius: 10px; padding: 6px; }}
        #Title {{ font-size: 14pt; font-weight: 600; }}
        #Muted {{ color: #7A8594; }}
        QPushButton {{ padding: 6px 12px; border-radius: 6px; border: 1px solid palette(mid); background: palette(button); }}
        QPushButton:hover {{ border-color: {PRIMARY}; }}
        QPushButton#Primary {{ background: {PRIMARY}; color: white; border: none; font-weight: 600; padding: 10px 18px; font-size: 11pt; }}
        QPushButton#Primary:hover {{ background: {PRIMARY_HOVER}; }}
        QPushButton#Primary:disabled {{ background: #8FA3B8; }}
        QGroupBox {{ border: 1px solid palette(mid); border-radius: 8px; margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
        QTableWidget {{ gridline-color: palette(mid); border-radius: 6px; }}
        QHeaderView::section {{ padding: 6px; border: none; border-bottom: 1px solid palette(mid); background: palette(alternate-base); font-weight: 600; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ padding: 4px 6px; border: 1px solid palette(mid); border-radius: 5px; background: palette(base); }}
        QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {PRIMARY}; }}
    """)
