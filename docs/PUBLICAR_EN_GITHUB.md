# Publicar el proyecto en GitHub (paso a paso)

## 1. Crear el repositorio
En https://github.com/new: nombre `kipufirma`, **sin** README ni licencia (ya
vienen en el proyecto). Público o privado según prefiera.

## 2. Reemplazar el usuario
Busque `jorgeosmani` y cámbielo por su usuario de GitHub en: `pyproject.toml`,
`packaging/kipufirma.iss`, `.github/ISSUE_TEMPLATE/config.yml`,
`CONTRIBUTING.md`, `docs/COMPILACION_WINDOWS.md` y `README.md`.

```powershell
Get-ChildItem -Recurse -File -Include *.md,*.toml,*.iss,*.yml |
  ForEach-Object { (Get-Content $_ -Raw) -replace 'jorgeosmani','su-usuario' | Set-Content $_ -NoNewline }
```

## 3. Primer commit
```powershell
cd kipufirma
git init -b main
git add .
git status            # REVISE: no debe aparecer ningún .p12/.pfx ni PDF personal
git commit -m "feat: KipuFirma 1.0.0"
git remote add origin https://github.com/su-usuario/kipufirma.git
git push -u origin main
```

## 4. Configurar el repositorio
* **Settings → Code security**: active *Dependabot alerts*, *Secret scanning*
  y *Private vulnerability reporting*.
* **Settings → Branches**: proteja `main` (requerir PR y que pase CI).
* **About**: descripción y temas `firma-electronica`, `ecuador`, `pades`, `firmaec`.

## 5. Publicar la primera versión
```powershell
git tag v1.0.0
git push origin v1.0.0
```
El flujo *Publicar versión* compila en Windows y adjunta al *Release* el
instalador, el ZIP portable y `SHA256SUMS.txt`.
