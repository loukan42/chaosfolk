# Install Chaosfolk on Windows: the engine, its browser and the skill for your coding agents.
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.ps1 | iex"
# Run it again to update. $env:CHAOSFOLK_SOURCE installs another version, for example a release archive;
# $env:CHAOSFOLK_NO_MODIFY_PATH = '1' leaves your PATH unchanged.
$ErrorActionPreference = 'Stop'

$source = if ($env:CHAOSFOLK_SOURCE) { $env:CHAOSFOLK_SOURCE } else { 'https://github.com/loukan42/chaosfolk/archive/refs/heads/main.zip' }

function Invoke-Step($label) {
    if ($LASTEXITCODE -ne 0) { throw "Chaosfolk installation stopped: $label failed (exit code $LASTEXITCODE)." }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv, which installs Python and Chaosfolk without touching your system Python...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host 'Installing the Chaosfolk engine...'
uv tool install --force --python '>=3.12' "chaosfolk @ $source"
Invoke-Step 'uv tool install'
if (-not $env:CHAOSFOLK_NO_MODIFY_PATH) {
    # Windows PowerShell turns native stderr into errors; uv only reports here whether PATH changed.
    try { uv tool update-shell *> $null } catch { }
}

$bin = (uv tool dir --bin).Trim()
& (Join-Path $bin 'chaosfolk.exe') setup @args
Invoke-Step 'chaosfolk setup'
Write-Host 'Open a new terminal to use the chaosfolk command yourself.'
