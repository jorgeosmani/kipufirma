"""Arranque de la aplicación gráfica con instancia única.

Si el usuario selecciona varios PDF en el Explorador y elige «Firmar con
KipuFirma», Windows lanza un proceso por archivo: el primero queda como
instancia principal y los demás le envían sus rutas por un canal local
(QLocalServer, accesible solo para el usuario actual) y terminan.
"""
from __future__ import annotations

import getpass
import logging
import sys

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from kipufirma import APP_NAME, APP_ORG, __version__
from kipufirma.core.config import load_settings
from kipufirma.core.logging_setup import setup_logging
from kipufirma.paths import resource_path

log = logging.getLogger(__name__)


def _server_name() -> str:
    user = "".join(ch for ch in getpass.getuser() if ch.isalnum()) or "usuario"
    return f"{APP_NAME}-{user}"


def _send_to_running(files: list[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(400):
        return False
    sock.write(QByteArray("\n".join(files).encode("utf-8")))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def run(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    setup_logging()
    app = QApplication([sys.argv[0], *[a for a in argv if a.startswith("-")]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(__version__)
    files = [a for a in argv if not a.startswith("-")]

    if _send_to_running(files):
        return 0
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    QLocalServer.removeServer(_server_name())
    server.listen(_server_name())

    from kipufirma.gui.main_window import MainWindow
    from kipufirma.gui.theme import apply_theme

    settings = load_settings()
    apply_theme(app, settings.ui.theme)
    icon = resource_path("icons", "kipufirma.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    try:
        win = MainWindow(settings)
    except Exception as e:  # p. ej. recursos dañados
        log.exception("No se pudo iniciar")
        QMessageBox.critical(None, APP_NAME, f"No se pudo iniciar {APP_NAME}:\n{e}")
        return 1

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        def read() -> None:
            data = bytes(conn.readAll()).decode("utf-8", "replace")
            win.open_files([p for p in data.splitlines() if p.strip()])
        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)
    win.show()
    if files:
        win.open_files(files)
    log.info("%s %s iniciado", APP_NAME, __version__)
    code = app.exec()
    server.close()
    return code


def main() -> int:
    """Punto de entrada para ``kipufirma-gui`` (sin consola)."""
    return run(sys.argv[1:])
