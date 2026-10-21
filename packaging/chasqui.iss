; Inno Setup script for the chasqui installer. Built by packaging/build_windows.py,
; which passes AppVersion, AppDir (the PyInstaller folder), AppIcon and OutDir.
;
; Per-user install on purpose: no admin prompt, and nothing chasqui does needs
; one. The key and settings live in %USERPROFILE%\.chasqui and survive
; uninstalling, so a reinstall does not ask for the key again.

#ifndef AppVersion
  #error Build with packaging/build_windows.py
#endif

[Setup]
AppId={{6C1E5A0B-6F0E-4C55-9C3B-3E7A6C0B1A57}
AppName=chasqui
AppVersion={#AppVersion}
AppPublisher=kvothesson
AppPublisherURL=https://github.com/kvothesson/chasqui
AppSupportURL=https://github.com/kvothesson/chasqui/issues
DefaultDirName={localappdata}\Programs\chasqui
DefaultGroupName=chasqui
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=chasqui-setup-{#AppVersion}
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\chasqui.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#AppDir}\LICENSE.txt

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\chasqui"; Filename: "{app}\chasqui.exe"; WorkingDir: "{userdocs}"
Name: "{autodesktop}\chasqui"; Filename: "{app}\chasqui.exe"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\chasqui.exe"; Description: "{cm:LaunchProgram,chasqui}"; Flags: nowait postinstall skipifsilent
