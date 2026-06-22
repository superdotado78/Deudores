param(
    [string]$RemoteUrl = ""
)

# Inicializa un repo git local, configura usuario si falta, hace commit y opcionalmente push al remoto
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git no está instalado o no está en PATH. Instálalo y vuelve a ejecutar este script."
    exit 1
}

Set-Location -Path (Split-Path -Path $MyInvocation.MyCommand.Definition -Parent)\..\

if (-not (git rev-parse --is-inside-work-tree 2>$null)) {
    git init
}

$currentEmail = git config user.email
if (-not $currentEmail) {
    git config user.email "tu@correo.com"
}

$currentName = git config user.name
if (-not $currentName) {
    git config user.name "Tu Nombre"
}

git add .
try {
    git commit -m "Initial commit: app, Dockerfile, migration script and docs"
} catch {
    Write-Host "No se creó commit (posiblemente no hay cambios para commitear). Continuando..."
}

if ($RemoteUrl -ne "") {
    if (-not (git remote)) {
        git remote add origin $RemoteUrl
    }
    git branch -M main
    git push -u origin main
}

Write-Host "Listo. Ejecuta 'git status' para verificar el estado local."
