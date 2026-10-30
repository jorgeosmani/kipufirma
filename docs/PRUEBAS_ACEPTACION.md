# Pruebas de aceptación con certificado real (antes de usar en producción)

Las pruebas automáticas (`pytest`) usan una PKI simulada. La compatibilidad
**legal y operativa** se confirma con su certificado real y el validador
oficial. Registre los resultados (capturas) como evidencia.

## Preparación
* Su `.p12` vigente (BCE, Security Data, Uanataca, etc.).
* Carpeta con PDF **de prueba** (sin datos sensibles): A4 vertical, carta,
  oficio, A4 apaisado, una página girada, uno ya firmado con FirmaEC, uno de
  varias páginas, uno escaneado sin texto, uno con formularios.

## Casos

| # | Caso | Resultado esperado |
|---|---|---|
| 1 | Seleccionar `.p12`, cerrar y reabrir la app | La ruta se recuerda; al firmar solo pide contraseña |
| 2 | Contraseña incorrecta 4 veces | Mensaje claro y espera de 30 s |
| 3 | Firmar 1 PDF, posición fija | Archivo en `firmados/`; **válido en FirmaEC** |
| 4 | Lote de 20+ PDF de distintos tamaños, posición fija | Todos válidos; sello en la misma esquina relativa |
| 5 | Lote por palabra clave con firmas en lugares distintos | Cada sello junto a su palabra; **válidos en FirmaEC** |
| 6 | Palabra no encontrada con cada plan alternativo | Fija / invisible / omitido según configuración |
| 7 | Ocurrencia «todas» en un acta con 3 «Firma:» | 3 firmas, todas válidas |
| 8 | Firmar un PDF ya firmado con FirmaEC | Ambas firmas válidas en FirmaEC |
| 9 | Firmar con KipuFirma y luego con FirmaEC | Ambas firmas válidas |
| 10 | Página girada 90° | Sello derecho y en el lugar visto |
| 11 | PDF escaneado + palabra clave | Aplica plan alternativo (sin texto) |
| 12 | Formato PAdES ETSI | Válido en FirmaEC y en Adobe Reader |
| 13 | Sin internet (modo advertir / estricta) | Aviso / bloqueo |
| 14 | Leer el QR con el celular | Muestra firmante, razón, localización, fecha |
| 15 | Abrir en Adobe Reader | Panel de firmas muestra la firma; si la raíz de su entidad no está en la lista de confianza de Adobe, figurará «identidad desconocida» (normal) |
| 16 | Modificar un PDF firmado y verificar | KipuFirma y FirmaEC lo reportan inválido |

## Cómo validar en el validador oficial
1. Aplicación FirmaEC de escritorio → **Verificar documento** → seleccione el PDF firmado.
2. O el validador web del portal https://www.firmadigital.gob.ec.
3. Opcional (documentos de prueba): `python scripts/validar_con_mintel.py dist\firmado.pdf`.

Criterio de aceptación: **casos 3, 4, 5, 7, 8, 9 y 12 deben mostrarse válidos
en el validador oficial**. Si alguno falla, abra un issue (sin adjuntar su
certificado) y use FirmaEC mientras se corrige.
