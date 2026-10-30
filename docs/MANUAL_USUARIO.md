# Manual de usuario

## 1. Primer uso: configurar su certificado (una sola vez)
1. Abra **KipuFirma** desde el acceso directo del Escritorio.
2. Vaya a **Mi certificado → Seleccionar archivo .p12 / .pfx…** y elija su archivo.
3. Escriba la contraseña cuando se le pida. Verá su nombre, la entidad emisora,
   la fecha de vencimiento y el estado de la cadena de confianza.

Desde ahora KipuFirma **recuerda dónde está su archivo**. La contraseña **no se
guarda**: se le pedirá solo en el momento de firmar.

## 2. Firmar uno o muchos documentos
1. En **Firmar**, arrastre archivos PDF o carpetas a la lista (o use
   *Agregar PDF…* / *Agregar carpeta…*). También puede seleccionar PDF en el
   Explorador → clic derecho → *Mostrar más opciones* → **Firmar con KipuFirma**.
2. Elija **dónde va la firma** (panel derecho):

### Firmar un solo documento (lo más común)
1. *Agregar PDF…* y elija el documento.
2. Deje marcado **«Elegir el lugar con un clic en la página»**.
3. Vaya a la página con ◀ ▶ o la rueda del ratón. Al mover el ratón sobre la página verá
   un **sello amarillo** que muestra exactamente dónde y cómo quedará la firma.
4. **Clic** para colocarla (queda en verde). Si quiere afinar, use las **flechas** del
   teclado (1 punto por pulsación; con Mayús, 10).
5. **Firmar 1 documento(s)** → contraseña → listo.

El tamaño por defecto es el mismo de FirmaEC (39 × 13 mm); puede cambiarlo en *Tamaño*.

### a) Misma posición en todos
* Haga **clic** (o arrastre un recuadro) sobre la vista previa donde quiere la
  firma. Se guarda como «esquina + distancia», de modo que funciona aunque los
  documentos tengan distinto tamaño de hoja.
* Ajuste página (última, primera, número, todas) y distancias en milímetros.

### b) Buscar palabra clave
* Escriba una o varias palabras clave, **una por línea, en orden de
  prioridad** (ej.: `Firma del docente` y, debajo, `Firma:`).
* No importa mayúsculas ni tildes: «firma del decano» encuentra «FIRMA DEL DÉCANO».
* Elija si el sello va debajo, encima, a la derecha, a la izquierda o sobre el texto.
* Si aparece varias veces: primera, última o **todas** (una firma por aparición).
* **Si no se encuentra**: usar la posición fija, firmar invisible o no firmar ese documento.
* Requiere PDF con texto. Para escaneos sin OCR use posición fija o manual.

### c) Firma invisible
Válida igual que la visible; no agrega sello en la página.

### d) Ubicación manual para un documento
Seleccione el documento, cambie el selector superior a **«Al hacer clic: solo
ESTE documento»** y haga clic en la vista previa. El documento se marca con ✎.
Clic derecho → *Quitar ubicación manual* para deshacerlo.

3. Revise la columna **Ubicación prevista** (en ámbar se marca lo que requiere
   atención) y la vista previa (recuadro verde).
4. Pulse **Firmar N documento(s)** → escriba **solo la contraseña** → **Firmar**.
5. Al terminar verá el resumen: firmados, con avisos, omitidos o con error. Puede
   abrir la carpeta o **exportar un informe CSV**.

Los archivos firmados se guardan (por defecto) en la subcarpeta `firmados`
junto a cada original, con el nombre `documento-firmado.pdf`. **El original
nunca se modifica.**

## 3. Verificar documentos
En **Verificar**, arrastre PDF firmados. Verá firmante, entidad, fecha y si la
firma es íntegra y de una entidad reconocida. Para fines legales use además el
**validador oficial** (botón *Abrir validador oficial*).

## 4. Ajustes útiles
* **Formato**: «Compatible FirmaEC» (recomendado) o PAdES ETSI.
* **Contenido del sello**: encabezado, pie («Validar únicamente en FirmaEC»), QR, fecha.
* **Seguridad**: revocación (advertir/estricta), PDF con contenido activo
  (advertir/bloquear), exigir entidad reconocida, verificación del reloj.
* **Sello de tiempo**: URL de una TSA contratada/autorizada.

## 5. Preguntas frecuentes
**¿Dónde están los registros?** `%LOCALAPPDATA%\KipuFirma\logs` (botón en Ajustes).
**¿Dónde está la configuración?** `%APPDATA%\KipuFirma\config.json`.
**Renové mi certificado.** Seleccione el nuevo `.p12` en *Mi certificado*; si
reemplazó el archivo en la misma ruta, KipuFirma le avisará del cambio.
**«Entidad no reconocida».** Su entidad puede ser nueva: avise al proyecto
(issue) o, bajo su responsabilidad, copie su certificado raíz a
`%APPDATA%\KipuFirma\anclas_adicionales\`.
**El sello sale sobre texto.** Ajuste la separación/posición o use la ubicación manual.
