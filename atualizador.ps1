<#
Atualizador automatico do Concilia.

Roda como SYSTEM, de hora em hora e na inicializacao do servidor, numa tarefa
agendada que o proprio instalador cria quando instala para todos os usuarios (o
caso do SRV-ESQUEMA). Usuario comum nao tem permissao de escrever em Program
Files, entao a atualizacao nao pode partir do programa aberto: parte daqui.

A cada execucao:
  1. le a versao instalada no registro de desinstalacao do Inno Setup;
  2. consulta a ultima release do GitHub;
  3. se houver versao nova, baixa o instalador e confere o sha256 publicado pelo
     GitHub e a versao gravada no proprio .exe - um instalador velho anexado a
     uma release nova seria reinstalado toda hora, sem fim;
  4. instala em silencio, mas so com o Concilia fechado em todas as sessoes. De
     madrugada fecha as copias esquecidas em sessoes DESCONECTADAS (nunca nas
     ativas): as edicoes de historico ja vao para o disco a cada alteracao, entao
     nada se perde - so a tela aberta.

Uso:
  atualizador.ps1              verifica e instala (o que a tarefa executa)
  atualizador.ps1 -Simular     baixa e confere numa pasta temporaria, mas nao
                               fecha nem instala nada; so diz o que faria
  atualizador.ps1 -Registrar   cria a tarefa agendada (chamado pelo instalador)
  atualizador.ps1 -Remover     apaga a tarefa (chamado pelo desinstalador)

Registro em atualizacao\atualizador.log, ao lado do programa.
#>
param(
    [switch]$Simular,
    [switch]$Registrar,
    [switch]$Remover,
    [string]$VersaoInstalada   # so para teste: finge que esta e a versao instalada
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # a barra de progresso deixa o download do PS 5.1 lentissimo

$Repositorio = "rodrigohsr/concilia"
$ChaveDesinstalacao = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8F3C21D7-4B6E-4A55-9E2C-7D1A0C5B93E4}_is1"
$NomeTarefa = "Concilia - atualizacao automatica"
$ChaveMarca = "HKLM:\SOFTWARE\Concilia"   # o programa le daqui para avisar que a versao nova vem sozinha
$Madrugada = 1..5                          # horas em que copias em sessoes desconectadas podem ser fechadas

$Pasta = if ($Simular) { Join-Path $env:TEMP "concilia-atualizacao" } else { Join-Path $PSScriptRoot "atualizacao" }
$Log = Join-Path $Pasta "atualizador.log"


