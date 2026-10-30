# Arquitectura

## Capas

```mermaid
flowchart TB
    subgraph UI["Interfaz (PySide6) — src/kipufirma/gui"]
        MW[main_window.py<br/>Firmar · Verificar · Certificado · Ajustes]
        PV[preview.py<br/>vista previa + clic/arrastre]
        DL[dialogs.py<br/>contraseña · resultados]
        WK[workers.py<br/>hilos en segundo plano]
    end
    CLI[cli.py<br/>kipufirma-cli]
    subgraph CORE["Núcleo sin Qt — src/kipufirma/core"]
        BATCH[batch.py<br/>orquestación del lote]
        CERT[certificate.py · ec_certs.py · trust.py<br/>.p12, datos del titular, cadena]
        REV[revocation.py · timecheck.py<br/>OCSP/CRL, reloj]
        PDF[pdf_inspect.py · locator.py<br/>análisis y búsqueda de texto]
        PLC[placement.py · geometry.py<br/>reglas de ubicación, rotación]
        SIG[signer.py · stamp.py<br/>PAdES + sello QR]
        VER[verify.py<br/>verificación posterior]
        CFG[config.py · dpapi.py · secrets.py · logging_setup.py]
    end
    MW --> WK --> BATCH
    CLI --> BATCH
    BATCH --> CERT & REV & PDF & PLC & SIG & VER
    SIG -->|pyHanko| PDFOUT[(PDF firmado)]
    PDF -->|pypdfium2| PDFIN[(PDF original)]
    CERT --> ANCLAS[(resources/trust<br/>66 anclas ECEP)]
```

## Flujo de firma de un lote

```mermaid
sequenceDiagram
    actor U as Usuario
    participant UI
    participant C as certificate
    participant B as batch
    participant S as signer
    participant V as verify
    U->>UI: Firmar N documentos
    UI->>UI: ¿cambió el .p12? (huella SHA-256)
    UI->>U: Pide SOLO la contraseña
    U->>UI: contraseña
    UI->>C: load_credential(ruta, SecretBuffer)
    C-->>UI: credencial (contraseña ya borrada)
    UI->>B: prepare_session: vigencia, uso de clave, cadena, OCSP/CRL, reloj
    loop cada documento (un error no detiene el lote)
        B->>B: inspect_pdf (cifrado, DocMDP, JavaScript…)
        B->>B: resolve (fija | palabra clave | manual | invisible)
        B->>S: sign_pdf_bytes (una firma incremental por recuadro)
        B->>V: verify_pdf_bytes (las firmas recién añadidas)
        B->>B: atomic_write(firmados/…-firmado.pdf)
    end
    B-->>UI: resultados + informe CSV
    UI->>C: credential.destroy()
```

## Sistemas de coordenadas
* **Espacio de usuario PDF**: el que usan la firma y PDFium para el texto.
* **Espacio visual**: la página como se ve (con `/Rotate` aplicado), origen
  abajo-izquierda, en puntos. Las reglas («esquina inferior derecha»,
  «debajo de la palabra») se evalúan aquí y se convierten con
  `PageGeom.to_user/to_visual`. El sello se contrarrota (matriz `cm`) para
  leerse derecho en páginas giradas.

## Decisiones clave
* **Núcleo sin Qt** → testeable, reutilizable por la CLI.
* **`KeySigner`** firma con el objeto de clave de `cryptography` sin
  serializarla (pyHanko `SimpleSigner` la exporta a DER en cada firma).
* **Una firma por recuadro**: el estándar no permite una firma con varios
  widgets de forma interoperable; «todas las apariciones» genera N firmas.
* **Verificación posterior obligatoria** y **escritura atómica**.
* **Configuración JSON** versionada (`schema`), tolerante a campos
  desconocidos, con respaldo si está corrupta.
