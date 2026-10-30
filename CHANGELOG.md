# Registro de cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) ·
Versionado: [SemVer](https://semver.org/lang/es/).

## [Sin publicar]
### Corregido
- `requirements.txt`: cryptography 50.0.2 (la 46.0.6 era incompatible con pyHanko 0.38).
- `instalar_desarrollo.ps1` se detiene si pip falla o si `.venv` usa Python < 3.11.
- Vista previa: conversión directa PDFium → Qt; ya no requiere Pillow (fallaba la prueba de interfaz).
- Un recuadro dibujado demasiado pequeño usa el tamaño de sello configurado (evita sellos ilegibles).
### Añadido
- Autor y contacto en «Acerca de», README y metadatos.
- Colocación interactiva: sello «fantasma» que sigue al ratón con QR y nombre; el clic asienta
  la firma al instante; flechas para ajuste fino (Mayús = 10 pt).
- Textos adaptados cuando se firma un solo documento.
### Cambiado
- Tamaño de sello por defecto igual al de FirmaEC (110 × 36 pt) y sin línea de fecha
  (la fecha queda en la firma y en el QR). Las configuraciones antiguas se migran solas.
- La vista previa ya no reanaliza el PDF en cada cambio (caché por versión del archivo).

## [1.0.0] - 2026-10-29
### Añadido
- Firma PAdES incremental compatible con FirmaEC (adbe.pkcs7.detached, SHA-512) y modo PAdES ETSI.
- Certificado .p12/.pfx recordado (ruta + huella SHA-256); al firmar solo se pide la contraseña.
- Firma por lotes con verificación automática de cada documento y continuidad ante errores.
- Ubicación: posición fija adaptable a cualquier tamaño de hoja, búsqueda por palabras clave
  (insensible a tildes/mayúsculas, varias alternativas, primera/última/todas las apariciones,
  plan alternativo), firma invisible y ubicación manual por documento.
- Soporte de páginas giradas (0/90/180/270).
- Sello con QR vectorial y ajuste automático del nombre.
- Validación del certificado: vigencia, uso de clave, cadena hasta 66 certificados de 16 ECEP
  ecuatorianas, revocación OCSP/CRL con política configurable, verificación del reloj.
- Análisis de PDF peligrosos (JavaScript, /Launch, adjuntos, XFA) y respeto de certificaciones DocMDP.
- Interfaz PySide6 con vista previa, arrastrar y soltar, instancia única y tema claro/oscuro.
- CLI (`kipufirma-cli`), instalador Inno Setup con acceso directo en el escritorio y menú contextual.