# ---- tarefa agendada --------------------------------------------------------
if ($Registrar) {
    # Se ja existe, fica como esta: o instalador chama -Registrar tambem quando
    # e a propria tarefa que esta atualizando o programa, e quem desativou a
    # tarefa de proposito nao a ve voltar a cada versao.
    if (-not (Get-ScheduledTask -TaskName $NomeTarefa -ErrorAction SilentlyContinue)) {
        $acao = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        $gatilhos = @(
            (New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(17) -RepetitionInterval (New-TimeSpan -Hours 1)),
            (New-ScheduledTaskTrigger -AtStartup)
        )
        $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
        $conta = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilhos -Settings $ajustes `
            -Principal $conta -Description "Instala as versoes novas do Concilia publicadas no GitHub." | Out-Null
    }
    New-Item -Path $ChaveMarca -Force | Out-Null
    Set-ItemProperty -Path $ChaveMarca -Name "AtualizacaoAutomatica" -Value 1 -Type DWord
    exit 0
}

if ($Remover) {
    Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -Path $ChaveMarca -Recurse -Force -ErrorAction SilentlyContinue
    exit 0
}


# ---- utilitarios ------------------------------------------------------------
function Escrever-Log([string]$texto) {
    $linha = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $texto
    Write-Host $linha
    New-Item -ItemType Directory -Force -Path $Pasta | Out-Null
    if ((Test-Path $Log) -and (Get-Item $Log).Length -gt 256KB) {
        $resto = Get-Content $Log -Tail 1000
        Set-Content -Path $Log -Value $resto -Encoding UTF8
    }
    Add-Content -Path $Log -Value $linha -Encoding UTF8
}

function Ler-Versao([string]$texto) {
    # 'v1.2.0' da tag, '1.2.0' do registro e '1.2.0.0' do .exe viram todos 1.2.0
    $n = @([regex]::Matches("$texto", "\d+") | ForEach-Object { [int]$_.Value })
    if (-not $n.Count) { return $null }
    while ($n.Count -lt 3) { $n += 0 }
    [version]("{0}.{1}.{2}" -f $n[0], $n[1], $n[2])
}

function Sessoes-Desconectadas {
    if (-not ("Concilia.Wts" -as [type])) {
        Add-Type -Namespace Concilia -Name Wts -MemberDefinition @"
[StructLayout(LayoutKind.Sequential)]
public struct Info { public int SessionId; public IntPtr Nome; public int Estado; }

[DllImport("wtsapi32.dll", SetLastError = true)]
static extern bool WTSEnumerateSessions(IntPtr servidor, int reservado, int versao, out IntPtr lista, out int total);
[DllImport("wtsapi32.dll")]
static extern void WTSFreeMemory(IntPtr memoria);

public static int[] Desconectadas() {
    IntPtr lista; int total;
    if (!WTSEnumerateSessions(IntPtr.Zero, 0, 1, out lista, out total)) return new int[0];
    var ids = new System.Collections.Generic.List<int>();
    int tamanho = Marshal.SizeOf(typeof(Info));
    for (int i = 0; i < total; i++) {
        var s = (Info)Marshal.PtrToStructure(new IntPtr(lista.ToInt64() + i * tamanho), typeof(Info));
        if (s.Estado == 4) ids.Add(s.SessionId);   // WTSDisconnected
    }
    WTSFreeMemory(lista);
    return ids.ToArray();
}
"@
    }
    [Concilia.Wts]::Desconectadas()
}


# ---- execucao ---------------------------------------------------------------
try {
    $instalada = if ($VersaoInstalada) { Ler-Versao $VersaoInstalada } else { Ler-Versao (Get-ItemProperty $ChaveDesinstalacao -ErrorAction SilentlyContinue).DisplayVersion }
    if (-not $instalada) {
        Escrever-Log "Concilia nao esta instalado para todos os usuarios - nada a fazer."
        exit 0
    }

    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $release = Invoke-RestMethod -UseBasicParsing -TimeoutSec 30 `
        -Uri "https://api.github.com/repos/$Repositorio/releases/latest" `
        -Headers @{ Accept = "application/vnd.github+json"; "User-Agent" = "Concilia-atualizador" }
    $publicada = Ler-Versao $release.tag_name

    if (-not $publicada -or $publicada -le $instalada) {
        # nao registra no log: seriam 24 linhas por dia dizendo a mesma coisa
        if ($Simular) { Write-Host "Instalada $instalada, publicada $publicada - nada a fazer." }
        exit 0
    }

    $arquivo = $release.assets | Where-Object { $_.name -like "Concilia-*-setup.exe" } | Select-Object -First 1
    if (-not $arquivo) {
        throw "a release $($release.tag_name) nao tem o anexo Concilia-*-setup.exe"
    }

    # ---- download e conferencia ---------------------------------------------
    New-Item -ItemType Directory -Force -Path $Pasta | Out-Null
    $setup = Join-Path $Pasta $arquivo.name
    $esperado = "$($arquivo.digest)" -replace "^sha256:", ""

    function Arquivo-Confere {
        if (-not (Test-Path $setup)) { return $false }
        if ($esperado) { return (Get-FileHash $setup -Algorithm SHA256).Hash -ieq $esperado }
        return (Get-Item $setup).Length -eq $arquivo.size
    }

    if (-not (Arquivo-Confere)) {
        Escrever-Log "Versao $publicada publicada (instalada: $instalada). Baixando $($arquivo.name)..."
        $parcial = "$setup.parcial"
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 900 -Uri $arquivo.browser_download_url -OutFile $parcial
        Move-Item -Force -Path $parcial -Destination $setup
        if (-not (Arquivo-Confere)) {
            Remove-Item -Force $setup
            throw "o arquivo baixado nao confere com o sha256 publicado no GitHub"
        }
    }

    $versaoDoExe = Ler-Versao (Get-Item $setup).VersionInfo.FileVersion
    if ($versaoDoExe -ne $publicada) {
        throw "a release $($release.tag_name) traz o instalador da versao $versaoDoExe - a tag e o binario precisam bater"
    }

    # ---- ninguem pode estar com o programa aberto ---------------------------
    $abertos = @(Get-Process -Name "Concilia" -ErrorAction SilentlyContinue)
    if ($abertos.Count -and ((Get-Date).Hour -in $Madrugada)) {
        $desconectadas = Sessoes-Desconectadas
        $esquecidos = @($abertos | Where-Object { $desconectadas -contains $_.SessionId })
        if ($esquecidos.Count) {
            $sessoes = ($esquecidos.SessionId | Sort-Object -Unique) -join ", "
            if ($Simular) {
                Write-Host "Fecharia o Concilia nas sessoes desconectadas: $sessoes"
                $abertos = @($abertos | Where-Object { $desconectadas -notcontains $_.SessionId })
            } else {
                $esquecidos | Stop-Process -Force
                Escrever-Log "Fechado o Concilia esquecido nas sessoes desconectadas: $sessoes"
                Start-Sleep -Seconds 3
                $abertos = @(Get-Process -Name "Concilia" -ErrorAction SilentlyContinue)
            }
        }
    }

    if ($abertos.Count) {
        $sessoes = ($abertos.SessionId | Sort-Object -Unique) -join ", "
        $texto = "Versao $publicada pronta, adiada: Concilia aberto nas sessoes $sessoes."
        if ($Simular) { Write-Host $texto } else { Escrever-Log $texto }
        exit 0
    }

    if ($Simular) {
        Write-Host "Instalador $($arquivo.name) baixado e conferido (sha256 e versao $versaoDoExe). Instalaria agora."
        exit 0
    }

    # ---- instalacao -------------------------------------------------------------
    # Sem /TASKS o Inno repete as opcoes da instalacao anterior (atalho, associacao).
    Escrever-Log "Instalando $publicada..."
    & change user /install *> $null   # modo de instalacao do RD Session Host; inocuo fora dele
    try {
        $p = Start-Process -FilePath $setup -Wait -PassThru -ArgumentList @(
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/ALLUSERS",
            "/LOG=`"$(Join-Path $Pasta 'instalacao.log')`""
        )
    } finally {
        & change user /execute *> $null
    }

    $agora = Ler-Versao (Get-ItemProperty $ChaveDesinstalacao -ErrorAction SilentlyContinue).DisplayVersion
    if ($p.ExitCode -ne 0 -or $agora -ne $publicada) {
        throw "o instalador terminou com codigo $($p.ExitCode) e a versao instalada ficou $agora (ver instalacao.log)"
    }

    Remove-Item -Force (Join-Path $Pasta "Concilia-*-setup.exe") -ErrorAction SilentlyContinue
    Escrever-Log "Atualizado: $instalada -> $agora."
    exit 0
}
catch {
    Escrever-Log "FALHA: $($_.Exception.Message)"
    exit 1
}
