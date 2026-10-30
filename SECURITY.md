# Política de seguridad

KipuFirma maneja certificados de firma electrónica: una vulnerabilidad puede
permitir suplantar la identidad del firmante. Tomamos los reportes en serio.

## Versiones con soporte

| Versión | Soporte |
|---|---|
| 1.x | ✅ |

## Cómo reportar una vulnerabilidad

**No abra un issue público.** Use *Security → Report a vulnerability*
(GitHub Private Vulnerability Reporting) en este repositorio, o escriba al
correo de los mantenedores indicado en el perfil del proyecto.

Incluya: versión, sistema operativo, pasos para reproducir e impacto. **Nunca
envíe su archivo .p12 ni su contraseña**; si hace falta, genere un certificado
de prueba (ver `tests/helpers.py`).

Plazos objetivo: acuse de recibo en 72 h, evaluación en 7 días, corrección
según gravedad. Publicaremos un aviso de seguridad (GHSA) y le daremos crédito
si lo desea.

## Alcance

Dentro: manejo de la contraseña y la clave privada, verificación de
certificados y firmas, procesamiento de PDF maliciosos, instalador, cadena de
suministro (dependencias, compilación). Fuera: la seguridad del equipo del
usuario (malware, keyloggers) y de los servicios de terceros (OCSP/CRL/TSA).

Modelo de amenazas completo: [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md).
