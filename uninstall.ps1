<#
.SYNOPSIS
    Removes HeySpeaky from this PC: every copy, its shortcuts, the saved OpenAI
    key and the downloaded speech models.

.DESCRIPTION
    Paste this into PowerShell:

        irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/uninstall.ps1 | iex

    Copies installed under the older names VoiceType and SpeakIt are removed
    too. A folder is only deleted if it is an installed copy. A git
    clone is left where it is, so this never deletes someone's working copy.

.PARAMETER InstallDir
    One more folder to remove, for a copy somewhere unusual whose shortcuts are
    already gone. UNINSTALL.bat passes its own folder.
#>
param(
    [string]$InstallDir
)

# Empty when piped into iex.
$SelfPath = $PSCommandPath

# Piped into iex, a script runs in the caller's own session. The block keeps
# its variables out of that session, and a failure from closing the window.
& {

$ErrorActionPreference = 'Stop'

# Messages from PowerShell and Windows come out in the Windows display
# language. This script's own are English, so everything is.
$SavedUICulture = [Threading.Thread]::CurrentThread.CurrentUICulture
try {
    [Threading.Thread]::CurrentThread.CurrentUICulture = [Globalization.CultureInfo]::GetCultureInfo('en-US')
} catch {}

$Names       = @('HeySpeaky', 'SpeakIt', 'VoiceType')
$StartupDir  = [Environment]::GetFolderPath('Startup')
$ProgramsDir = [Environment]::GetFolderPath('Programs')
if ($env:HF_HUB_CACHE) {
    $ModelCache = $env:HF_HUB_CACHE
} elseif ($env:HF_HOME) {
    $ModelCache = Join-Path $env:HF_HOME 'hub'
} else {
    $ModelCache = Join-Path $env:USERPROFILE '.cache\huggingface\hub'
}

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Note([string]$Text) {
    Write-Host "    $Text"
}

function Remove-Path([string]$Path) {
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force
        Write-Note "removed $Path"
    } catch {
        Write-Warning "Could not remove all of $Path. $($_.Exception.Message) Close anything using it and run this again."
    }
}

# ---------------------------------------------------------------------------
# Finding every copy
# ---------------------------------------------------------------------------

$Folders = New-Object System.Collections.Generic.List[string]

