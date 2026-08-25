; Instalador do Concilia - Inno Setup 6
;
; Compile com:  .\build_installer.ps1
; (o script roda o build.ps1 antes, para garantir que dist\Concilia esta atualizado)

#define Nome        "Concilia"
#define Versao      "1.0.0"
#define Empresa     "Esquema Assessoria Contabil"
#define Descricao   "Conferencia de extratos bancarios em OFX"
#define Executavel  "Concilia.exe"

[Setup]
; AppId identifica o programa nas atualizacoes e na desinstalacao.
; NAO altere entre versoes: e ele que faz o instalador reconhecer e substituir
; uma instalacao anterior em vez de criar uma segunda copia.
AppId={{8F3C21D7-4B6E-4A55-9E2C-7D1A0C5B93E4}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher={#Empresa}
VersionInfoVersion={#Versao}
VersionInfoDescription={#Descricao}

DefaultDirName={autopf}\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
DisableDirPage=auto

; Por padrao instala so para o usuario atual, sem passar pela tela de UAC nas
; maquinas onde o usuario nao e administrador.
;
; 'commandline' habilita /ALLUSERS e /CURRENTUSER na linha de comando, que e o
; que permite a instalacao para todos os usuarios da maquina em um script de
; distribuicao (executado com privilegio de administrador). Sem essa opcao o
; /ALLUSERS e simplesmente recusado.
PrivilegesRequiredOverridesAllowed=commandline dialog
PrivilegesRequired=lowest

OutputDir=dist
OutputBaseFilename={#Nome}-{#Versao}-setup
SetupIconFile=concilia.ico
UninstallDisplayIcon={app}\{#Executavel}
UninstallDisplayName={#Nome} {#Versao}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"
Name: "associar";   Description: "Abrir arquivos .ofx com o {#Nome}"; GroupDescription: "Arquivos:"

[Files]
; A pasta inteira gerada pelo PyInstaller (--onedir), incluindo _internal
Source: "dist\{#Nome}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nome}";                  Filename: "{app}\{#Executavel}"
Name: "{group}\Desinstalar o {#Nome}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nome}";            Filename: "{app}\{#Executavel}"; Tasks: desktopicon

[Registry]
; Associacao do .ofx. Fica em HKA (HKLM ou HKCU conforme o modo de instalacao),
; e o ProgId proprio evita atropelar o programa que ja abre OFX na maquina -
; o Windows continua oferecendo os dois em "Abrir com".
Root: HKA; Subkey: "Software\Classes\.ofx\OpenWithProgids"; \
    ValueType: string; ValueName: "{#Nome}.Extrato"; ValueData: ""; \
    Flags: uninsdeletevalue; Tasks: associar

Root: HKA; Subkey: "Software\Classes\{#Nome}.Extrato"; \
    ValueType: string; ValueName: ""; ValueData: "Extrato bancario OFX"; \
    Flags: uninsdeletekey; Tasks: associar

Root: HKA; Subkey: "Software\Classes\{#Nome}.Extrato\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#Executavel},0"; \
    Tasks: associar

Root: HKA; Subkey: "Software\Classes\{#Nome}.Extrato\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#Executavel}"" ""%1"""; \
    Tasks: associar

; Registra o programa na lista "Abrir com" tambem para .qfx (variante do formato)
Root: HKA; Subkey: "Software\Classes\.qfx\OpenWithProgids"; \
    ValueType: string; ValueName: "{#Nome}.Extrato"; ValueData: ""; \
    Flags: uninsdeletevalue; Tasks: associar

[Run]
Filename: "{app}\{#Executavel}"; Description: "Abrir o {#Nome} agora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Preferencias gravadas pelo programa (ultima pasta e tamanho da janela)
Type: filesandordirs; Name: "{userappdata}\{#Nome}"

[Code]
// Impede instalar por cima com o programa aberto: os arquivos ficariam em uso
// e a instalacao terminaria pela metade.
function EstaRodando(): Boolean;
var
  Codigo: Integer;
begin
  Result := False;
  if Exec('cmd.exe', '/C tasklist /FI "IMAGENAME eq {#Executavel}" | find /I "{#Executavel}"',
          '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
    Result := (Codigo = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if EstaRodando() then
  begin
    MsgBox('O {#Nome} esta aberto. Feche o programa antes de continuar a instalacao.',
           mbError, MB_OK);
    Result := False;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if EstaRodando() then
  begin
    MsgBox('O {#Nome} esta aberto. Feche o programa antes de desinstalar.',
           mbError, MB_OK);
    Result := False;
  end;
end;
