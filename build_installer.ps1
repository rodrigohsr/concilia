# Monta o instalador do Concilia.
#
# Roda o build.ps1 (PyInstaller) e em seguida compila o installer.iss com o
# Inno Setup, gerando dist\Concilia-<versao>-setup.exe.
#
# Uso:  .\build_installer.ps1
#       .\build_installer.ps1 -PularBuild    (reaproveita dist\Concilia)

param([switch]$PularBuild)

$ErrorActionPreference = "Stop"

# ---- localiza o compilador do Inno Setup -----------------------------------
$candidatos = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
)
$iscc = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "Inno Setup nao encontrado." -ForegroundColor Yellow
    Write-Host "Baixe em https://jrsoftware.org/isdl.php e instale, ou rode:" -ForegroundColor Yellow
    Write-Host '  winget install JRSoftware.InnoSetup' -ForegroundColor Yellow
    throw "ISCC.exe ausente"
}

# ---- gera o executavel ------------------------------------------------------
if (-not $PularBuild) {
    & "$PSScriptRoot\build.ps1"
} elseif (-not (Test-Path "dist\Concilia\Concilia.exe")) {
    throw "dist\Concilia\Concilia.exe nao existe - rode sem -PularBuild"
}

# ---- compila o instalador ---------------------------------------------------
Write-Host "Compilando o instalador..." -ForegroundColor Cyan
& $iscc "installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou (codigo $LASTEXITCODE)" }

$setup = Get-ChildItem "dist\Concilia-*-setup.exe" | Sort-Object LastWriteTime | Select-Object -Last 1
$mb = "{0:N1} MB" -f ($setup.Length / 1MB)
Write-Host ""
Write-Host "Instalador pronto: $($setup.FullName) ($mb)" -ForegroundColor Green
