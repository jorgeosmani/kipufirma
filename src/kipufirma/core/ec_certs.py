"""Identificación de la Entidad de Certificación (ECEP) y extracción de los
datos del firmante a partir de certificados emitidos en Ecuador.

Las ECEP ecuatorianas publican los datos del titular de dos formas:

1. **Extensiones propietarias (esquema "EXT")**, heredado del Banco Central:
   ``1.3.6.1.4.1.<arco>.3.<n>`` donde ``n`` es 1=cédula, 2=nombres,
   3=primer apellido, 4=segundo apellido, 5=cargo, 6=institución,
   7=dirección, 8=teléfono, 9=ciudad, 10=razón social, 11=RUC, 12=país.
2. **Atributos estándar del sujeto (esquema "SUBJ")**: serialNumber
   (2.5.4.5), givenName (2.5.4.42), surname (2.5.4.4), title (2.5.4.12),
   organizationIdentifier (2.5.4.97), CN, O.

El mapeo se obtuvo del análisis de ``CertEcUtils`` y las clases
``CertificadoExt*`` de FirmaEC 5.3.0. Esta implementación es genérica: no
depende del arco de cada entidad, de modo que funciona con entidades nuevas
que sigan cualquiera de los dos esquemas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.x509.oid import NameOID

# Nombre de organización del emisor (O) -> nombre comercial mostrado.
KNOWN_CAS: dict[str, str] = {
    "ALPHA TECHNOLOGIES CIA. LTDA.": "Alpha Technologies",
    "ANFAC AUTORIDAD DE CERTIFICACION ECUADOR C.A.": "ANF AC Ecuador",
    "ANFAC AUTORIDAD DE CERTIFICACION ECUADOR CA": "ANF AC Ecuador",
    "APPFIRMAS S.A.": "AppFirmas",
    "APPFIRMAS S.A. SUB CA": "AppFirmas",
    "ARGOSDATA CERTIFICACIÓN DE INFORMACIÓN Y SERVICIOS RELACIONADOS": "ArgosData",
    "ARGOSDATA": "ArgosData",
    "BANCO CENTRAL DEL ECUADOR": "Banco Central del Ecuador",
    "CONSEJO DE LA JUDICATURA": "Consejo de la Judicatura",
    "CORPNEWBEST CIA. LTDA.": "CorpNewBest",
    "DARKCAM S.A.": "Darkcam",
    "DATILMEDIA S.A.": "Datil",
    "DIRECCIÓN GENERAL DE REGISTRO CIVIL, IDENTIFICACIÓN Y CEDULACIÓN": "Registro Civil (DIGERCIC)",
    "ECLIPSOFT S.A.": "Eclipsoft",
    "FIRMASEGURA S.A.S.": "FirmaSegura",
    "LAZZATE CIA. LTDA.": "Lazzate",
    "LETMI ECUADOR S.A.": "Letmi",
    "PRIMECORELAT S.A.S. B.I.C.": "PrimeCoreLat",
    "SECURITY DATA SEGURIDAD EN DATOS Y FIRMA DIGITAL S.A.": "Security Data",
    "SECURITY DATA": "Security Data",
    "UANATACA ECUADOR S.A.": "Uanataca",
    "UANATACA S.A.": "Uanataca",
}

_EXT_RE = re.compile(r"^1\.3\.6\.1\.4\.1\.(\d+)\.3\.(\d+)$")
_EXT_FIELDS = {
    1: "cedula", 2: "nombres", 3: "apellido1", 4: "apellido2", 5: "cargo",
    6: "institucion", 9: "ciudad", 10: "razon_social", 11: "ruc",
}
_ORG_IDENTIFIER = x509.ObjectIdentifier("2.5.4.97")


@dataclass
class SignerData:
    cedula: str = ""
    nombres: str = ""
    apellidos: str = ""
    ruc: str = ""
    razon_social: str = ""
    cargo: str = ""
    institucion: str = ""
    ciudad: str = ""
    common_name: str = ""
    esquema: str = ""          # "EXT", "SUBJ" o "CN"
    extras: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Nombre que se imprime en el sello, con la misma regla que FirmaEC:
        nombres + apellidos si hay cédula; si no, razón social; si no, CN."""
        full = f"{self.nombres} {self.apellidos}".strip()
        if self.cedula and full:
            name = full
        elif self.razon_social:
            name = self.razon_social
        else:
            name = full or self.common_name
        return " ".join(name.split()).upper()

    def masked_id(self) -> str:
        """Cédula/RUC enmascarado para registros: 17******78."""
        v = self.cedula or self.ruc
        return v[:2] + "*" * max(len(v) - 4, 0) + v[-2:] if len(v) > 4 else ""


