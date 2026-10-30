# Análisis de FirmaEC y decisiones de diseño de KipuFirma

Este documento registra qué se estudió, qué hace FirmaEC, qué buenas prácticas
se adoptaron, qué carencias se corrigieron y por qué. Sirve como respaldo
técnico del proyecto (y como insumo si se presenta como trabajo académico).

## 1. Fuentes estudiadas

El repositorio **oficial** de FirmaEC está en el GitLab del Estado
(`minka.gob.ec/mintel/ge/firmaec`), no en GitHub. En GitHub existen copias y
derivados; se analizaron:

| Repositorio | Contenido | Licencia | Uso en este análisis |
|---|---|---|---|
| `davidcanar/firmaec` | Reconstrucción de **FirmaEC 5.3.0** (librería + aplicación de escritorio) a partir del binario oficial | GPL-3.0 | Fuente principal: flujo de la app, firma, apariencias, entidades, anclas |
| `sarmientodeveloper/firmaec` | `firmadigital-libreria`, `firmadigital-servicio`, `firmadigital-api` | AGPL-3.0 | Servicios REST (validación, revocación, hora) |
| `fachamorro/Firmaec` | Fuente de la librería (versión anterior) | GPL-3.0 | Contraste de versiones |
| `XaviMontero/firmaec.js` | Port a TypeScript con pruebas de paridad contra Java | AGPL-3.0 | Confirmación de detalles de compatibilidad |
| `ragutierrez/validador-firmaec` | Cliente del servicio público de validación | MIT-0 | Endpoint para pruebas de aceptación |

## 2. Cómo firma FirmaEC 5.3.0

### 2.1 Formato de la firma PDF
* `PadesEnhancedSigner` (usado por la app): iText 7, **modo incremental**
  (`StampingProperties.useAppendMode()`), contenedor **`adbe.pkcs7.detached`**
  con `CryptoStandard.CMS`, resumen **SHA-512**, 16 384 bytes reservados.
* Sello de tiempo RFC 3161 contra `https://tsa.uanatacaec.com/tsa/timestamp`,
  autenticando con **usuario = contraseña = cédula/RUC del firmante**.
* `/SignatureCreator`: `"<versión> (FirmaEC)"`.
* Hora de la firma: la obtiene de `https://api.firmadigital.gob.ec/api/fecha-hora`.

### 2.2 Apariencia (estampado)
Tres tipos: `QR`, `information1`, `information2`. Con QR:
* Rectángulo por defecto **110 × 36 pt** desde el punto clicado.
* QR en el primer tercio; texto «Validar únicamente en FirmaEC. / Firmado
  electrónicamente por:» y el nombre en Courier Bold 6,25 pt, truncado a 57
  caracteres.
* Contenido del QR: `FIRMADO POR`, `RAZON`, `LOCALIZACION`, `FECHA` (ISO-8601
  con zona), `VALIDAR CON: https://www.firmadigital.gob.ec`, versión y SO.
* Página por defecto: la última.

### 2.3 Certificados y entidades
* **Lista blanca** de entidades por la organización (O) del emisor:
  21 nombres de 16 entidades (BCE, Security Data, ANF AC, Consejo de la
  Judicatura, Uanataca, Eclipsoft, Datil, Lazzate, ArgosData, FirmaSegura,
  CorpNewBest, AppFirmas, Alpha Technologies, Letmi, PrimeCoreLat, Darkcam,
  DIGERCIC).
* 70 clases con certificados raíz/intermedios embebidos (66 únicos).
* Datos del titular por dos esquemas:
  **EXT** (extensiones `1.3.6.1.4.1.<arco>.3.n`: 1 cédula, 2 nombres,
  3-4 apellidos, 5 cargo, 6 institución, 7 dirección, 8 teléfono, 9 ciudad,
  10 razón social, 11 RUC, 12 país) y **SUBJ** (atributos X.500 estándar).
* Antes de firmar: vigencia según la hora del servidor, revocación vía API de
  MINTEL (`/certificado/fechaRevocado`) u OCSP/CRL, y verificación de la firma
  del certificado contra la sub-CA conocida.

### 2.4 Otros controles
* `CheckPDF`: rechaza PDF con JavaScript en `/OpenAction` o en acciones de
  anotaciones («El documento es potencialmente sospechoso»).
* Nombre de salida: `<original>-signed.pdf` (y `_new` si existe).
* Preferencias en `~/firmadigital.properties`: ruta del certificado y tipo
  (archivo/token). Nunca la contraseña.
* Soporte de tokens PKCS#11 (ePass, SafeNet, Bit4id, UKC) y almacén de Windows.

## 3. Buenas prácticas identificadas (y adoptadas)

