; Tuckly kurulum betiği (Inno Setup 6).
; Önce `python -m PyInstaller --noconfirm --clean tuckly.spec` ile dist\Tuckly klasörünü üretin, sonra:
;     ISCC installer\tuckly.iss            ->  dist\Tuckly-Setup-<sürüm>.exe
; Kurulum yönetici izni istemez; yalnızca geçerli kullanıcı için kurar.

#define AppName "Tuckly"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6B6B3A52-6C1F-4E0B-9C7C-7D0B5A2C7A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Tuckly
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Tuckly-Setup-{#AppVersion}
SetupIconFile=..\assets\tuckly.ico
UninstallDisplayIcon={app}\Tuckly.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Güncellemede çalışan Tuckly kapatılır (gizlenen simgeler geri gelsin diye önce düzgünce kapatılır)
CloseApplications=yes
CloseApplicationsFilter=Tuckly.exe
LicenseFile=..\LICENSE

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "autostart"; Description: "{cm:AutoStartProgram,{#AppName}}"; Flags: unchecked

[Files]
Source: "..\dist\Tuckly\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Tuckly.exe"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\Tuckly.exe"; Parameters: "--arkaplan"; Tasks: autostart

[Run]
Filename: "{app}\Tuckly.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Çalışan Tuckly'yi kapatır, gizlenen masaüstü simgelerini geri getirir, sağ tık menüsü ve başlangıç kayıtlarını siler
Filename: "{app}\Tuckly.exe"; Parameters: "--temizle"; RunOnceId: "TucklyCleanup"; Flags: waituntilterminated

[Code]
// Güncelleme kurulumundan önce çalışan Tuckly'yi düzgünce kapat: böylece gizlenen simgeler geri gelir
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Exe: String;
begin
  Result := '';
  Exe := ExpandConstant('{app}\Tuckly.exe');
  if FileExists(Exe) then
  begin
    Exec(Exe, '--cik', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(2500);
  end;
end;

// Kaldırırken ayarların da silinip silinmeyeceğini sor
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Tuckly settings and card layout are kept in your profile. Delete them too?',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\Tuckly'), True, True, True);
end;
