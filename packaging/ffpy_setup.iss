; Inno Setup 6 Script for ffpy
; Creates a standard "Next -> Next -> Finish" Windows installer (ffpy-<version>-setup.exe)

#define MyAppName "ffpy"
#ifndef MyAppVersion
  #define MyAppVersion "0.2.1"
#endif
#define MyAppPublisher "Andrei Eltsov"
#define MyAppURL "https://github.com/eltsovan2006/ffpy"
#define MyAppExeName "ffpy-gui.exe"
#define MyConsoleExeName "ffpy.exe"

[Setup]
AppId={{D37E64B2-16FA-4E28-89E2-60D9E6E2452F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName=C:\ffpy
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=ffpy-{#MyAppVersion}-setup
SetupIconFile=ffpy.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes
ChangesAssociations=yes
DisableDirPage=no
DisableProgramGroupPage=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Добавить ffpy в переменную окружения PATH (для запуска из любого терминала)"; GroupDescription: "Системная интеграция:"; Flags: checkedonce
Name: "associateinp"; Description: "Ассоциировать файлы .inp (входные файлы Firefly/GAMESS) с ffpy-gui"; GroupDescription: "Ассоциации файлов:"; Flags: checkedonce

[Files]
Source: "..\dist\ffpy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ffpy-gui"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "ffpy GUI — редактор и запуск расчётов"
Name: "{group}\ffpy (командная строка)"; Filename: "{app}\{#MyConsoleExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Parameters: "--help"; Comment: "ffpy консольный интерфейс"
Name: "{group}\Примеры расчётов"; Filename: "{app}\examples"
Name: "{group}\Документация по ключевым словам"; Filename: "{app}\docs\KEYWORDS.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ffpy-gui"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "ffpy GUI"

[Registry]
; File association for .inp
Root: HKA; Subkey: "Software\Classes\.inp"; ValueType: string; ValueName: ""; ValueData: "ffpy.InputFile"; Flags: uninsdeletevalue; Tasks: associateinp
Root: HKA; Subkey: "Software\Classes\ffpy.InputFile"; ValueType: string; ValueName: ""; ValueData: "Firefly / ffpy Input File"; Flags: uninsdeletekey; Tasks: associateinp
Root: HKA; Subkey: "Software\Classes\ffpy.InputFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associateinp
Root: HKA; Subkey: "Software\Classes\ffpy.InputFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associateinp

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,ffpy-gui}"; Flags: nowait postinstall skipifsilent

[Code]
const
    SMTO_ABORTIFHUNG = 2;
    WM_SETTINGCHANGE = $001A;

function SendMessageTimeout(hWnd: Integer; Msg: Cardinal; wParam: Cardinal; lParam: String; fuFlags: Cardinal; uTimeout: Cardinal; out lpdwResult: Cardinal): Integer;
    external 'SendMessageTimeoutW@user32.dll stdcall';

procedure EnvRefresh();
var
    DummyResult: Cardinal;
begin
    SendMessageTimeout($FFFF, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, DummyResult);
end;

procedure AddToPath(DirToAdd: string);
var
    OldPath: string;
    NewPath: string;
    RootKey: Integer;
    SubKey: string;
begin
    if IsAdminInstallMode() then
    begin
        RootKey := HKEY_LOCAL_MACHINE;
        SubKey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
    end
    else
    begin
        RootKey := HKEY_CURRENT_USER;
        SubKey := 'Environment';
    end;

    if not RegQueryStringValue(RootKey, SubKey, 'Path', OldPath) then
        OldPath := '';

    if Pos(';' + Uppercase(DirToAdd) + ';', ';' + Uppercase(OldPath) + ';') = 0 then
    begin
        if (OldPath <> '') and (OldPath[Length(OldPath)] <> ';') then
            OldPath := OldPath + ';';
        NewPath := OldPath + DirToAdd;
        RegWriteStringValue(RootKey, SubKey, 'Path', NewPath);
        EnvRefresh();
    end;
end;

procedure RemoveFromPath(DirToRemove: string);
var
    OldPath, NewPath, SearchPattern: string;
    P: Integer;
    RootKey: Integer;
    SubKey: string;
begin
    if IsAdminInstallMode() then
    begin
        RootKey := HKEY_LOCAL_MACHINE;
        SubKey := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
    end
    else
    begin
        RootKey := HKEY_CURRENT_USER;
        SubKey := 'Environment';
    end;

    if not RegQueryStringValue(RootKey, SubKey, 'Path', OldPath) then
        Exit;

    SearchPattern := ';' + Uppercase(DirToRemove) + ';';
    NewPath := ';' + OldPath + ';';
    P := Pos(SearchPattern, Uppercase(NewPath));
    if P > 0 then
    begin
        Delete(NewPath, P, Length(DirToRemove) + 1);
        if (Length(NewPath) > 0) and (NewPath[1] = ';') then
            Delete(NewPath, 1, 1);
        if (Length(NewPath) > 0) and (NewPath[Length(NewPath)] = ';') then
            Delete(NewPath, Length(NewPath), 1);
        RegWriteStringValue(RootKey, SubKey, 'Path', NewPath);
        EnvRefresh();
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    begin
        AddToPath(ExpandConstant('{app}'));
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
    if CurUninstallStep = usPostUninstall then
    begin
        RemoveFromPath(ExpandConstant('{app}'));
    end;
end;
