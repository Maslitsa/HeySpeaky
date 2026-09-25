<#
.SYNOPSIS
    Installs or updates HeySpeaky.

.DESCRIPTION
    One command, pasted into PowerShell:

        irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex

    It runs inside the PowerShell that is already open. Do not wrap it in
    powershell -ExecutionPolicy Bypass -c "...": a second powershell.exe with
    a download on its command line is what Windows Defender reports as
    Trojan:Win32/Commando.A!ml, and it refuses to start it.

    You do not need Python. The script downloads uv, a single-file Python
    manager, and uv downloads the exact Python HeySpeaky is tested on into the
    install folder. Whatever Python you already have is never used: none,
    3.13, the Microsoft Store one and conda all behave the same.

    With your OpenAI key in the command, it checks the key with OpenAI, saves
    it, takes it back out of the PowerShell history file, and uses OpenAI:

        $env:OPENAI_API_KEY = "sk-..."; irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex

    Without one, a fresh install asks whether to transcribe with OpenAI or on
    this computer, and takes the key there. Updates do not ask again.

    To remove HeySpeaky, use uninstall.ps1.

    Run it again to update. config.json and the speech models are kept.

    If it fails, the window stays open, the last lines say why, and the whole
    run is in %TEMP%\HeySpeaky-install.log.

.PARAMETER InstallDir
    Where to install when downloading. Defaults to
    %LOCALAPPDATA%\Programs\HeySpeaky. Ignored when this script is run from a
    copy of the project, which installs that copy.

.PARAMETER Backend
    openai or local, to answer the question a fresh install asks.

.PARAMETER SetApiKey
    Asks for an OpenAI API key, checks it with OpenAI, and stores it outside
    the project, readable only by you.

.PARAMETER NoStart
    Set everything up but do not launch the app.

.PARAMETER NoAutostart
    Do not start HeySpeaky when you sign in.

.PARAMETER NoGame
    Do not open the window with the progress bar and the dinosaur game.

.EXAMPLE
    # Arguments with the one-command install:
    $s = [scriptblock]::Create((irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1))
    & $s -InstallDir 'D:\Apps\HeySpeaky'
    & $s -Backend local

.EXAMPLE
    # From a copy of the project:
    INSTALL.bat
    INSTALL.bat -SetApiKey
#>
param(
    [switch]$SetApiKey,
    [switch]$NoStart,
    [switch]$NoAutostart,
    [switch]$NoGame,
    [string]$InstallDir,
    [ValidateSet('ask', 'openai', 'local')]
    [string]$Backend = 'ask'
)

# Empty when piped into iex, which is how the one-command install runs.
$SelfPath = $PSCommandPath

# Everything happens inside this block. Piped into iex, a script runs in the
# caller's own session, so without it every preference and variable set here
# would leak into their PowerShell, and a plain `exit` would close the window
# they need to read the error in.
& {

$ErrorActionPreference = 'Stop'
# Invoke-WebRequest is several times slower while drawing its progress bar.
$ProgressPreference = 'SilentlyContinue'

# Messages from PowerShell and Windows come out in the Windows display
# language, mixed in with this script's English ones. Not everyone who reads
# them, or searches for them, knows that language, so everything is English.
$SavedUICulture = [Threading.Thread]::CurrentThread.CurrentUICulture
try {
    [Threading.Thread]::CurrentThread.CurrentUICulture = [Globalization.CultureInfo]::GetCultureInfo('en-US')
} catch {}

$AppName      = 'HeySpeaky'
$RepoUrl      = 'https://github.com/Maslitsa/HeySpeaky'
$RawInstaller = 'https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1'
$KeysPage     = 'https://platform.openai.com/api-keys'
# Lets a branch be tried before it reaches main.
$Ref          = if ($env:HEYSPEAKY_REF) { $env:HEYSPEAKY_REF } else { 'main' }

# uv is pinned, and checked against the SHA-256 published with that release,
# because the installer runs it.
$UvVersion = '0.12.13'
$UvSha256  = 'a86c9dc7bad9b03f388583b7187c05fe9951c2e0d392217e8fd43d97787f6ec2'

# RealtimeSTT declares python_requires >=3.11,<3.13. Always the x86_64 build:
# it also runs on ARM laptops through Windows 11's emulation, and PyAudio and
# ctranslate2 publish no ARM wheels.
$PythonRequest = 'cpython-3.12-windows-x86_64-none'

$MinFreeGB = 3
# Deepest file an install creates, measured below the folder: 149
# characters, in uv's cache. Windows refuses paths over 260 unless long paths
# are enabled, and a failure there surfaces as an unrelated build error.
$MaxRootLength = 90

# The app was VoiceType, then SpeakIt, now HeySpeaky. Newest first.
$LegacyNames = @('SpeakIt', 'VoiceType')
$LogFile    = Join-Path $env:TEMP 'HeySpeaky-install.log'
# Read by the progress window, tools\install_game.py.
$ProgressFile = Join-Path $env:TEMP 'HeySpeaky-progress.json'

# Shared with the functions below by changing their contents: a function that
# assigns a variable gets its own copy.
$Progress  = @{ Plan = $null; Active = $false }
$StepTimer = @{ Name = ''; Watch = $null }

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

function Write-Log([string]$Text) {
    try { Add-Content -LiteralPath $LogFile -Value $Text -Encoding UTF8 } catch {}
}

function Complete-StepTime {
    # How long each step took goes in the log, so a slow install on someone
    # else's PC shows where the time went.
    if ($StepTimer.Watch) {
        Write-Log ("    ({0}: {1}s)" -f $StepTimer.Name, [int]$StepTimer.Watch.Elapsed.TotalSeconds)
        $StepTimer.Watch = $null
    }
}

function Write-Step([string]$Text) {
    Complete-StepTime
    $StepTimer.Name = $Text
    $StepTimer.Watch = [Diagnostics.Stopwatch]::StartNew()
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
    Write-Log "==> $Text"
}

function Write-Note([string]$Text) {
    Write-Host "    $Text"
    Write-Log "    $Text"
}

function Invoke-Native([string]$What, [string]$Exe, [string[]]$Arguments) {
    # Windows PowerShell turns every stderr line of a native program into an
    # error record, and with ErrorActionPreference at Stop the first one aborts
    # the script. uv and pip write ordinary progress to stderr.
    Write-Log "> $Exe $($Arguments -join ' ')"
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Empty stdin. Nothing here should ever wait for an answer, and a
        # prompt nobody can see would hang the install instead of failing it.
        $null | & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = "$_"
            Write-Host "    $line"
            Write-Log "    $line"
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "$What failed (exit code $code). The lines above say why."
    }
}

