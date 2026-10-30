#!/usr/bin/env python3
"""Extrae los certificados raíz e intermedios de las ECEP ecuatorianas
embebidos en el código fuente de FirmaEC (clases ``*/cert/*.java``) y los
guarda como PEM junto a un manifiesto con huellas SHA-256.

Uso:
    python tools/extraer_anclas_firmaec.py <ruta-libreria-firmaec> src/kipufirma/resources/trust

La ruta debe apuntar a ``.../ec/gob/firmadigital/libreria/certificate/ec``
(o a una carpeta superior). Ejecútelo cuando FirmaEC publique una versión
con nuevas entidades certificadoras y REVISE el diff de ``manifest.json``
antes de hacer commit: estas anclas definen en quién confía la aplicación.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

APPEND_RE = re.compile(r'stringBuilder\.append\("([^"]*)"\)')


def pem_from_java(text: str) -> str | None:
    """Reconstruye el PEM a partir de las llamadas ``stringBuilder.append``."""
    pem = "".join(p.replace("\\n", "\n") for p in APPEND_RE.findall(text))
    return pem if "BEGIN CERTIFICATE" in pem else None


def main(src: Path, dst: Path) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    for old in dst.glob("*.pem"):
        old.unlink()
    manifest: list[dict] = []
    seen: set[str] = set()
    for java in sorted(src.rglob("*.java")):
        if "/cert/" not in java.as_posix():
            continue
        pem = pem_from_java(java.read_text(encoding="utf-8", errors="replace"))
        if not pem:
            continue
        cert = x509.load_pem_x509_certificate(pem.encode())
        der = cert.public_bytes(Encoding.DER)
        sha = hashlib.sha256(der).hexdigest()
        if sha in seen:
            continue
        seen.add(sha)
        entity = java.parent.parent.name
        name = f"{entity}__{java.stem}.pem"
        (dst / name).write_bytes(cert.public_bytes(Encoding.PEM))
        try:
            is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        except x509.ExtensionNotFound:
            is_ca = None
        manifest.append({
            "archivo": name,
            "entidad": entity,
            "clase_origen": java.stem,
            "sujeto": cert.subject.rfc4514_string(),
            "emisor": cert.issuer.rfc4514_string(),
            "autofirmado": cert.subject == cert.issuer,
            "es_ca": is_ca,
            "valido_desde": cert.not_valid_before_utc.isoformat(),
            "valido_hasta": cert.not_valid_after_utc.isoformat(),
            "sha256": sha,
        })
    manifest.sort(key=lambda m: (m["entidad"], m["archivo"]))
    (dst / "manifest.json").write_text(
        json.dumps(
            {
                "origen": "FirmaEC 5.3.0 - firmadigital-libreria (certificate/ec/*/cert)",
                "nota": "Generado con tools/extraer_anclas_firmaec.py. No editar a mano.",
                "certificados": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(manifest)} certificados exportados a {dst}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
