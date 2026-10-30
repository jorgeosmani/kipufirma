# Seguridad: modelo de amenazas y controles

## Activos a proteger
1. **Clave privada** del firmante (dentro del `.p12`).
2. **Contraseña** del `.p12`.
3. **Integridad** de los documentos y de la firma (que firme lo que el usuario ve, donde lo ve).
4. **Identidad**: que se firme con el certificado correcto.
5. **Datos personales** (cédula, nombres) en registros y configuración.

## Amenazas y controles

| Amenaza | Control en KipuFirma | Riesgo residual |
|---|---|---|
| Robo de la contraseña desde disco | Nunca se guarda; ni en `config.json` ni en registros | — |
| Contraseña residual en memoria | `SecretBuffer` (`bytearray` sobrescrito con ceros); el campo de texto se vacía al aceptar; credencial destruida al terminar el lote | Python/Qt pueden haber copiado cadenas internamente; un atacante con acceso a la memoria del proceso ya controla el equipo |
| Prueba masiva de contraseñas desde la interfaz | Espera exponencial tras 3 intentos (30 s → 15 min) | El `.p12` copiado puede atacarse fuera de línea: **use una contraseña robusta** |
| Sustitución del `.p12` por otro | Se guarda la huella SHA-256 del archivo y del certificado; si cambia, se advierte y se muestra el titular antes de firmar | — |
| `.p12` sincronizado a la nube | Advertencia si la ruta está en OneDrive/Dropbox/Google Drive/iCloud/MEGA | Decisión del usuario |
| Certificado de una entidad no acreditada | Cadena verificada criptográficamente hasta 66 anclas de ECEP ecuatorianas; por defecto se bloquea | Las anclas deben actualizarse al aparecer nuevas ECEP (`tools/extraer_anclas_firmaec.py`) |
| Certificado revocado | OCSP (firma de la respuesta verificada) y CRL (firma verificada) desde las URL del propio certificado; política *advertir/estricta* | Sin red, en modo *advertir* se puede firmar con aviso (igual que FirmaEC) |
| Certificado caducado o sin uso de firma | Bloqueo previo con mensaje claro | — |
| Reloj del equipo manipulado | Comparación con la hora de un servidor HTTPS; aviso si difiere > 2 min; TSA opcional | Sin TSA, la hora de firma es la del equipo |
| PDF malicioso (JavaScript, `/Launch`, adjuntos, XFA) | Análisis previo; política *advertir/bloquear*. KipuFirma nunca ejecuta JavaScript del PDF | El usuario puede elegir firmar igualmente |
| PDF certificado sin cambios permitidos (DocMDP P=1) | Se rechaza (firmarlo invalidaría la certificación) | — |
| PDF cifrado | Se rechaza si requiere contraseña de apertura | — |
| Firma dañada o mal construida | **Verificación inmediata** de cada firma generada; si falla, no se escribe el archivo | — |
| Archivo de salida corrupto (corte de energía) | Escritura atómica: temporal + `fsync` + renombrado | — |
| Sobrescritura de originales | Nunca se escribe sobre el original ni sobre un firmado existente | — |
| Fuga de datos personales en registros | Filtro que enmascara cédulas/RUC y valores tipo `password=` | — |
| Otra aplicación inyecta archivos por el canal de instancia única | `QLocalServer` con `UserAccessOption` (solo el usuario actual) y solo se agregan a la lista; firmar exige la contraseña | — |
| Cadena de suministro | Versiones fijadas, `pip-audit` y Dependabot en CI, `SHA256SUMS.txt` en cada versión | Se recomienda firmar el `.exe` con Authenticode |
| Instalación con privilegios excesivos | Instalador por usuario, sin administrador | — |

## Conexiones de red que realiza la aplicación
Solo estas, y todas pueden desactivarse en Ajustes:
1. **OCSP/CRL** de la entidad emisora (URL incluidas en su certificado).
2. **Cabecera `Date`** de `https://www.firmadigital.gob.ec/` (verificación del reloj).
3. **TSA** configurada por el usuario (si la configura).

Nunca se envían documentos a servidores. La herramienta opcional
`scripts/validar_con_mintel.py` sí envía documentos y por eso está fuera de la
aplicación y pide confirmación.

## Recomendaciones al usuario
* Contraseña del `.p12` de al menos 12 caracteres y única.
* Guardar el `.p12` en una carpeta local y una copia de respaldo cifrada fuera del equipo.
* Bloquear la sesión de Windows (Win + L) al alejarse.
* Mantener Windows y KipuFirma actualizados; descargar solo de *Releases* y comprobar `SHA256SUMS.txt`.
* Si sospecha que su `.p12` o contraseña se filtraron: **solicite la revocación a su entidad de certificación de inmediato**.
