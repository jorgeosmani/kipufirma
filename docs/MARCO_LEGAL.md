# Marco legal de la firma electrónica en Ecuador (resumen orientativo)

> **Aviso.** Este resumen no es asesoría legal. Las normas citadas pueden haber
> sido reformadas; verifique el texto vigente en el Registro Oficial, en
> ARCOTEL y en el portal oficial https://www.firmadigital.gob.ec antes de
> tomar decisiones.

## Normas principales
* **Ley de Comercio Electrónico, Firmas Electrónicas y Mensajes de Datos**
  (Ley 2002-67, Registro Oficial Suplemento 557, 17 de abril de 2002), con sus
  reformas posteriores (incluidas, según la información disponible, las
  introducidas por la Ley Orgánica para la Transformación Digital y
  Audiovisual de 2023).
  * Los mensajes de datos tienen igual valor jurídico que los documentos escritos.
  * La **firma electrónica tiene igual validez y efectos jurídicos que la firma
    manuscrita** respecto de los datos consignados en documentos escritos.
  * **Requisitos** (en síntesis): ser individual y vinculada exclusivamente a
    su titular; permitir verificar inequívocamente la autoría e identidad del
    signatario; que su método de creación y verificación sea confiable, seguro
    e inalterable; y que los datos de creación estén bajo **control exclusivo**
    del signatario al momento de firmar.
* **Reglamento General** a la Ley (Decreto Ejecutivo 3496, 2002) y sus reformas.
* **Ley Orgánica de Telecomunicaciones** (2015): la **ARCOTEL** es la autoridad
  que acredita y controla a las Entidades de Certificación de Información (ECEP).
* **Ley Orgánica de Protección de Datos Personales** (2021): aplica al manejo
  de cédulas y nombres; por eso KipuFirma no los guarda en configuración y los
  enmascara en registros.

## Qué hace legal una firma hecha con KipuFirma
La validez **no la otorga el programa**, sino el cumplimiento de los requisitos:

| Requisito | Cómo se cumple |
|---|---|
| Certificado emitido por una **ECEP acreditada** | Su certificado `.p12` de BCE, Security Data, Uanataca, etc. KipuFirma verifica la cadena hasta las raíces de esas entidades |
| Certificado **vigente y no revocado** al firmar | Verificación de vigencia y revocación (OCSP/CRL) antes de firmar |
| **Control exclusivo** del titular | El `.p12` y su contraseña los tiene solo usted; KipuFirma no guarda la contraseña |
| **Verificable e inalterable** | Firma PAdES estándar; cualquier cambio posterior al documento invalida la firma. Verificable en FirmaEC |

## Recomendaciones de uso institucional
1. Antes de usar en producción, ejecute las pruebas de
   [`PRUEBAS_ACEPTACION.md`](PRUEBAS_ACEPTACION.md) con su certificado real y
   conserve la evidencia (capturas del validador oficial).
2. Si su institución exige expresamente «firmado con FirmaEC», consulte con su
   área jurídica: la norma exige requisitos técnicos, no un programa en
   particular, pero las políticas internas pueden ser más estrictas.
3. Para documentos que deban probar la **fecha** con fuerza, use sello de tiempo
   (TSA) de una entidad acreditada.
4. Conserve los documentos firmados en su formato original (no los imprima a
   PDF de nuevo ni los «optimice»: eso rompe la firma).
