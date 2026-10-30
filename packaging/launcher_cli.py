"""Punto de entrada del ejecutable de consola (kipufirma-cli.exe)."""
import sys

from kipufirma.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