def _attr(name: x509.Name, oid) -> str:
    vals = name.get_attributes_for_oid(oid)
    return str(vals[0].value).strip() if vals else ""


def issuer_organization(cert: x509.Certificate) -> str:
    return _attr(cert.issuer, NameOID.ORGANIZATION_NAME)


def identify_ca(cert: x509.Certificate) -> tuple[str, bool]:
    """Devuelve (nombre de la entidad, reconocida). Igual criterio que FirmaEC:
    por la organización (O) del emisor."""
    org = issuer_organization(cert).upper()
    if org in KNOWN_CAS:
        if org == "UANATACA S.A." and _attr(cert.issuer, NameOID.COMMON_NAME).upper() == "UANATACA CA1 2016":
            return "Eclipsoft", True
        return KNOWN_CAS[org], True
    for key, nice in KNOWN_CAS.items():
        if key in org and len(key) > 10:
            return nice, True
    return org or cert.issuer.rfc4514_string(), False


def decode_der_string(raw: bytes) -> str:
    """Decodifica un string ASN.1 DER simple (UTF8, Printable, IA5, BMP, T61)."""
    if len(raw) < 2:
        return raw.decode("utf-8", "replace")
    tag, length, pos = raw[0], raw[1], 2
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(raw[2:2 + n], "big")
        pos = 2 + n
    body = raw[pos:pos + length]
    if tag == 0x1E:
        return body.decode("utf-16-be", "replace")
    if tag in (0x14, 0x1A):
        return body.decode("latin-1", "replace")
    if tag in (0x0C, 0x13, 0x16, 0x1A):
        return body.decode("utf-8", "replace")
    return raw.decode("utf-8", "replace")


def _digits(value: str, sizes: tuple[int, ...] = (13, 10)) -> str:
    """'IDCEC-1712345678' -> '1712345678'; 'VATEC-1790012345001' -> RUC."""
    for size in sizes:
        m = re.search(rf"(?<!\d)\d{{{size}}}(?!\d)", value)
        if m:
            return m.group(0)
    return value.strip()


def extract_signer_data(cert: x509.Certificate) -> SignerData:
    data = SignerData(common_name=_attr(cert.subject, NameOID.COMMON_NAME))

    # 1) Esquema EXT (extensiones propietarias)
    ext_values: dict[str, str] = {}
    for ext in cert.extensions:
        m = _EXT_RE.match(ext.oid.dotted_string)
        if not m or not isinstance(ext.value, x509.UnrecognizedExtension):
            continue
        key = _EXT_FIELDS.get(int(m.group(2)))
        if key:
            text = decode_der_string(ext.value.value).strip()
            if text:
                ext_values[key] = text
    if ext_values:
        data.esquema = "EXT"
        data.cedula = ext_values.get("cedula", "")
        data.nombres = ext_values.get("nombres", "")
        data.apellidos = " ".join(
            v for v in (ext_values.get("apellido1", ""), ext_values.get("apellido2", "")) if v
        )
        data.cargo = ext_values.get("cargo", "")
        data.institucion = ext_values.get("institucion", "")
        data.ciudad = ext_values.get("ciudad", "")
        data.razon_social = ext_values.get("razon_social", "")
        data.ruc = ext_values.get("ruc", "")

    # 2) Esquema SUBJ (atributos estándar) para completar lo que falte
    subj = cert.subject
    serial = _attr(subj, NameOID.SERIAL_NUMBER)
    given = _attr(subj, NameOID.GIVEN_NAME)
    surname = _attr(subj, NameOID.SURNAME)
    if not data.esquema and (serial or given or surname):
        data.esquema = "SUBJ"
    data.cedula = data.cedula or (_digits(serial, (10, 13)) if serial else "")
    data.nombres = data.nombres or given
    data.apellidos = data.apellidos or surname
    data.cargo = data.cargo or _attr(subj, NameOID.TITLE)
    data.ciudad = data.ciudad or _attr(subj, NameOID.LOCALITY_NAME)
    org_id = _attr(subj, _ORG_IDENTIFIER)
    data.ruc = data.ruc or (_digits(org_id, (13,)) if org_id else "")
    if data.ruc or org_id:
        data.razon_social = data.razon_social or _attr(subj, NameOID.ORGANIZATION_NAME)

    # 3) Último recurso: CN
    if not (data.nombres or data.apellidos or data.razon_social):
        data.esquema = data.esquema or "CN"
    return data
