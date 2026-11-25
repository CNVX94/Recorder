; Instalador de Recorder para Windows (Inno Setup 6.3 o superior, también 7).
;
; Lo compila packaging\build.ps1 con tres definiciones:
;     ISCC /DMyAppVersion=<versión> /DSourceDir=<carpeta onedir> /DOutputDir=<carpeta de salida> recorder.iss
; Sin ellas (p. ej. abriendo este archivo en el IDE de Inno Setup tras un build.ps1 -SinInstalador),
; toma la carpeta onedir de %LOCALAPPDATA%\RecorderBuild\dist\Recorder, deja el instalador en
; %LOCALAPPDATA%\RecorderBuild\installer y lee la versión del recurso de Recorder.exe.
;
; Instala por usuario (sin administrador) en %LOCALAPPDATA%\Programs\Recorder; el diálogo
; permite elegir "para todos los usuarios" si se quiere. Al desinstalar solo se quitan los
; archivos instalados: nunca la configuración (%APPDATA%\Recorder), los registros
; (%LOCALAPPDATA%\Recorder), las notas ni la caché de modelos de Hugging Face.

#ifndef SourceDir
  #define SourceDir GetEnv("LOCALAPPDATA") + "\RecorderBuild\dist\Recorder"
#endif
#ifndef OutputDir
  #define OutputDir GetEnv("LOCALAPPDATA") + "\RecorderBuild\installer"
#endif
#ifndef MyAppVersion
  #define MyAppVersion GetStringFileInfo(SourceDir + "\Recorder.exe", "ProductVersion")
#endif
#define MyAppName "Recorder"
#define MyAppExe "Recorder.exe"
#define MyTerminalExe "daily.exe"
; GUID de la aplicación: AppId (con la llave escapada) y la clave de desinstalación donde Windows
; guarda la versión instalada.
#define MyAppGuid "7D2B1C4E-5F3A-4B8E-9C1D-2E6F8A0B3C5D"
#define MyUninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{" + MyAppGuid + "}_is1"

