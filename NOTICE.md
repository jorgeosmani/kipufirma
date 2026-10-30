# Avisos y atribuciones

**KipuFirma** — Copyright (C) 2026 Jorge Osmani Ordonez Ordonez y contribuidores.
Licencia: GNU Affero General Public License v3.0 o posterior (ver `LICENSE`).

## FirmaEC

Este proyecto se basa en el estudio de **FirmaEC**, software libre del
Ministerio de Telecomunicaciones y de la Sociedad de la Información (MINTEL)
del Ecuador, con aportes de Soporte Libre y SERCOP:

* `firmadigital-libreria` — AGPL-3.0 (repositorio oficial: `minka.gob.ec/mintel/ge/firmaec`).
* Aplicación de escritorio `firmador` — GPL-3.0.

Se tomaron de FirmaEC, como datos y especificación de compatibilidad:

* Los certificados raíz e intermedios de las Entidades de Certificación
  ecuatorianas (`src/kipufirma/resources/trust/`, generados con
  `tools/extraer_anclas_firmaec.py`; procedencia en `manifest.json`).
* El mapeo de OID de los datos del titular (esquemas EXT y SUBJ).
* El formato de la firma (adbe.pkcs7.detached, SHA-512) y el contenido del QR.

Referencias de estudio: `davidcanar/firmaec` (reconstrucción de FirmaEC 5.3.0),
`sarmientodeveloper/firmaec`, `fachamorro/Firmaec` y `XaviMontero/firmaec.js`.

«FirmaEC» es una marca y un servicio del Gobierno del Ecuador. KipuFirma
**no es un producto oficial** ni está avalado por MINTEL.

## Componentes de terceros

| Componente | Licencia |
|---|---|
| pyHanko, pyhanko-certvalidator | MIT |
| pypdfium2 / PDFium | Apache-2.0 / BSD-3-Clause |
| Qt for Python (PySide6) | LGPL-3.0 |
| cryptography | Apache-2.0 o BSD-3-Clause |
| asn1crypto | MIT |
| qrcode | BSD |
