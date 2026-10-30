## Descripción

## Tipo de cambio
- [ ] Corrección  - [ ] Nueva función  - [ ] Seguridad  - [ ] Documentación

## Lista de verificación
- [ ] `pytest -q` y `ruff check src tests` pasan.
- [ ] No incluye certificados, contraseñas ni documentos reales.
- [ ] Si cambia el formato de firma: validé muestras en el validador oficial FirmaEC (docs/PRUEBAS_ACEPTACION.md).
- [ ] Si cambia `resources/trust/`: generado con `tools/extraer_anclas_firmaec.py` y procedencia explicada.
- [ ] Actualicé `CHANGELOG.md` y la documentación.
