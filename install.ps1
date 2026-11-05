# Install Chaosfolk on Windows: the engine, its browser and the skill for your coding agents.
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/loukan42/chaosfolk/v0.8.0/install.ps1 | iex"
# Run it again to update. Read docs/security.md before using it in a managed environment.
#
# Environment variables:
#   CHAOSFOLK_VERSION          release to install (default: the version this script was published with)
#   CHAOSFOLK_SOURCE           archive URL or local file instead of the GitHub release archive (internal mirror)
#   CHAOSFOLK_SHA256           expected SHA-256 of the archive; the installation stops on a mismatch
#   CHAOSFOLK_REQUIRE_UV=1     never download uv; fail when it is not already installed
#   CHAOSFOLK_UV_VERSION       uv version downloaded when uv is missing (default below)
#   CHAOSFOLK_UV_SHA256        expected SHA-256 of that version's uv installer script (required with CHAOSFOLK_UV_VERSION)
#   CHAOSFOLK_NO_MODIFY_PATH=1 leave your PATH unchanged
$ErrorActionPreference = 'Stop'

$version = if ($env:CHAOSFOLK_VERSION) { $env:CHAOSFOLK_VERSION } else { '0.8.0' }
$source = if ($env:CHAOSFOLK_SOURCE) { $env:CHAOSFOLK_SOURCE } else { "https://github.com/loukan42/chaosfolk/archive/refs/tags/v$version.zip" }
# The uv installer script is checked against this SHA-256 before it runs. It is the GitHub release asset
# uv-installer.ps1 of that version, which verifies the checksum of the uv binary it downloads.
$defaultUvVersion = '0.13.6'
$defaultUvSha256 = 'd00580051699bee58a2e2d9b925f45788b35f7e0fff7966fd5bedfc3c547dc7d'
$uvVersion = if ($env:CHAOSFOLK_UV_VERSION) { $env:CHAOSFOLK_UV_VERSION } else { $defaultUvVersion }

function Invoke-Step($label) {
    if ($LASTEXITCODE -ne 0) { throw "Chaosfolk installation stopped: $label failed (exit code $LASTEXITCODE)." }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if ($env:CHAOSFOLK_REQUIRE_UV) {
        throw 'Chaosfolk installation stopped: uv is not installed and CHAOSFOLK_REQUIRE_UV is set. Install uv or Python 3.12+ with your package manager first.'
    }
    if ($env:CHAOSFOLK_UV_SHA256) { $uvSha256 = $env:CHAOSFOLK_UV_SHA256 }
    elseif ($uvVersion -eq $defaultUvVersion) { $uvSha256 = $defaultUvSha256 }
    else { throw "Chaosfolk installation stopped: CHAOSFOLK_UV_VERSION=$uvVersion needs CHAOSFOLK_UV_SHA256, the SHA-256 of that version's uv-installer.ps1." }
    Write-Host "Installing uv $uvVersion, which installs Python and Chaosfolk without touching your system Python..."
    $uvInstaller = Join-Path ([System.IO.Path]::GetTempPath()) ("uv-installer-" + [System.IO.Path]::GetRandomFileName() + ".ps1")
    try {
        Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-installer.ps1" -OutFile $uvInstaller -UseBasicParsing
        $uvScript = [System.IO.File]::ReadAllBytes($uvInstaller)
    } finally {
        Remove-Item -Force -LiteralPath $uvInstaller -ErrorAction SilentlyContinue
    }
    # The bytes that are hashed are the bytes that run: the script is read once and executed from memory.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $uvActual = -join ($sha.ComputeHash($uvScript) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
    if ($uvActual -ne $uvSha256.ToLowerInvariant()) {
        throw "Chaosfolk installation stopped: uv installer checksum mismatch (expected $uvSha256, got $uvActual)."
    }
    if ($env:CHAOSFOLK_NO_MODIFY_PATH) { $env:UV_NO_MODIFY_PATH = '1' }
    [System.Text.Encoding]::UTF8.GetString($uvScript) | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("chaosfolk-" + [System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $work | Out-Null
$name = Split-Path -Leaf $source
if ($name -notmatch '\.(zip|tar\.gz|tgz|whl)$') { $name = 'chaosfolk.zip' }
$archive = Join-Path $work $name
try {
    if ($source -match '^https?://') {
        Write-Host "Downloading $source ..."
        Invoke-WebRequest -Uri $source -OutFile $archive -UseBasicParsing
    } else {
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Chaosfolk installation stopped: $source is not a file." }
        Copy-Item -LiteralPath $source -Destination $archive
    }

    if ($env:CHAOSFOLK_SHA256) {
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $env:CHAOSFOLK_SHA256.ToLowerInvariant()) {
            throw "Chaosfolk installation stopped: archive checksum mismatch (expected $env:CHAOSFOLK_SHA256, got $actual)."
        }
        Write-Host 'Archive checksum verified.'
    } else {
        Write-Warning 'CHAOSFOLK_SHA256 is not set; the archive is trusted from HTTPS alone. Release notes list the checksum.'
    }

    Write-Host 'Installing the Chaosfolk engine...'
    $uri = ([System.Uri]$archive).AbsoluteUri
    uv tool install --force --python '>=3.12' "chaosfolk @ $uri"
    Invoke-Step 'uv tool install'
} finally {
    Remove-Item -Recurse -Force -LiteralPath $work -ErrorAction SilentlyContinue
}

if (-not $env:CHAOSFOLK_NO_MODIFY_PATH) {
    # Windows PowerShell turns native stderr into errors; uv only reports here whether PATH changed.
    try { uv tool update-shell *> $null } catch { }
}

$bin = (uv tool dir --bin).Trim()
& (Join-Path $bin 'chaosfolk.exe') setup @args
Invoke-Step 'chaosfolk setup'
Write-Host 'Open a new terminal to use the chaosfolk command yourself.'