[Setup]
; GUID fijo: identifica la aplicación en "Aplicaciones instaladas" y permite actualizar encima.
AppId={{{#MyAppGuid}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Recorder
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany=Recorder
VersionInfoProductName=Recorder
VersionInfoDescription=Instalador de Recorder
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Por usuario, sin UAC; el diálogo deja elegir "todos los usuarios" (ahí sí pide administrador).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Recorder-{#MyAppVersion}-setup
SetupIconFile=..\recorder\assets\recorder.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
; Avisa a Windows del cambio de PATH al terminar, para que las terminales nuevas lo vean.
ChangesEnvironment=yes
InfoBeforeFile=LEEME.txt
CloseApplications=yes
; Actualizar encima de la versión anterior: se reutiliza su carpeta (la página de carpeta no sale si
; ya hay una instalación) y las tareas que se eligieron (UsePreviousTasks, por defecto).
DisableDirPage=auto
; Recorder.exe y daily.exe crean este mutex al arrancar (recorder/registro.py, NOMBRE_MUTEX; las
; versiones anteriores a que se añadiera no lo tienen y las cierra solo el Administrador de reinicio).
; Mientras exista, Setup pide cerrarlos antes de copiar archivos en vez de dejar que daily.exe, que no
; tiene ventana que cerrar, haga fallar la actualización a los 30 segundos.
AppMutex=RecorderEnEjecucion

[CustomMessages]
spanish.ActualizarVersion=Se actualizará Recorder de la versión %1 a la %2 en la misma carpeta. Se conservan la configuración, las notas y las tareas que elegiste.
spanish.ReinstalarVersion=Recorder %1 ya está instalado. Se volverá a instalar encima, conservando la configuración, las notas y las tareas que elegiste.
spanish.VersionMasNueva=Ojo: hay instalada una versión más nueva (%1) que la de este instalador (%2). Seguir la sustituirá por la anterior; la configuración y las notas se conservan.
spanish.PerfilConDaily=En tu perfil de PowerShell hay una función «daily» de una instalación desde el código: tapa a la «daily» instalada y abre la copia del código con su propia configuración. Para usar la instalada, quita ese bloque del perfil (pasos en docs\instalacion.md, dentro de la carpeta _internal).

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "path"; Description: "Añadir ""daily"" a la terminal (PATH del usuario)"; GroupDescription: "Terminal:"

[InstallDelete]
; Al actualizar, la carpeta interna de PyInstaller se reemplaza entera para no dejar restos de
; versiones anteriores. La configuración nunca vive ahí (va en %APPDATA%\Recorder).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Transcribe reuniones y micrófono a una nota Markdown"
Name: "{autoprograms}\{#MyAppName} (terminal)"; Filename: "{app}\{#MyTerminalExe}"; Parameters: "menu"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExe}"; Comment: "Recorder desde la terminal: menú con todo lo que se puede hacer"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  VersionPrevia: String; // la versión que ya hay instalada; vacío si es una instalación nueva

function LeerVersionPrevia: String;
begin
  // Por usuario va a HKCU; si se instaló para todos, a HKLM.
  if not RegQueryStringValue(HKEY_CURRENT_USER, '{#MyUninstallKey}', 'DisplayVersion', Result) then
    if not RegQueryStringValue(HKEY_LOCAL_MACHINE, '{#MyUninstallKey}', 'DisplayVersion', Result) then
      Result := '';
end;

function InitializeSetup: Boolean;
begin
  VersionPrevia := LeerVersionPrevia;
  Result := True;
end;

// Lo que solo sirve la primera vez (SmartScreen, descarga del modelo) no se repite al actualizar.
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpInfoBefore) and (VersionPrevia <> '');
end;

function TextoActualizacion: String;
var
  Anterior, Nueva: Int64;
begin
  Result := FmtMessage(CustomMessage('ActualizarVersion'), [VersionPrevia, '{#MyAppVersion}']);
  if VersionPrevia = '{#MyAppVersion}' then
    Result := FmtMessage(CustomMessage('ReinstalarVersion'), [VersionPrevia])
  else if StrToVersion(VersionPrevia, Anterior) and StrToVersion('{#MyAppVersion}', Nueva)
       and (ComparePackedVersion(Anterior, Nueva) > 0) then
    Result := FmtMessage(CustomMessage('VersionMasNueva'), [VersionPrevia, '{#MyAppVersion}']);
end;

// Un perfil de PowerShell con el bloque que deja install.ps1 (la función daily del código).
function PerfilTieneDaily(const Carpeta: String): Boolean;
var
  Contenido: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{userdocs}\') + Carpeta + '\Microsoft.PowerShell_profile.ps1', Contenido)
    and (Pos('# >>> recorder >>>', String(Contenido)) > 0);
end;

function PerfilConDailyDelCodigo: Boolean;
begin
  Result := PerfilTieneDaily('WindowsPowerShell') or PerfilTieneDaily('PowerShell');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if VersionPrevia <> '' then
  begin
    if CurPageID = wpSelectTasks then
      WizardForm.SelectTasksLabel.Caption := TextoActualizacion
    else if CurPageID = wpReady then
      WizardForm.ReadyLabel.Caption := TextoActualizacion;
  end;
  if (CurPageID = wpFinished) and PerfilConDailyDelCodigo then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + CustomMessage('PerfilConDaily');
end;
// PATH: se añade {app} al final sin duplicarlo y se quita al desinstalar, sin tocar el resto.
// Por usuario va a HKCU\Environment; si se eligió instalar para todos, a la clave del sistema.

function RaizEntorno: Integer;
begin
  if IsAdminInstallMode then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

function ClaveEntorno: String;
begin
  if IsAdminInstallMode then
    Result := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Result := 'Environment';
end;

function PosEnPath(const Carpeta, Path: String): Integer;
begin
  // Sin distinguir mayúsculas y con ';' a los lados: C:\Recorder no es C:\Recorder2.
  Result := Pos(';' + Uppercase(Carpeta) + ';', ';' + Uppercase(Path) + ';');
end;

procedure AgregarAlPath(const Carpeta: String);
var
  Path: String;
begin
  if not RegQueryStringValue(RaizEntorno, ClaveEntorno, 'Path', Path) then
    Path := '';
  if PosEnPath(Carpeta, Path) > 0 then
    Exit; // ya estaba: no se duplica
  // Un PATH que acaba en ';' sigue acabando en ';': así, al quitarla, queda idéntico al de antes.
  if Path = '' then
    Path := Carpeta
  else if Path[Length(Path)] = ';' then
    Path := Path + Carpeta + ';'
  else
    Path := Path + ';' + Carpeta;
  if RegWriteExpandStringValue(RaizEntorno, ClaveEntorno, 'Path', Path) then
    Log('PATH: añadido ' + Carpeta)
  else
    Log('PATH: no se pudo escribir la clave');
end;

procedure QuitarDelPath(const Carpeta: String);
var
  Path: String;
  P: Integer;
begin
  if not RegQueryStringValue(RaizEntorno, ClaveEntorno, 'Path', Path) then
    Exit;
  P := PosEnPath(Carpeta, Path);
  if P = 0 then
    Exit;
  // P cuenta el ';' puesto delante, así que en Path la carpeta empieza en P. Se borra junto
  // con un separador: el siguiente si lo hay (deshace lo que hizo AgregarAlPath); si va al
  // final, el anterior; si es la única entrada, sola.
  if P + Length(Carpeta) <= Length(Path) then
    Delete(Path, P, Length(Carpeta) + 1)
  else if P > 1 then
    Delete(Path, P - 1, Length(Carpeta) + 1)
  else
    Delete(Path, P, Length(Carpeta));
  if RegWriteExpandStringValue(RaizEntorno, ClaveEntorno, 'Path', Path) then
    Log('PATH: quitado ' + Carpeta);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('path') then
    AgregarAlPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    QuitarDelPath(ExpandConstant('{app}'));
end;
