"""Interfaz de línea de comandos.

Ejemplos::

    kipufirma certificado --p12 "C:\\Firma\\mi_firma.p12"
    kipufirma firmar --p12 mi.p12 --entrada C:\\Docs --palabra "Firma del docente" --palabra "Firma:"
    kipufirma firmar --entrada contrato.pdf --pagina ultima --ancla inf-der --dx 60 --dy 80
    kipufirma verificar C:\\Docs\\firmados

La contraseña se pide de forma interactiva (sin eco) o se lee de la entrada
estándar con ``--clave-stdin``. Nunca se acepta como argumento: quedaría en
el historial de la consola y en la lista de procesos.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from kipufirma import APP_NAME, __version__

if TYPE_CHECKING:
    from kipufirma.core.secrets import SecretBuffer

SUBCOMMANDS = ("firmar", "verificar", "certificado")


def _collect(paths: list[str], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(x for x in (p.rglob("*") if recursive else p.iterdir())
                          if x.suffix.lower() == ".pdf" and x.is_file())
        elif p.suffix.lower() == ".pdf":
            out.append(p)
    return out


def _password(args) -> "SecretBuffer":
    from kipufirma.core.secrets import SecretBuffer
    if args.clave_stdin:
        return SecretBuffer(sys.stdin.readline().rstrip("\r\n"))
    return SecretBuffer(getpass.getpass("Contraseña del certificado: "))


def _p12_path(args, settings) -> Path:
    p = args.p12 or settings.certificate.path
    if not p:
        sys.exit("Indique el certificado con --p12 (o configúrelo en la aplicación).")
    return Path(p)


def cmd_certificado(args) -> int:
    from kipufirma.core.certificate import check_usable, load_credential
    from kipufirma.core.config import load_settings
    from kipufirma.core.errors import KipuError
    from kipufirma.core.trust import TrustStore
    settings = load_settings()
    try:
        cred = load_credential(_p12_path(args, settings), _password(args), TrustStore.default())
    except KipuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    i = cred.info
    print(f"Titular:        {i.signer.display_name}")
    print(f"Identificación: {i.signer.masked_id() or '-'}")
    print(f"Entidad:        {i.ca_name} ({'reconocida' if i.ca_recognized else 'NO reconocida'})")
    print(f"Vigencia:       {i.not_before:%d/%m/%Y} – {i.not_after:%d/%m/%Y} ({i.days_left()} días)")
    print(f"Uso de clave:   {i.key_usage_text}")
    print(f"Cadena:         {'confiable' if cred.chain and cred.chain.trusted else 'no confiable'}")
    print(f"Huella SHA-256: {i.thumbprint}")
    try:
        for w in check_usable(cred, require_trusted_chain=False):
            print(f"Aviso: {w}")
    except KipuError as e:
        print(f"NO APTO PARA FIRMAR: {e}")
        return 1
    finally:
        cred.destroy()
    return 0


def cmd_firmar(args) -> int:
    from kipufirma.core.batch import STATUS_ERROR, export_report, prepare_session, run_batch
    from kipufirma.core.certificate import load_credential
    from kipufirma.core.config import load_settings
    from kipufirma.core.errors import KipuError
    from kipufirma.core.trust import TrustStore
    settings = load_settings()
    files = _collect(args.entrada, args.recursivo)
    if not files:
        print("No se encontraron archivos PDF.", file=sys.stderr)
        return 2
    rule = settings.placement
    if args.palabra:
        rule.mode = "palabra"
        rule.keyword.keywords = args.palabra
        rule.keyword.position = args.posicion
        rule.keyword.occurrence = args.ocurrencia
        rule.keyword.fallback = args.si_no_encuentra
    elif args.invisible:
        rule.mode = "invisible"
    elif args.pagina or args.ancla or args.dx is not None or args.dy is not None:
        rule.mode = "fija"
    if args.pagina:
        if args.pagina.isdigit():
            rule.fixed.page_mode, rule.fixed.page_number = "numero", int(args.pagina)
        else:
            rule.fixed.page_mode = args.pagina
    if args.ancla:
        rule.fixed.anchor = args.ancla
    if args.dx is not None:
        rule.fixed.dx = args.dx
    if args.dy is not None:
        rule.fixed.dy = args.dy
    if args.razon is not None:
        settings.signing.reason = args.razon
    if args.ubicacion is not None:
        settings.signing.location = args.ubicacion
    if args.salida:
        settings.output.mode, settings.output.folder = "carpeta", args.salida
    rule.validate()
    trust = TrustStore.default()
    try:
        cred = load_credential(_p12_path(args, settings), _password(args), trust)
        for w in prepare_session(cred, settings):
            print(f"Aviso: {w}")
    except KipuError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    def progress(i, total, f, r):
        if r is not None:
            print(f"[{i}/{total}] {r.status:<20} {f.name}  {r.message}")

    try:
        results = run_batch(files, cred, settings, trust, progress=progress)
    finally:
        cred.destroy()
    if args.informe:
        export_report(results, Path(args.informe), cred.info.signer.display_name)
    ok = sum(r.status != STATUS_ERROR for r in results)
    print(f"\nListo: {ok}/{len(results)} sin errores.")
    return 0 if ok == len(results) else 1


def cmd_verificar(args) -> int:
    from kipufirma.core.trust import TrustStore
    from kipufirma.core.verify import verify_pdf_bytes
    trust = TrustStore.default()
    bad = 0
    for f in _collect(args.entrada, args.recursivo):
        reps = verify_pdf_bytes(f.read_bytes(), trust, allow_fetching=args.en_linea)
        print(f"\n{f}")
        if not reps:
            print("  (sin firmas)")
        for r in reps:
            estado = "VÁLIDA" if r.ok else "INVÁLIDA"
            conf = "entidad reconocida" if r.trusted else "entidad NO reconocida"
            fecha = r.signing_time.astimezone().strftime("%d/%m/%Y %H:%M") if r.signing_time else "-"
            print(f"  {estado:<9} {r.signer_name} · {r.ca_name} · {fecha} · {conf}")
            bad += not r.ok
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=APP_NAME.lower(), description=f"{APP_NAME} {__version__}: firma electrónica de PDF (Ecuador)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("certificado", help="Muestra y valida el certificado .p12")
    c.add_argument("--p12")
    c.add_argument("--clave-stdin", action="store_true")
    c.set_defaults(func=cmd_certificado)

    f = sub.add_parser("firmar", help="Firma uno o varios PDF")
    f.add_argument("entrada", nargs="+", help="Archivos PDF o carpetas")
    f.add_argument("--p12")
    f.add_argument("--clave-stdin", action="store_true")
    f.add_argument("-r", "--recursivo", action="store_true")
    f.add_argument("--palabra", action="append", help="Palabra clave (repetible, en orden de prioridad)")
    f.add_argument("--posicion", default="debajo", choices=["debajo", "encima", "derecha", "izquierda", "sobre"])
    f.add_argument("--ocurrencia", default="ultima", choices=["primera", "ultima", "todas"])
    f.add_argument("--si-no-encuentra", default="fija", choices=["omitir", "fija", "invisible"])
    f.add_argument("--pagina", help="primera | ultima | todas | número")
    f.add_argument("--ancla", choices=["inf-der", "inf-izq", "sup-der", "sup-izq"])
    f.add_argument("--dx", type=float)
    f.add_argument("--dy", type=float)
    f.add_argument("--invisible", action="store_true")
    f.add_argument("--razon")
    f.add_argument("--ubicacion")
    f.add_argument("--salida", help="Carpeta de salida")
    f.add_argument("--informe", help="Ruta del informe CSV")
    f.set_defaults(func=cmd_firmar)

    v = sub.add_parser("verificar", help="Verifica las firmas de PDF")
    v.add_argument("entrada", nargs="+")
    v.add_argument("-r", "--recursivo", action="store_true")
    v.add_argument("--en-linea", action="store_true", help="Consultar revocación en línea")
    v.set_defaults(func=cmd_verificar)
    return p


def main(argv: list[str] | None = None) -> int:
    from kipufirma.core.logging_setup import setup_logging
    setup_logging()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
