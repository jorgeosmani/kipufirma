# Cómo contribuir

¡Gracias por su interés! Este proyecto se rige por el
[Código de conducta](CODE_OF_CONDUCT.md).

## Preparar el entorno

```powershell
git clone https://github.com/jorgeosmani/kipufirma.git
cd kipufirma
powershell -ExecutionPolicy Bypass -File scripts\instalar_desarrollo.ps1
```

En Linux/macOS: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pip install -e . --no-deps`.

## Reglas de oro

1. **Nunca suba certificados reales, contraseñas ni documentos personales.**
   El `.gitignore` bloquea `*.p12`/`*.pfx`, pero revise `git status` antes de cada commit.
2. Todo cambio en firma, certificados o PDF necesita **pruebas automáticas**
   (`pytest`) y, si afecta el formato de firma, una **validación oficial**
   según [`docs/PRUEBAS_ACEPTACION.md`](docs/PRUEBAS_ACEPTACION.md).
3. El núcleo (`src/kipufirma/core`) **no importa Qt**.
4. Mensajes al usuario en español claro; errores como subclases de `KipuError`.
5. Nunca registre datos sensibles (use el filtro de `logging_setup.py`).
6. Cambios en `resources/trust/` solo mediante `tools/extraer_anclas_firmaec.py`,
   revisando el diff de `manifest.json` y explicando la procedencia en el PR.

## Flujo

1. Cree una rama: `git checkout -b feat/descripcion-corta`.
2. Ejecute `ruff check src tests` y `pytest -q` (con `QT_QPA_PLATFORM=offscreen` sin pantalla).
3. Actualice `CHANGELOG.md` (sección *Sin publicar*).
4. Abra el Pull Request completando la plantilla.

Mensajes de commit sugeridos: [Conventional Commits](https://www.conventionalcommits.org/es/)
(`feat:`, `fix:`, `docs:`, `test:`, `sec:`).

## Publicar una versión

1. Actualice `__version__` en `src/kipufirma/__init__.py` y `CHANGELOG.md`.
2. `git tag v1.2.3 && git push --tags`: el flujo *release* compila el
   ejecutable y el instalador y los adjunta al *release* con `SHA256SUMS.txt`.
