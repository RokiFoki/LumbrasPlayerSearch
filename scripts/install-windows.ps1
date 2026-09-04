<#
.SYNOPSIS
    Install and register the Lumbras & Chess Genie native helper for Chrome on
    Windows.

.DESCRIPTION
    Mirrors scripts/install-macos.sh. It copies the native helper to a stable
    per-user location outside the repository (so moving the repository does not
    break the install), renders Chrome's native-messaging manifest with
    render-native-manifest.py, and registers the manifest under
    HKCU\Software\Google\Chrome\NativeMessagingHosts.

.PARAMETER ExtensionId
    The 32-character unpacked-extension ID from chrome://extensions.

.PARAMETER InstallRoot
    Where the helper is installed. Defaults to %LOCALAPPDATA%\LumbrasChessGenie.
    Overridable for tests.

.PARAMETER RegistryRoot
    The Chrome NativeMessagingHosts registry key. Defaults to the real Chrome
    location. Overridable for tests.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 abcdefghijklmnopabcdefghijklmnop
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ExtensionId,

    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'LumbrasChessGenie'),

    [string]$RegistryRoot = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HostName = 'app.chessgenie.local_games'

if ($ExtensionId -notmatch '^[a-p]{32}$') {
    throw "Extension ID must be exactly 32 letters from a through p (copied from chrome://extensions)."
}

function Get-Python3 {
    # Prefer the py launcher pinned to Python 3; it cannot resolve to 2.x.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c 'import sys' 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = 'py'; Pre = @('-3') } }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = 'python'; Pre = @() } }
    }
    throw "Python 3 was not found on PATH. Install Python 3 and ensure 'python' or 'py' is available."
}

$scriptDir = $PSScriptRoot
$repositoryDir = Split-Path -Parent $scriptDir
$sourceHost = Join-Path $repositoryDir 'native-host'
$renderScript = Join-Path $scriptDir 'render-native-manifest.py'

$installedHost = Join-Path $InstallRoot 'native-host'
$installedScid = Join-Path $installedHost 'scid'
$launcher = Join-Path $installedHost 'launch.bat'
$manifest = Join-Path $InstallRoot ($HostName + '.json')

# Copy the helper (never symlink), so a later repository move cannot break it.
if (Test-Path -LiteralPath $installedHost) {
    Remove-Item -LiteralPath $installedHost -Recurse -Force
}
New-Item -ItemType Directory -Path $installedScid -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceHost 'host.py') -Destination $installedHost -Force
Copy-Item -LiteralPath (Join-Path $sourceHost 'launch.bat') -Destination $installedHost -Force
Copy-Item -Path (Join-Path $sourceHost 'scid\*.tcl') -Destination $installedScid -Force

# render-native-manifest.py is the single source of truth for the manifest JSON.
$python = Get-Python3
& $python.Exe @($python.Pre) $renderScript `
    --extension-id $ExtensionId `
    --launcher $launcher `
    --output $manifest
if ($LASTEXITCODE -ne 0) {
    throw "Failed to render the native-messaging manifest."
}

# Chrome finds the host on Windows through the registry: a key named for the
# host whose default value is the absolute path to the manifest file.
$hostKey = Join-Path $RegistryRoot $HostName
New-Item -Path $hostKey -Force | Out-Null
Set-ItemProperty -Path $hostKey -Name '(default)' -Value (Resolve-Path -LiteralPath $manifest).Path

Write-Host "Installed native helper:        $installedHost"
Write-Host "Installed native-host manifest: $manifest"
Write-Host "Registered native-host key:     $hostKey"
Write-Host ""
Write-Host "Fully quit Chrome (close every window, including background apps) and reopen it before testing the extension."