| Práctica en FirmaEC | En KipuFirma |
|---|---|
| Firma incremental: no altera contenido ni firmas previas | ✅ pyHanko `IncrementalPdfFileWriter` |
| SHA-512 y `adbe.pkcs7.detached` | ✅ por defecto («Compatible FirmaEC»); PAdES ETSI opcional |
| Lista de entidades y anclas embebidas | ✅ mismas 66 anclas, extraídas con trazabilidad (`manifest.json`) |
| Verificación de vigencia y revocación previa | ✅ OCSP/CRL directos, con verificación de la firma de la respuesta |
| Rechazo de PDF con JavaScript | ✅ ampliado (Launch, AA, adjuntos, XFA) con política configurable |
| No guardar la contraseña | ✅ y además se borra de memoria tras usarla |
| Recordar la ruta del certificado | ✅ y además su huella SHA-256 para detectar sustituciones |
| QR con datos de la firma | ✅ mismo contenido y orden |

## 4. Carencias detectadas y mejoras

| # | Carencia en FirmaEC 5.3.0 | Mejora en KipuFirma |
|---|---|---|
| 1 | En lotes, **una sola posición** para todos los documentos | Regla general + **ubicación manual por documento** |
| 2 | **No busca palabras clave** | Búsqueda insensible a tildes/mayúsculas, alternativas en orden, primera/última/todas, posición relativa, plan B |
| 3 | Solo acepta hojas **A4** al estampar | Cualquier tamaño (carta, oficio, apaisado) con esquina de anclaje |
| 4 | Ignora la rotación de página | Soporte 0/90/180/270 con sello siempre legible |
| 5 | Errores del lote en **ventanas modales**; reinicia el formulario | El lote continúa; resumen final con informe CSV |
| 6 | Contraseña (`char[]`) no se limpia | `SecretBuffer` que se sobrescribe con ceros |
| 7 | Nombre truncado a 57 caracteres | Ajuste automático de tamaño y hasta 3 líneas |
| 8 | QR raster | QR vectorial (nítido al imprimir) |
| 9 | Sin verificación posterior | Cada documento se **verifica tras firmar**; si falla, no se guarda |
| 10 | Escritura directa del archivo | Escritura **atómica** (temporal + renombrado), sin sobrescribir |
| 11 | Si la entidad no es reconocida → `NullPointerException` | Mensaje claro y política configurable |
| 12 | Sin vista previa de dónde quedará cada firma | Vista previa en vivo para cada documento antes de firmar |
| 13 | Sin línea de comandos | `kipufirma-cli` para automatizar |

## 5. Lo que deliberadamente NO se replicó

* **TSA de Uanataca con la cédula como credencial**: es un acuerdo del servicio
  oficial; usarlo desde otro software sin autorización no es apropiado. En su
  lugar, el sello de tiempo es configurable (URL/usuario/contraseña de una TSA
  que el usuario tenga contratada o autorizada).
* **API de hora y de versión de MINTEL**: imitar la identidad del cliente
  oficial (`base64` con «FIRMADOR») no es correcto. Se verifica el reloj con la
  cabecera HTTP `Date` de un servidor público y se advierte del desfase.
* **Tokens PKCS#11** (versión 1.0): se planifica para una versión futura
  (pyHanko lo soporta); el requerimiento actual es el archivo `.p12`.
* **XAdES (comprobantes del SRI)**: fuera de alcance de esta versión.

## 6. Elección tecnológica

| Opción | Ventajas | Desventajas | Decisión |
|---|---|---|---|
| Java + librería FirmaEC | Máxima paridad | Requiere JRE, UI Swing limitada, iText AGPL | Descartada |
| **Python + pyHanko + PySide6** | pyHanko es una librería PAdES madura (MIT), validación incluida; Qt moderno; pruebas sencillas | Empaquetado más pesado (~120 MB) | **Elegida** |
| Node/Electron (`firmaec.js`) | Port fiel | Electron pesado; menos herramientas de validación | Descartada |

Compatibilidad verificada en las pruebas: subfiltro `/adbe.pkcs7.detached`,
`sha512`, cobertura total del archivo, cadena hasta las anclas, conservación de
firmas previas. **La compatibilidad final con el validador oficial debe
confirmarse con certificados reales** (ver `PRUEBAS_ACEPTACION.md`).

## 7. Licencia

La librería de FirmaEC es AGPL-3.0 y la aplicación GPL-3.0. Aunque KipuFirma
es una implementación nueva, incorpora datos extraídos de FirmaEC y replica su
formato; por coherencia y respeto al proyecto original se publica bajo
**AGPL-3.0-or-later** (compatible con ambas).
