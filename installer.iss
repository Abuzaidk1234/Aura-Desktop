[Setup]
AppName=AURA
AppVersion=1.0.0
DefaultDirName={autopf}\AURA
DefaultGroupName=AURA
OutputBaseFilename=AURASetup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=aura_icon.ico
UninstallDisplayIcon={app}\AURA.exe
PrivilegesRequired=lowest

[Files]
; Include the PyInstaller output directory
Source: "dist\AURA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AURA"; Filename: "{app}\AURA.exe"
Name: "{autodesktop}\AURA"; Filename: "{app}\AURA.exe"

[Run]
Filename: "{app}\AURA.exe"; Description: "Launch AURA Settings"; Flags: nowait postinstall skipifsilent

[Code]

function IsOllamaInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  // Check if Ollama is accessible via PATH
  if Exec('cmd.exe', '/c ollama --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
  
  // Check default installation path
  if FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) then
  begin
    Result := True;
    Exit;
  end;

  Result := False;
end;

function InitializeSetup(): Boolean;
var
  MsgResult: Integer;
begin
  Result := True;
  
  if not IsOllamaInstalled() then
  begin
    MsgResult := MsgBox('AURA requires Ollama and the llama3.2 model to run locally.' + #13#10#13#10 +
                        'Would you like the installer to automatically download and install Ollama now?', 
                        mbConfirmation, MB_YESNO);
                        
    if MsgResult = idYes then
    begin
      // Let the installer download and run OllamaSetup.exe
      // Since downloading inside InitializeSetup without a UI is hard in standard Inno Setup without plugins,
      // we will just open the browser and instruct the user, OR we can use the DownloadTemporaryFile function in Inno Setup 6.1+.
      // We assume Inno Setup 6.1+ is used.
    end
    else
    begin
      MsgBox('Ollama is required for AURA to function. Installation aborted.', mbCriticalError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

// Using the built-in Download function in Inno Setup 6.1+
var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  OllamaInstallerPath: string;
  ResultCode: Integer;
begin
  Result := True;

  if (CurPageID = wpReady) and not IsOllamaInstalled() then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        OllamaInstallerPath := ExpandConstant('{tmp}\OllamaSetup.exe');
        
        // Run Ollama Installer passively
        DownloadPage.SetText('Installing Ollama...', '');
        if Exec(OllamaInstallerPath, '', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
        begin
          // After installing, pull the llama3.2 model
          DownloadPage.SetText('Downloading llama3.2 model (this may take a few minutes)...', '');
          Exec('cmd.exe', '/c ollama pull llama3.2', '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
        end
        else
        begin
          MsgBox('Failed to install Ollama. Please install it manually.', mbError, MB_OK);
          Result := False;
        end;
      except
        if DownloadPage.AbortedByUser then
          Log('Aborted by user.')
        else
          MsgBox('Failed to download Ollama. Please check your internet connection.', mbError, MB_OK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