function Add-Folder([string]$Dir) {
    if (-not $Dir) { return }
    try { $full = [IO.Path]::GetFullPath($Dir).TrimEnd('\') } catch { return }
    if ((Test-Path -LiteralPath $full) -and -not ($Folders -contains $full)) {
        $Folders.Add($full)
    }
}

function Get-Shortcuts {
    foreach ($name in $Names) {
        $menu = Join-Path $ProgramsDir $name
        foreach ($lnk in @((Join-Path $StartupDir "$name.lnk"), (Join-Path $menu "$name.lnk"))) {
            if (Test-Path -LiteralPath $lnk) { $lnk }
        }
    }
}

function Get-ShortcutFolder([string]$Path) {
    # The shortcuts start pythonw.exe with run.py as the argument, so the copy
    # is wherever that run.py is.
    try {
        $shell = New-Object -ComObject WScript.Shell
        $target = $shell.CreateShortcut($Path).Arguments.Trim().Trim('"')
        if ($target -like '*run.py') { return Split-Path -Parent $target }
    } catch {}
    return $null
}

function Test-InstalledCopy([string]$Dir) {
    return (Test-Path -LiteralPath (Join-Path $Dir 'run.py')) -and
           (Test-Path -LiteralPath (Join-Path $Dir 'install.ps1')) -and
           -not (Test-Path -LiteralPath (Join-Path $Dir '.git'))
}

# ---------------------------------------------------------------------------
# Stopping
# ---------------------------------------------------------------------------

function Stop-Everything {
    $all = @(Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" -ErrorAction SilentlyContinue)
    if (-not $all) { return }

    $needles = @($Names) + @($Folders)
    $isOurs = {
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
    $mains = @($all | Where-Object { $_.CommandLine -like '*run.py*' -and (& $isOurs $_.CommandLine) })
    foreach ($m in $mains) { $targets.Add($m) }
    $mainIds = @($mains | ForEach-Object { $_.ProcessId })

    # The transcription worker, including orphans whose parent is gone.
    foreach ($p in $all) {
        if ($p.CommandLine -notlike '*spawn_main*') { continue }
        $isChild  = $mainIds -contains $p.ParentProcessId
        $isOrphan = (-not $live.ContainsKey($p.ParentProcessId)) -and (& $isOurs $p.CommandLine)
        if ($isChild -or $isOrphan) { $targets.Add($p) }
    }

    foreach ($t in ($targets | Sort-Object ProcessId -Unique)) {
        Write-Note "stopping PID $($t.ProcessId)"
        try { Stop-Process -Id $t.ProcessId -Force -ErrorAction Stop } catch {}
    }
    # Windows keeps a folder locked for a moment after the last process in it
    # exits.
    if ($targets.Count -gt 0) { Start-Sleep -Seconds 2 }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Invoke-Uninstall {
    foreach ($name in $Names) {
        Add-Folder (Join-Path $env:LOCALAPPDATA "Programs\$name")
    }
    Add-Folder $InstallDir
    $shortcuts = @(Get-Shortcuts)
    foreach ($lnk in $shortcuts) {
        Add-Folder (Get-ShortcutFolder $lnk)
    }

    Write-Step 'Stopping HeySpeaky'
    Stop-Everything

    Write-Step 'Removing shortcuts'
    foreach ($lnk in $shortcuts) { Remove-Path $lnk }
    foreach ($name in $Names) {
        $menu = Join-Path $ProgramsDir $name
        if ((Test-Path -LiteralPath $menu) -and -not (Get-ChildItem -LiteralPath $menu -Force)) {
            Remove-Path $menu
        }
    }

    Write-Step 'Removing the program'
    $kept = @()
    foreach ($dir in $Folders) {
        if (Test-InstalledCopy $dir) {
            Remove-Path $dir
        } elseif (Test-Path -LiteralPath (Join-Path $dir '.git')) {
            $kept += $dir
        }
    }
    if (-not $Folders.Count) { Write-Note 'no installed copy found' }

    Write-Step 'Removing your saved OpenAI key'
    $keyDirs = @($Names | ForEach-Object { Join-Path $env:APPDATA $_ } | Where-Object { Test-Path -LiteralPath $_ })
    foreach ($dir in $keyDirs) { Remove-Path $dir }
    if (-not $keyDirs) { Write-Note 'none saved' }

    Write-Step 'Removing the downloaded speech models'
    $models = @()
    if (Test-Path -LiteralPath $ModelCache) {
        $models = @(Get-ChildItem -LiteralPath $ModelCache -Directory | Where-Object {
            $_.Name -like 'models--Systran--faster-whisper-*' -or
            $_.Name -like 'models--mobiuslabsgmbh--faster-whisper-*'
        })
    }
    foreach ($model in $models) { Remove-Path $model.FullName }
    if (-not $models) { Write-Note 'none found' }

    Write-Host ''
    Write-Host 'HeySpeaky is uninstalled.' -ForegroundColor Green
    if ($kept) {
        Write-Host ''
        Write-Host 'Left alone, because they are git clones. Delete them yourself if you want:'
        foreach ($dir in $kept) { Write-Host "    $dir" }
    }
}

$failed = $false
$savedLocation = Get-Location
Set-Location -LiteralPath $env:TEMP
try {
    Invoke-Uninstall
} catch {
    $failed = $true
    Write-Host ''
    Write-Host 'The uninstall stopped.' -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
} finally {
    try { [Threading.Thread]::CurrentThread.CurrentUICulture = $SavedUICulture } catch {}
    # The window may have been inside a folder that no longer exists.
    if (Test-Path -LiteralPath $savedLocation.Path) {
        Set-Location -LiteralPath $savedLocation.Path
    } else {
        Set-Location -LiteralPath $env:USERPROFILE
    }
    # UNINSTALL.bat runs a temporary copy of this script.
    if ($SelfPath -and $SelfPath -like "$env:TEMP\HeySpeaky-uninstall.ps1") {
        Remove-Item -LiteralPath $SelfPath -Force -ErrorAction SilentlyContinue
    }
}

# Only a script run from a file may exit. Piped into iex, exit would close
# the window with the message still in it.
if ($failed -and $SelfPath) { exit 1 }

}
