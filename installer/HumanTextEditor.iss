#define MyAppName "Human Text Editor"
#define MyAppExeName "HumanTextEditor.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Wart050"
#define MyAppURL "https://github.com/Wart050/human_editor"

[Setup]
AppId={{8A7D3F4F-2E2C-4C0F-9C31-9B1C8C0F8C7C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\HumanTextEditor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=HumanTextEditor-Setup
OutputDir=..\dist\installer
SetupIconFile=..\assets\icon.ico
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
