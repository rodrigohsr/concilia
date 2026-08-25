# Instala o Concilia para TODOS os usuarios deste servidor.
#
# Feito para o SRV-ESQUEMA, que e um RD Session Host: os usuarios do escritorio
# entram por area de trabalho remota, entao uma unica instalacao para todos
# atende o escritorio inteiro. Nao ha nada para distribuir maquina a maquina.
#
# Precisa ser executado como administrador:
#   Start-Process powershell -Verb RunAs -ArgumentList '-File','.\instalar_no_servidor.ps1'
#
# Parametros:
#   -SemAtalhoNaAreaDeTrabalho   nao cria o atalho na area de trabalho publica
#   -Setup <caminho>             usa outro instalador que nao o de dist\

param(
    [switch]$SemAtalhoNaAreaDeTrabalho,
    [string]$Setup
)

$ErrorActionPreference = "Stop"

# ---- confere elevacao -------------------------------------------------------
$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidade)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Este script precisa ser executado como administrador (botao direito > Executar como administrador)."
}

# ---- localiza o instalador --------------------------------------------------
if (-not $Setup) {
    $Setup = Get-ChildItem (Join-Path $PSScriptRoot "dist\Concilia-*-setup.exe") -EA SilentlyContinue |
             Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object { $_.FullName }
}
if (-not $Setup -or -not (Test-Path $Setup)) {
    throw "Instalador nao encontrado. Rode .\build_installer.ps1 antes, ou informe -Setup <caminho>."
}
Write-Host "Instalador: $Setup" -ForegroundColor Cyan

# ---- avisa se houver usuarios com o programa aberto -------------------------
$abertos = Get-Process -Name "Concilia" -EA SilentlyContinue
if ($abertos) {
    $quem = ($abertos | ForEach-Object { $_.SessionId } | Sort-Object -Unique) -join ", "
    throw "O Concilia esta aberto nas sessoes: $quem. Peca para fecharem antes de instalar."
}

# ---- modo de instalacao do Terminal Server ----------------------------------
# Em um RD Session Host, aplicativos devem ser instalados com a maquina em
# "install mode". E o procedimento documentado para que a instalacao valha
# corretamente para todos os usuarios, inclusive os que ainda nao logaram.
$ehSessionHost = $false
try {
    $ehSessionHost = (Get-WindowsFeature -Name RDS-RD-Server -EA Stop).InstallState -eq "Installed"
} catch { }

if ($ehSessionHost) {
    Write-Host "RD Session Host detectado - entrando em modo de instalacao..." -ForegroundColor Cyan
    & change user /install | Out-Null
}

try {
    # ---- instalacao ---------------------------------------------------------
    $tarefas = if ($SemAtalhoNaAreaDeTrabalho) { "associar" } else { "associar,desktopicon" }
    $argumentos = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS", "/TASKS=$tarefas")

    Write-Host "Instalando para todos os usuarios (tarefas: $tarefas)..." -ForegroundColor Cyan
    $p = Start-Process $Setup -ArgumentList $argumentos -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "O instalador retornou codigo $($p.ExitCode)." }
}
finally {
    if ($ehSessionHost) {
        & change user /execute | Out-Null
        Write-Host "Modo de execucao restaurado." -ForegroundColor Cyan
    }
}

# ---- verificacao ------------------------------------------------------------
Write-Host ""
Write-Host "--- conferencia ---" -ForegroundColor Cyan

$exe = Join-Path $env:ProgramFiles "Concilia\Concilia.exe"
if (Test-Path $exe) { Write-Host "OK    programa: $exe" } else { throw "FALHA: $exe nao existe" }

$registro = Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" -EA SilentlyContinue |
            ForEach-Object { Get-ItemProperty $_.PSPath } |
            Where-Object { $_.DisplayName -like "Concilia*" }
if ($registro) { Write-Host "OK    registrado: $($registro.DisplayName)" } else { Write-Host "AVISO nao aparece em Programas e Recursos" }

if (Test-Path "HKLM:\SOFTWARE\Classes\Concilia.Extrato\shell\open\command") {
    Write-Host "OK    arquivos .ofx associados para todos os usuarios"
} else {
    Write-Host "AVISO associacao de .ofx nao encontrada em HKLM"
}

$menu = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Concilia"
if (Test-Path $menu) { Write-Host "OK    menu iniciar de todos os usuarios" } else { Write-Host "AVISO atalho do menu iniciar ausente" }

$publico = Join-Path $env:PUBLIC "Desktop\Concilia.lnk"
if (-not $SemAtalhoNaAreaDeTrabalho) {
    if (Test-Path $publico) { Write-Host "OK    atalho na area de trabalho de todos os usuarios" }
    else { Write-Host "AVISO atalho da area de trabalho ausente" }
}

Write-Host ""
Write-Host "Instalado. Cada usuario ja encontra o Concilia no menu iniciar." -ForegroundColor Green
Write-Host "As preferencias (ultima pasta, tamanho da janela) ficam separadas por usuario," -ForegroundColor Green
Write-Host "em %APPDATA%\Concilia - um nao interfere no outro." -ForegroundColor Green
