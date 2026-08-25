# Gera o executavel do Concilia.
#
# IMPORTANTE: usa --onedir (pasta), e nao --onefile. O modo --onefile descompacta
# o programa inteiro numa pasta temporaria a cada execucao, o que costuma custar
# de 2 a 5 segundos toda vez que o usuario abre o programa. Com --onedir a
# abertura e praticamente imediata.
#
# Uso:  .\build.ps1          (gera dist\Concilia)
#       .\build_installer.ps1 monta o instalador a partir dessa pasta.

$ErrorActionPreference = "Stop"

$nome = "Concilia"

$argumentos = @(
    "--noconfirm", "--clean",
    "--windowed",              # sem janela de console
    "--onedir",
    "--name", $nome,
    "--icon", "concilia.ico",
    "--add-data", "concilia.ico;."
)

# O logo da empresa e opcional: entra no pacote so se estiver na pasta
if (Test-Path "logo.png") { $argumentos += @("--add-data", "logo.png;.") }

# Bibliotecas pesadas que o programa nao usa. Excluir evita que o PyInstaller as
# arraste por engano (o pandas sozinho somava dezenas de MB e um atraso
# perceptivel na abertura).
foreach ($modulo in @("pandas", "numpy", "matplotlib", "scipy", "IPython", "pytest")) {
    $argumentos += @("--exclude-module", $modulo)
}

$argumentos += "app_desktop.py"

Write-Host "Gerando $nome..." -ForegroundColor Cyan
python -m PyInstaller @argumentos
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (codigo $LASTEXITCODE)" }

$exe = "dist\$nome\$nome.exe"
$tamanho = "{0:N1} MB" -f ((Get-ChildItem "dist\$nome" -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "Pronto: $exe ($tamanho na pasta)" -ForegroundColor Green