$SavedEnv = @{}
function Set-ProcessEnv([string]$Name, [string]$Value) {
    if (-not $SavedEnv.ContainsKey($Name)) {
        $SavedEnv[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if ($SelfPath) {
    $Root = Split-Path -Parent $SelfPath
} elseif ($InstallDir) {
    $Root = $InstallDir
} else {
    # Not Documents or Desktop: those are often synced by OneDrive, which would
    # try to upload a gigabyte of Python packages.
    $Root = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
}
$Root = [IO.Path]::GetFullPath($Root)

# [IO.Path]::Combine, not Join-Path: Join-Path fails on a drive that does not
# exist, and out here that error would skip the explanation below.
$UvDir       = [IO.Path]::Combine($Root, '.uv')
$VenvDir     = [IO.Path]::Combine($Root, '.venv')
$VenvPy      = [IO.Path]::Combine($VenvDir, 'Scripts\python.exe')
$VenvPyW     = [IO.Path]::Combine($VenvDir, 'Scripts\pythonw.exe')
$EntryFile   = [IO.Path]::Combine($Root, 'run.py')
$IconFile    = [IO.Path]::Combine($Root, 'heyspeaky.ico')
$ConfigFile  = [IO.Path]::Combine($Root, 'config.json')
$StartupDir  = [Environment]::GetFolderPath('Startup')
$ProgramsDir = [Environment]::GetFolderPath('Programs')
$StartupLnk  = Join-Path $StartupDir "$AppName.lnk"
$MenuDir     = Join-Path $ProgramsDir $AppName
$MenuLnk     = Join-Path $MenuDir "$AppName.lnk"
$KeyDir      = Join-Path $env:APPDATA $AppName
$KeyFile     = Join-Path $KeyDir 'openai.key'
$LegacyKeys  = @($LegacyNames | ForEach-Object { Join-Path $env:APPDATA "$_\openai.key" })
$MutexName   = "Global\$AppName.SingleInstance"

# ---------------------------------------------------------------------------
# Stopping
# ---------------------------------------------------------------------------

function Stop-HeySpeaky {
    # Matches run.py only when it belongs to HeySpeaky, or to VoiceType before
    # the rename, so an unrelated Python script called run.py is left alone.
    $all = @(Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue)
    if (-not $all) { return }

    $needles = @($AppName) + $LegacyNames + @($Root)
    $ours = {
        param($line)
        if (-not $line) { return $false }
        foreach ($needle in $needles) {
            if ($line.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        }
        return $false
    }

    $live = @{}
    foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) { $live[$p.Id] = $true }

    $targets = New-Object System.Collections.Generic.List[object]
    $mains = @($all | Where-Object { $_.CommandLine -like '*run.py*' -and (& $ours $_.CommandLine) })
    foreach ($m in $mains) { $targets.Add($m) }
    $mainIds = @($mains | ForEach-Object { $_.ProcessId })

    # RealtimeSTT transcribes in a spawned worker. Take those too, including
    # orphans from old versions whose parent is already gone.
    foreach ($p in $all) {
        if ($p.CommandLine -notlike '*spawn_main*') { continue }
        $isChild  = $mainIds -contains $p.ParentProcessId
        $isOrphan = (-not $live.ContainsKey($p.ParentProcessId)) -and (& $ours $p.CommandLine)
        if ($isChild -or $isOrphan) { $targets.Add($p) }
    }

    foreach ($t in ($targets | Sort-Object ProcessId -Unique)) {
        Write-Note "stopping PID $($t.ProcessId)"
        try { Stop-Process -Id $t.ProcessId -Force -ErrorAction Stop } catch {}
    }
    if ($targets.Count -gt 0) { Start-Sleep -Milliseconds 800 }
}

function Remove-Shortcuts([string]$Name) {
    $menu = Join-Path $ProgramsDir $Name
    foreach ($lnk in @((Join-Path $StartupDir "$Name.lnk"), (Join-Path $menu "$Name.lnk"))) {
        if (Test-Path -LiteralPath $lnk) {
            Remove-Item -LiteralPath $lnk -Force
            Write-Note "removed $lnk"
        }
    }
    if ((Test-Path -LiteralPath $menu) -and -not (Get-ChildItem -LiteralPath $menu -Force)) {
        Remove-Item -LiteralPath $menu -Force
    }
}

# ---------------------------------------------------------------------------
# OpenAI key, and the choice between OpenAI and local
# ---------------------------------------------------------------------------

function Test-HaveKey {
    if (Test-Path -LiteralPath $KeyFile) { return $true }
    foreach ($old in $LegacyKeys) {
        if (Test-Path -LiteralPath $old) { return $true }
    }
    return $false
}

function Save-ApiKey([string]$Key) {
    New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
    [IO.File]::WriteAllText($KeyFile, $Key, (New-Object Text.UTF8Encoding($false)))
    # Break inheritance so only this account can read it.
    & icacls $KeyFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    Write-Note "saved to $KeyFile, readable only by $($env:USERNAME)"
}

function Test-ApiKey([string]$Key) {
    # Listing models is free and needs nothing but a valid key, so a mistyped
    # or half-pasted key is caught here instead of at the first dictation.
    try {
        $null = Invoke-RestMethod -Uri 'https://api.openai.com/v1/models' -Headers @{ Authorization = "Bearer $Key" } -TimeoutSec 20 -UseBasicParsing
        return 'valid'
    } catch {
        $status = 0
        try { $status = [int]$_.Exception.Response.StatusCode } catch {}
        if ($status -eq 401) { return 'invalid' }
        if ($status) { return "OpenAI answered $status" }
        return 'OpenAI could not be reached'
    }
}

function Format-Key([string]$Key) {
    # Enough to recognise a key by, never enough to use it.
    if ($Key.Length -gt 12) {
        return $Key.Substring(0, 8) + '...' + $Key.Substring($Key.Length - 4)
    }
    return 'that key'
}

function Read-ApiKey {
    # Returns a key that OpenAI accepted, or $null if the user skipped.
    $interactive = -not [Console]::IsInputRedirected
    Write-Host ''
    Write-Host "    1. Open $KeysPage"
    Write-Host '    2. Click "Create new secret key", then Copy'
    Write-Host '    3. Come back here, paste it with Ctrl+V or a right-click, press Enter'
    Write-Host '       A key starts with sk-. It shows as ***** while you paste, on purpose.'
    Write-Host ''
    if ($interactive) {
        try { Start-Process $KeysPage; Write-Host '    (opened that page in your browser)' } catch {}
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $plain = ''
        try {
            if ($interactive) {
                $secure = Read-Host -AsSecureString '    Paste your key, or just press Enter to skip'
                if ($secure) {
                    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
                    try {
                        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
                    } finally {
                        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
                    }
                }
            } else {
                # -AsSecureString reads the console itself, never piped input,
                # and would wait forever for a key nobody can type.
                $plain = [Console]::In.ReadLine()
            }
        } catch {}
        # A pasted key often brings a space, a line break or quotes with it.
        $plain = "$plain" -replace '[\s"'']', ''
        if (-not $plain) { return $null }

        $shown = Format-Key $plain
        $verdict = Test-ApiKey $plain
        if ($verdict -eq 'valid') {
            Write-Note "$shown works"
            return $plain
        }
        if ($verdict -eq 'invalid') {
            Write-Warning "OpenAI does not accept $shown. Copy the key again with its Copy button and paste all of it."
            continue
        }
        Write-Note "$verdict, so $shown could not be checked. Saving it anyway."
        return $plain
    }
    Write-Note 'OpenAI turned down three keys in a row. Skipping for now.'
    return $null
}

function Get-KeptKey {
    # A key someone keeps in their environment on purpose, as opposed to one
    # set in the install command.
    $kept = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'User')
    if (-not $kept) { $kept = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Machine') }
    return $kept
}

function Remove-KeyFromHistory([string]$Key) {
    # A key typed into a command lands in PowerShell's history file in plain
    # text. The command stays there, the key does not.
    $paths = @(Join-Path $env:APPDATA 'Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt')
    try { $paths += (Get-PSReadLineOption).HistorySavePath } catch {}
    $removed = $false
    foreach ($path in ($paths | Where-Object { $_ } | Select-Object -Unique)) {
        try {
            if (-not (Test-Path -LiteralPath $path)) { continue }
            $text = [IO.File]::ReadAllText($path)
            if ($text.Contains($Key)) {
                [IO.File]::WriteAllText($path, $text.Replace($Key, 'sk-...removed'), (New-Object Text.UTF8Encoding($false)))
                $removed = $true
            }
        } catch {}
    }
    # And from this window's up-arrow history.
    try { [Microsoft.PowerShell.PSConsoleReadLine]::ClearHistory() } catch {}
    try { Clear-History } catch {}
    if ($removed) { Write-Note 'took the key back out of your PowerShell history' }
}

function Use-KeyFromCommand {
    # The easiest way in:
    #   $env:OPENAI_API_KEY = "sk-..."; irm .../install.ps1 | iex
    # Returns 'saved', 'rejected', or 'none' when the command had no key.
    $raw = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
    $kept = Get-KeptKey
    # A key that was already in the environment is not an instruction to
    # switch to OpenAI on every update. HeySpeaky reads that one by itself.
    if (-not $raw -or $raw -eq $kept) { return 'none' }
    # Put the variable back the way it was before the command set it.
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $kept, 'Process')

    Write-Step 'Your OpenAI API key'
    $key = $raw -replace '[\s"'']', ''
    if (-not $key -or $key -eq 'PASTE-YOUR-KEY-HERE') {
        Write-Warning 'The command still says PASTE-YOUR-KEY-HERE. Put your own key between the quotes.'
        return 'rejected'
    }
    Remove-KeyFromHistory $key
    $shown = Format-Key $key
    $verdict = Test-ApiKey $key
    if ($verdict -eq 'invalid') {
        Write-Warning "OpenAI does not accept $shown. Copy the key again with its Copy button and paste all of it."
        return 'rejected'
    }
    if ($verdict -eq 'valid') {
        Write-Note "$shown works"
    } else {
        Write-Note "$verdict, so $shown could not be checked. Saving it anyway."
    }
    Save-ApiKey $key
    return 'saved'
}

function Write-KeyHint {
    Write-Note 'To add one later: click the HeySpeaky icon in the tray, click'
    Write-Note '"Add your OpenAI key", paste it and press Save.'
}

function Set-ApiKey {
    $fromCommand = Use-KeyFromCommand
    if ($fromCommand -ne 'saved') {
        if ($fromCommand -eq 'none') { Write-Step 'Your OpenAI API key' }
        $key = Read-ApiKey
        if (-not $key) {
            Write-Note 'Skipped. Nothing was changed.'
            return
        }
        Save-ApiKey $key
    }
    Write-Note 'The key is read on every request, so there is nothing to restart.'
    Write-Note 'To use it, click the HeySpeaky tray icon: Transcribed by > OpenAI.'
}

function Select-Backend {
    # Returns 'cloud' or 'local' to write into config.json, or $null to leave
    # an existing choice alone. Asked before the long download on purpose, so
    # the rest of the install can run while nobody is watching.
    $fromCommand = Use-KeyFromCommand
    if ($fromCommand -eq 'saved' -and $Backend -ne 'local') {
        return 'cloud'
    }
    $update = Test-Path -LiteralPath $ConfigFile
    if ($fromCommand -eq 'rejected' -and $Backend -ne 'local') {
        # A key in the command means OpenAI, so skip the question and ask for
        # a working key instead.
        $key = Read-ApiKey
        if ($key) {
            Save-ApiKey $key
            return 'cloud'
        }
        Write-Note 'No key for now.'
        Write-KeyHint
        if ($update) { return $null }
        return 'local'
    }
    if ($Backend -eq 'ask' -and $update) {
        return $null
    }

    $pick = $Backend
    if ($pick -eq 'ask') {
        Write-Step 'How should HeySpeaky turn your speech into text?'
        Write-Host ''
        Write-Host '    1  OpenAI   (recommended)' -ForegroundColor Green
        Write-Host '       Much more accurate, especially in Russian and German, and the'
        Write-Host '       only option that keeps up when you switch language in the'
        Write-Host '       middle of a sentence. Needs an OpenAI API key. Costs about'
        Write-Host '       $0.006 per minute of speech, roughly $3.60 a month at 20'
        Write-Host '       minutes a day. Your recordings are sent to OpenAI.'
        Write-Host ''
        Write-Host '    2  This computer'
        Write-Host '       Free, private and works offline, but noticeably less accurate,'
        Write-Host '       and it loses a language switch unless you pause at it.'
        Write-Host ''
        $answer = $null
        try { $answer = Read-Host '    Press Enter for OpenAI, or type 2 and Enter for this computer' } catch {}
        $answer = "$answer".Trim()
        if ($answer -eq '2') {
            $pick = 'local'
        } elseif ($answer -eq '' -and [Console]::IsInputRedirected) {
            # Nobody at the keyboard, as on a CI runner. Do not open a browser
            # and wait for a key that will never come.
            $pick = 'local'
        } else {
            $pick = 'openai'
        }
    }
    Write-Log "    backend chosen: $pick"

    if ($pick -eq 'local') {
        Write-Note 'This computer it is. Switch any time from the tray: Transcribed by.'
        return 'local'
    }
    if (Test-HaveKey) {
        Write-Note 'Found your saved OpenAI key, using it.'
        return 'cloud'
    }

    Write-Step 'Your OpenAI API key'
    $key = Read-ApiKey
    if (-not $key) {
        Write-Note 'No key for now, so HeySpeaky starts on this computer.'
        Write-KeyHint
        return 'local'
    }
    Save-ApiKey $key
    return 'cloud'
}

function Set-LocalModel {
    # Which local model to fall back on is a hardware question. Measured on a
    # laptop with no GPU: base answers in 1.2-1.7s, small takes 4-7s and
    # large-v3-turbo 17-19s, which is far too long to wait after a sentence.
    # With a CUDA card the big model is both fast and much better, so it wins.
    $code = 'import sys; sys.path.insert(0, sys.argv[1]); from heyspeaky import config; from heyspeaky.hardware import resolve_hardware; c = config.load(); device, _ = resolve_hardware(''auto'', ''auto''); c[''model''][''final''] = ''large-v3-turbo'' if device == ''cuda'' else ''base''; config.save(c); print(''local model: '' + c[''model''][''final''])'
    Invoke-Native 'Choosing the local model' $VenvPy @('-c', $code, $Root)
}

function Set-ConfigBackend([string]$Value) {
    # config.py is standard library only, so this runs before anything is
    # installed, and config.save() writes the file exactly as the app does.
    # Single quotes in the Python: Windows PowerShell mangles double quotes
    # inside arguments passed to native programs.
    $code = 'import sys; sys.path.insert(0, sys.argv[1]); from heyspeaky import config; c = config.load(); c[''transcription''][''backend''] = sys.argv[2]; config.save(c)'
    Invoke-Native 'Saving your choice' $VenvPy @('-c', $code, $Root, $Value)
}

# ---------------------------------------------------------------------------
# Getting the project
# ---------------------------------------------------------------------------

function Test-SafeToReplace([string]$Dir) {
    # The update deletes the old code before copying the new, so refuse any
    # folder that is not already a HeySpeaky install.
    if (-not (Test-Path -LiteralPath $Dir)) { return $true }
    if (-not (Get-ChildItem -LiteralPath $Dir -Force)) { return $true }
    return (Test-Path -LiteralPath (Join-Path $Dir 'run.py')) -and
           (Test-Path -LiteralPath (Join-Path $Dir 'install.ps1'))
}

function Get-Project {
    if (-not (Test-SafeToReplace $Root)) {
        throw "$Root already exists and is not a HeySpeaky folder. Choose another with -InstallDir, or empty it."
    }
    $stamp = [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $zip = Join-Path $env:TEMP "HeySpeaky-$stamp.zip"
    $tmp = Join-Path $env:TEMP "HeySpeaky-$stamp"
    try {
        Write-Note "from $RepoUrl ($Ref)"
        Invoke-WebRequest -Uri "$RepoUrl/archive/$Ref.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $inner = @(Get-ChildItem -LiteralPath $tmp -Directory)[0]
        if (-not $inner -or -not (Test-Path -LiteralPath (Join-Path $inner.FullName 'run.py'))) {
            throw 'The download did not contain HeySpeaky.'
        }
        New-Item -ItemType Directory -Force -Path $Root | Out-Null
        # Kept across updates. Everything else is replaced, so files removed
        # from the project do not linger in old installs.
        $keep = @('.venv', '.uv', 'config.json', 'logs')
        Get-ChildItem -LiteralPath $Root -Force |
            Where-Object { $keep -notcontains $_.Name } |
            Remove-Item -Recurse -Force
        # Copy, not Move: Move-Item cannot move a folder to another drive.
        Get-ChildItem -LiteralPath $inner.FullName -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $Root -Recurse -Force
        }
    } finally {
        Remove-Item -LiteralPath $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Move-FromOldNames {
    # An update from either old name keeps the settings and the key, and takes
    # the old shortcuts away so only one copy starts with Windows.
    foreach ($old in $LegacyNames) {
        Remove-Shortcuts $old
        $oldDir = Join-Path $env:LOCALAPPDATA "Programs\$old"
        $oldConfig = Join-Path $oldDir 'config.json'
        if ((Test-Path -LiteralPath $oldConfig) -and -not (Test-Path -LiteralPath $ConfigFile)) {
            Copy-Item -LiteralPath $oldConfig -Destination $ConfigFile
            Write-Note "kept your settings from $old"
        }
        $oldKey = Join-Path $env:APPDATA "$old\openai.key"
        if ((Test-Path -LiteralPath $oldKey) -and -not (Test-Path -LiteralPath $KeyFile)) {
            New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
            Copy-Item -LiteralPath $oldKey -Destination $KeyFile
            & icacls $KeyFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
            Write-Note "kept your OpenAI key from $old"
        }
        if ((Test-Path -LiteralPath $oldDir) -and ($oldDir -ne $Root)) {
            Write-Note "the old $old folder is still at $oldDir"
            Write-Note 'delete it once HeySpeaky works'
        }
    }
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

function Test-LongPathsEnabled {
    try {
        $key = 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem'
        return (Get-ItemProperty -Path $key -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled -eq 1
    } catch {
        return $false
    }
}

function Assert-CanInstall {
    if ([Environment]::OSVersion.Version.Major -lt 10) {
        throw 'HeySpeaky needs Windows 10 or 11.'
    }
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        throw 'HeySpeaky needs PowerShell 5 or newer, which ships with Windows 10.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'HeySpeaky needs 64-bit Windows. PyTorch has no 32-bit build.'
    }
    if ($Root.Length -gt $MaxRootLength -and -not (Test-LongPathsEnabled)) {
        throw ("The install folder path is too long ({0} characters, the limit is {1} on this PC):`n  {2}`nUse a shorter one, for example:  & `$s -InstallDir 'C:\HeySpeaky'" -f $Root.Length, $MaxRootLength, $Root)
    }
    # Checked here rather than when downloading, so a folder that cannot be
    # used fails the install before anything running has been stopped.
    if (-not $SelfPath -and -not (Test-SafeToReplace $Root)) {
        throw "$Root already exists and is not a HeySpeaky folder. Choose another with -InstallDir, or empty it."
    }
    if ($Root -like '*\OneDrive*') {
        Write-Warning "$Root is inside OneDrive, which will try to sync about a gigabyte of packages. A folder outside it is better."
    }
    $driveRoot = [IO.Path]::GetPathRoot($Root)
    if (-not (Test-Path -LiteralPath $driveRoot)) {
        throw "$driveRoot does not exist on this PC. Choose a folder on another drive with -InstallDir."
    }
    if (-not (Test-Path -LiteralPath $VenvDir)) {
        $drive = New-Object IO.DriveInfo ($driveRoot)
        $freeGB = $drive.AvailableFreeSpace / 1GB
        if ($freeGB -lt $MinFreeGB) {
            throw ("Only {0:N1} GB free on {1}. HeySpeaky needs about {2} GB." -f $freeGB, $drive.Name, $MinFreeGB)
        }
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Warning "This window is running as administrator. HeySpeaky will be set up for the account '$($env:USERNAME)'. If that is not the account you use every day, close this window and run the command in a normal one."
    }
}

function Confirm-VCRuntime {
    # PyTorch and ctranslate2 are built against the Visual C++ runtime. Most
    # PCs have it from some other program; a fresh Windows does not, and the
    # symptom is "DLL load failed" at the very end.
    $system = Join-Path $env:SystemRoot 'System32'
    if ((Test-Path -LiteralPath (Join-Path $system 'msvcp140.dll')) -and
        (Test-Path -LiteralPath (Join-Path $system 'vcruntime140_1.dll'))) {
        return
    }
    Write-Step 'Installing the Microsoft Visual C++ runtime'
    Write-Note 'PyTorch needs it and this PC does not have it. Windows will ask for permission.'
    $url = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
    $exe = Join-Path $env:TEMP 'vc_redist.x64.exe'
    try {
        Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
        $p = Start-Process -FilePath $exe -ArgumentList '/install', '/quiet', '/norestart' -Verb RunAs -Wait -PassThru
        # 1638: a newer version is already there. 3010: installed, and a
        # restart is recommended but not needed for this.
        if (@(0, 1638, 3010) -notcontains $p.ExitCode) {
            Write-Warning "The runtime installer exited with $($p.ExitCode). If HeySpeaky fails to start, install it by hand: $url"
        }
    } catch {
        Write-Warning "Skipped: $($_.Exception.Message). If HeySpeaky fails to start, install it by hand: $url"
    } finally {
        Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Python environment
# ---------------------------------------------------------------------------

function Get-Uv {
    $uv = Join-Path $UvDir 'uv.exe'
    if (Test-Path -LiteralPath $uv) {
        $have = ''
        try { $have = "$(& $uv --version)" } catch {}
        if ($have -like "uv $UvVersion*") { return $uv }
    }
    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
    $zip = Join-Path $env:TEMP "uv-$UvVersion.zip"
    try {
        Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
        $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        if ($hash -ne $UvSha256) {
            throw 'The uv download did not match its published checksum. Try again. If it keeps happening, something on this network is changing downloads.'
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $UvDir -Force
    } finally {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    }
    return $uv
}

function Test-Venv {
    # Reuse an environment only if uv built it from its own Python. Older
    # installers used whatever Python was on PATH, and those environments
    # break when that Python is upgraded or uninstalled.
    $cfg = Join-Path $VenvDir 'pyvenv.cfg'
    if (-not (Test-Path -LiteralPath $VenvPy) -or -not (Test-Path -LiteralPath $cfg)) { return $false }
    $match = Select-String -LiteralPath $cfg -Pattern '^home\s*=\s*(.+)$' | Select-Object -First 1
    if (-not $match) { return $false }
    $pythonHome = $match.Matches[0].Groups[1].Value.Trim()
    return $pythonHome.StartsWith((Join-Path $UvDir 'python'), [StringComparison]::OrdinalIgnoreCase)
}

# ---------------------------------------------------------------------------
# Progress window
# ---------------------------------------------------------------------------

function Get-InstallPlan {
    # Rough seconds per step on an ordinary connection. They only steer the
    # progress bar, and a wrong guess just makes the bar slow down.
    $fresh = -not (Test-Venv)
    $plan = New-Object System.Collections.ArrayList
    if (-not $SelfPath) { [void]$plan.Add(@{ Name = 'project'; Seconds = 5 }) }
    [void]$plan.Add(@{ Name = 'uv'; Seconds = 5 })
    if ($fresh) { [void]$plan.Add(@{ Name = 'python'; Seconds = 15 }) }
    if ($fresh) { $packages = 150 } else { $packages = 20 }
    [void]$plan.Add(@{ Name = 'packages'; Seconds = $packages })
    [void]$plan.Add(@{ Name = 'models'; Seconds = 30 })
    if (-not $NoStart) { [void]$plan.Add(@{ Name = 'start'; Seconds = 40 }) }
    return ,$plan
}

function Write-ProgressFile([string]$State, [string]$Label, [double]$Started, [double]$Expected, [double]$Finished, [double]$Share, [double]$After) {
    # Invariant culture, or a Russian Windows writes 0.25 as 0,25.
    $json = [string]::Format([Globalization.CultureInfo]::InvariantCulture,
        '{{"state":"{0}","label":"{1}","started":{2},"expected":{3},"finished_share":{4},"share":{5},"remaining_after":{6}}}',
        $State, $Label, $Started, $Expected, $Finished, $Share, $After)
    try {
        [IO.File]::WriteAllText($ProgressFile, $json, (New-Object Text.UTF8Encoding($false)))
        $Progress.Active = $true
    } catch {}
}

function Set-Progress([string]$Name, [string]$Label) {
    $plan = $Progress.Plan
    if (-not $plan) { return }
    $total = 0.0
    $before = 0.0
    $mine = -1.0
    foreach ($step in $plan) {
        if ($step.Name -eq $Name) {
            $mine = [double]$step.Seconds
        } elseif ($mine -lt 0) {
            $before += $step.Seconds
        }
        $total += $step.Seconds
    }
    if ($mine -lt 0 -or $total -le 0) { return }
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    Write-ProgressFile 'running' $Label $now $mine ($before / $total) ($mine / $total) ($total - $before - $mine)
}

function Complete-Progress([string]$State) {
    if ($Progress.Active) { Write-ProgressFile $State '' 0 1 1 0 0 }
}

function Start-WaitGame {
    # A window with the progress bar and a dinosaur game for the long
    # download. It needs only the tkinter in Python's standard library, so it
    # can open as soon as the environment exists, before any package does.
    if ($NoGame -or $env:CI -or [Console]::IsInputRedirected) { return }
    $game = Join-Path $Root 'tools\install_game.py'
    if (-not (Test-Path -LiteralPath $game) -or -not (Test-Path -LiteralPath $VenvPyW)) { return }
    try {
        $arguments = @(('"{0}"' -f $game), '--progress', ('"{0}"' -f $ProgressFile), '--parent', $PID)
        Start-Process -FilePath $VenvPyW -ArgumentList $arguments -WorkingDirectory $Root | Out-Null
        Write-Log '    opened the progress window'
    } catch {
        Write-Log "    the progress window did not open: $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# Shortcuts and launch
# ---------------------------------------------------------------------------

function New-Shortcut([string]$Path) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($Path)
    # pythonw.exe, not python.exe: this is what keeps a console off the screen.
    $sc.TargetPath       = $VenvPyW
    $sc.Arguments        = '"{0}"' -f $EntryFile
    $sc.WorkingDirectory = $Root
    $sc.WindowStyle      = 7
    $sc.Description      = 'HeySpeaky - hold Ctrl+Alt to dictate'
    # Its own icon. The Python it starts has none, and the Start menu showed
    # a blank window for it.
    if (Test-Path -LiteralPath $IconFile) {
        $sc.IconLocation = "$IconFile,0"
    } else {
        $sc.IconLocation = "$VenvPyW,0"
    }
    $sc.Save()
    Write-Note "created $Path"
}

function Test-ShortcutPointsHere([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $shell = New-Object -ComObject WScript.Shell
        $arguments = $shell.CreateShortcut($Path).Arguments
        return $arguments.IndexOf($EntryFile, [StringComparison]::OrdinalIgnoreCase) -ge 0
    } catch {
        return $false
    }
}

function Read-LogSince([string]$Path, [long]$Offset) {
    # Only what this start wrote. The log rotates at 1 MB, so a file shorter
    # than the offset has started over.
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            if ($stream.Length -lt $Offset) { $Offset = 0 }
            $null = $stream.Seek($Offset, [IO.SeekOrigin]::Begin)
            $reader = New-Object IO.StreamReader($stream, (New-Object Text.UTF8Encoding($false)))
            return $reader.ReadToEnd()
        } finally {
            $stream.Dispose()
        }
    } catch {
        return ''
    }
}

function Start-HeySpeaky {
    $log = Join-Path $Root 'logs\heyspeaky.log'
    $offset = 0
    if (Test-Path -LiteralPath $log) { $offset = (Get-Item -LiteralPath $log).Length }
    $proc = Start-Process -FilePath $VenvPyW -ArgumentList ('"{0}"' -f $EntryFile) -WorkingDirectory $Root -PassThru

    # HeySpeaky loads its speech engine as it starts and logs the result, so
    # waiting for that line checks the engine without loading it a second
    # time. The first start after installing is slow: every file is new to
    # Python and PyTorch comes off a cold disk, 29 seconds on a fast laptop
    # before the engine even begins. A slow PC gets three minutes, and one
    # still loading after that gets a warning rather than a failure.
    Write-Note 'loading the speech model, the first start can take a minute or two'
    $broken = 'Engine error|Fatal error'
    $new = ''
    for ($i = 0; $i -lt 360; $i++) {
        Start-Sleep -Milliseconds 500
        $new = Read-LogSince $log $offset
        if ($new -match 'Engine ready') {
            Write-Note "running and ready to dictate (PID $($proc.Id))"
            return
        }
        if ($new -match $broken -or $proc.HasExited) { break }
    }
    if ($new -match 'Another instance is already running') {
        Write-Warning 'Another copy of HeySpeaky was already running, so that one stays. Quit it from the tray and start HeySpeaky from the Start Menu to use this one.'
        return
    }
    if (-not $proc.HasExited -and $new -notmatch $broken) {
        Write-Warning "HeySpeaky is still loading (PID $($proc.Id)). If the tray icon does not say Ready within a few minutes, double-click CHECKUP.bat in $Root."
        return
    }

    Write-Host ''
    Write-Host '    what HeySpeaky logged' -ForegroundColor Yellow
    @($new -split "`r?`n" | Where-Object { $_ }) | Select-Object -Last 15 | ForEach-Object { Write-Note $_ }
    $stdout = Join-Path $Root 'logs\stdout.log'
    if ((Test-Path -LiteralPath $stdout) -and (Get-Item -LiteralPath $stdout).Length -gt 0) {
        Write-Host '    last lines of logs\stdout.log' -ForegroundColor Yellow
        Get-Content -LiteralPath $stdout -Tail 15 | ForEach-Object { Write-Note $_ }
    }
    if ($proc.HasExited) {
        throw 'HeySpeaky installed but did not start. The log lines above say why.'
    }
    throw 'HeySpeaky started, but its speech engine did not load. The log lines above say why.'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Invoke-Install {
    Assert-CanInstall
    $Progress.Plan = Get-InstallPlan

    Write-Step 'Stopping any running copy'
    Stop-HeySpeaky

    if (-not $SelfPath) {
        Write-Step "Downloading HeySpeaky into $Root"
        Set-Progress 'project' 'Downloading HeySpeaky'
        Get-Project
    }
    if (-not (Test-Path -LiteralPath $EntryFile)) {
        throw "run.py is not in $Root. Run this script from inside the HeySpeaky folder."
    }
    Move-FromOldNames

    $choice = Select-Backend

    Confirm-VCRuntime

    Set-ProcessEnv 'UV_CACHE_DIR' (Join-Path $UvDir 'cache')
    Set-ProcessEnv 'UV_PYTHON_INSTALL_DIR' (Join-Path $UvDir 'python')
    # Slow connections time out on the PyTorch download at uv's default.
    Set-ProcessEnv 'UV_HTTP_TIMEOUT' '300'
    Set-ProcessEnv 'PYTHONUTF8' '1'

    Write-Step 'Getting uv'
    Set-Progress 'uv' 'Getting ready'
    $uv = Get-Uv

    if (-not (Test-Venv)) {
        Write-Step 'Getting Python 3.12 for HeySpeaky (your own Python is not touched)'
        Set-Progress 'python' 'Getting Python'
        Invoke-Native 'Creating the environment' $uv @('venv', '--clear', '--managed-python', '--python', $PythonRequest, $VenvDir)
    }
    Start-WaitGame

    if ($choice) {
        Set-ConfigBackend $choice
        Set-LocalModel
    }

    Write-Step 'Installing packages (about 1 GB and a few minutes the first time)'
    Set-Progress 'packages' 'Installing packages, the longest part'
    # The lock file pins every package to the versions this was tested with.
    # --no-build refuses to compile anything from source: every package has a
    # wheel, and the one that did not (halo) ships in vendor/.
    Invoke-Native 'Installing packages' $uv @(
        'pip', 'sync', '--python', $VenvPy, '--no-build',
        '--find-links', (Join-Path $Root 'vendor'),
        (Join-Path $Root 'requirements.lock')
    )

    Write-Step 'Checking the install and downloading the speech model'
    Set-Progress 'models' 'Downloading the speech model'
    $check = @((Join-Path $Root 'tools\doctor.py'), '--install')
    # Starting HeySpeaky below loads the engine and checks it, so loading it
    # here as well would only double the wait. -NoStart still checks it here.
    if (-not $NoStart) { $check += '--no-engine' }
    Invoke-Native 'The check' $VenvPy $check

    Write-Step 'Creating shortcuts'
    try {
        Invoke-Native 'Drawing the icon' $VenvPy @((Join-Path $Root 'tools\make_icon.py'), $IconFile)
    } catch {
        # A shortcut with a plain icon still starts HeySpeaky.
        Write-Note 'The icon could not be drawn; the shortcuts get a plain one.'
    }
    if ($NoAutostart) {
        # Only if it starts this copy. Another install's autostart is not ours
        # to remove.
        if (Test-ShortcutPointsHere $StartupLnk) { Remove-Item -LiteralPath $StartupLnk -Force }
        Write-Note 'not starting with Windows (-NoAutostart)'
    } else {
        New-Shortcut $StartupLnk
    }
    New-Shortcut $MenuLnk

    if (-not $NoStart) {
        Write-Step 'Starting HeySpeaky'
        Set-Progress 'start' 'Starting HeySpeaky'
        Start-HeySpeaky
    }
    Complete-StepTime
    Complete-Progress 'done'

    if ($choice -eq 'cloud') {
        $engineState = 'OpenAI'
    } elseif ($choice -eq 'local') {
        $engineState = 'this computer'
    } else {
        $engineState = 'as before'
    }
    if (Test-HaveKey) { $keyState = 'saved' } else { $keyState = 'none' }
    if ($NoAutostart) { $autoState = 'off' } else { $autoState = 'on' }

    Write-Host ''
    Write-Host '--------------------------------------------------------------' -ForegroundColor Green
    Write-Host ' HeySpeaky is installed.' -ForegroundColor Green
    Write-Host '--------------------------------------------------------------' -ForegroundColor Green
    Write-Host @"

  Hold Ctrl+Alt       record while held, release and the text is typed
  Tap Ctrl+Alt twice  hands-free, stops when you stop talking
  Ctrl+Alt+Win        teach it a word it got wrong
  Any other key       cancels

  Transcribed by   $engineState
  OpenAI key       $keyState
  Autostart        $autoState
  Folder           $Root

  Everything else is in the HeySpeaky icon in the tray - click it:
    Language, +          the languages you speak (just type to find one)
    Transcribed by       OpenAI or this computer
    OpenAI key           click it, paste your key, Save
    Model on this laptop tiny to large; bigger hears better, runs slower

  Something wrong?   double-click CHECKUP.bat in the folder above
  Remove it          double-click UNINSTALL.bat in the same folder

  To add or change your OpenAI key: click the tray icon, click
  "OpenAI key", paste it and press Save. Keys are made at $KeysPage
"@
}

$failed = $false
$savedEncoding = $null
Push-Location -LiteralPath $env:TEMP
try {
    # Native programs write UTF-8. Without this, a Cyrillic folder name in an
    # error message comes out as mojibake on a Russian or Kazakh Windows.
    try {
        $savedEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
    } catch {}
    # Old Windows 10 builds default to TLS 1.0, which GitHub refuses.
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch {}

    Set-Content -LiteralPath $LogFile -Value "HeySpeaky installer, $(Get-Date -Format s)" -Encoding UTF8
    Write-Log ("PowerShell {0} | {1} | {2} | root {3}" -f $PSVersionTable.PSVersion, [Environment]::OSVersion.VersionString, $env:PROCESSOR_ARCHITECTURE, $Root)

    if ($SetApiKey) {
        Set-ApiKey
    } else {
        Invoke-Install
    }
} catch {
    $failed = $true
    Complete-Progress 'failed'
    Write-Log "FAILED: $($_.Exception.Message)"
    Write-Log "$($_.ScriptStackTrace)"
    Write-Host ''
    Write-Host 'HeySpeaky was not installed.' -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Write-Host "  Full log: $LogFile"
    Write-Host "  If you open an issue, attach that file: $RepoUrl/issues"
} finally {
    try { [Threading.Thread]::CurrentThread.CurrentUICulture = $SavedUICulture } catch {}
    foreach ($name in $SavedEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $SavedEnv[$name], 'Process')
    }
    if ($savedEncoding) {
        try { [Console]::OutputEncoding = $savedEncoding } catch {}
    }
    Pop-Location
}

# Run as a file, a real exit code is useful and closes nothing. Piped into iex
# it would close the user's window, so there it is skipped.
if ($failed -and $SelfPath) { exit 1 }

}
