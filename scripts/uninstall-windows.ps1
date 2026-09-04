<#
.SYNOPSIS
    Remove the Lumbras & Chess Genie native helper and its Chrome registration
    on Windows.

.DESCRIPTION
    Mirrors scripts/uninstall-macos.sh. It deletes the Chrome registry value and
    the installed helper. With -RemoveConfig it also deletes the saved
    config.json (the Scid and database paths).

.PARAMETER InstallRoot
    Where the helper was installed. Defaults to %LOCALAPPDATA%\LumbrasChessGenie.

.PARAMETER RegistryRoot
    The Chrome NativeMessagingHosts registry key. Defaults to the real Chrome
    location.

.PARAMETER ConfigPath
    The saved configuration file. Defaults to
    %APPDATA%\LubrasChessGenie\config.json (as host.py resolves it).

.PARAMETER RemoveConfig
    Also delete the saved configuration.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1 -RemoveConfig
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'LumbrasChessGenie'),

    [string]$RegistryRoot = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts',

    [string]$ConfigPath = (Join-Path $env:APPDATA 'LubrasChessGenie\config.json'),

    [switch]$RemoveConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HostName = 'app.chessgenie.local_games'

$hostKey = Join-Path $RegistryRoot $HostName
if (Test-Path -Path $hostKey) {
    Remove-Item -Path $hostKey -Recurse -Force
    Write-Host "Removed native-host registration."
}

$manifest = Join-Path $InstallRoot ($HostName + '.json')
if (Test-Path -LiteralPath $manifest) {
    Remove-Item -LiteralPath $manifest -Force
    Write-Host "Removed native-host manifest."
}

$installedHost = Join-Path $InstallRoot 'native-host'
if (Test-Path -LiteralPath $installedHost) {
    Remove-Item -LiteralPath $installedHost -Recurse -Force
    Write-Host "Removed installed native helper."
}

if ($RemoveConfig -and (Test-Path -LiteralPath $ConfigPath)) {
    Remove-Item -LiteralPath $ConfigPath -Force
    Write-Host "Removed native-host configuration."
}
