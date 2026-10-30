#!/usr/bin/env python3
"""Envía PDF firmados al servicio PÚBLICO de validación de MINTEL y muestra
el resultado. Úselo para las pruebas de aceptación (docs/PRUEBAS_ACEPTACION.md).

ATENCIÓN - PRIVACIDAD: el documento COMPLETO se envía a un servidor externo
(ws.firmadigital.gob.ec). Use documentos de prueba, no información sensible.
Por eso esta herramienta está FUERA de la aplicación y pide confirmación.

El endpoint proviene del código del servicio FirmaEC
(ServicioValidacionPdfRest, ruta /validacionavanzadapdf); puede cambiar sin
aviso. Si falla, use el validador de la aplicación FirmaEC de escritorio.

Uso:
    python scripts/validar_con_mintel.py documento-firmado.pdf [...]
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

URL = "https://ws.firmadigital.gob.ec/servicio/validacionavanzadapdf"


def validar(path: Path) -> dict:
    body = base64.b64encode(path.read_bytes())
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "text/plain; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def main(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 2
    print("Se enviarán los documentos completos a", URL)
    if input("¿Confirma que son documentos de PRUEBA? (escriba SI): ").strip().upper() != "SI":
        return 1
    rc = 0
    for a in args:
        p = Path(a)
        try:
            res = validar(p)
        except Exception as e:
            print(f"{p.name}: error de conexión o respuesta: {e}")
            rc = 1
            continue
        ok = res.get("firmasValidas") and res.get("integridadDocumento")
        print(f"\n{p.name}: {'VÁLIDO' if ok else 'NO VÁLIDO'}")
        for c in res.get("certificado") or []:
            print(f"  - {c.get('emitidoPara')} | {c.get('entidadCertificadora')} | firma: {c.get('fechaFirma')}"
                  f" | íntegra: {c.get('integridadFirma')} | vigente: {c.get('certificadoVigente')}")
        if res.get("error"):
            print("  error:", res["error"])
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
