"""Permite ``python -m kipufirma``: abre la interfaz gráfica, o la CLI si
el primer argumento es un subcomando (firmar, verificar, certificado)."""
import sys

from kipufirma.cli import SUBCOMMANDS


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
        from kipufirma.cli import main as cli_main
        return cli_main(sys.argv[1:])
    from kipufirma.gui.app import run
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
