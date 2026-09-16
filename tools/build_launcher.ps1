param([string]$Destination = "build/launcher")

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$launcherProject = Join-Path $projectRoot "launcher\ChessBotLauncher.csproj"
$outputDirectory = Join-Path $projectRoot $Destination

dotnet publish $launcherProject -c Release --self-contained false `
    -p:DebugType=None -p:DebugSymbols=false -o $outputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo compilar ChessBot Launcher."
}

$executable = Join-Path $outputDirectory "ChessBot Launcher.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "ChessBot.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $executable
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Jugar, entrenar y administrar ChessBot"
$shortcut.IconLocation = "$executable,0"
$shortcut.Save()

Write-Host "Lanzador: $executable"
Write-Host "Acceso directo: $shortcutPath"
