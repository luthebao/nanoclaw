# Nanoclaw installer for Windows
# Usage: iwr -useb https://openclaw.ai/install.ps1 | iex

param(
    [ValidateSet("pypi", "git")]
    [string]$InstallMethod = $(if ($env:NANOCLAW_INSTALL_METHOD) { $env:NANOCLAW_INSTALL_METHOD } else { "pypi" }),
    [string]$GitDir = $(if ($env:NANOCLAW_GIT_DIR) { $env:NANOCLAW_GIT_DIR } else { Join-Path $HOME "nanoclaw" })
)

$ErrorActionPreference = "Stop"

$PkgName = "nanoclaw-ai"
$RepoUrl = "https://github.com/luthebao/nanoclaw.git"

function Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Ok "uv already installed"
        return
    }

    Info "Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    $userBin = Join-Path $HOME ".local\bin"
    if (Test-Path $userBin) {
        $env:Path = "$userBin;$env:Path"
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail "uv installation failed. Install manually: https://docs.astral.sh/uv/"
    }

    Ok "uv installed"
}

function Install-FromPyPI {
    Info "Installing $PkgName from PyPI via uv tool..."
    uv tool install --upgrade $PkgName
    Ok "Installed $PkgName"
}

function Install-FromGit {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail "Git is required for InstallMethod=git. Install from https://git-scm.com/download/win"
    }

    Info "Installing from git checkout: $RepoUrl"
    if (-not (Test-Path (Join-Path $GitDir ".git"))) {
        git clone $RepoUrl $GitDir
    } else {
        Info "Repo exists at $GitDir, updating..."
        git -C $GitDir pull --rebase
    }

    uv tool install --upgrade $GitDir
    Ok "Installed nanoclaw from $GitDir"
}

function Ensure-NanoclawPathNotice {
    if (Get-Command nanoclaw -ErrorAction SilentlyContinue) {
        return
    }

    Warn "'nanoclaw' not found in current PATH yet."
    Warn "Open a new terminal or add your uv tool bin path to PATH."
}

Info "Nanoclaw Installer"
Ensure-Uv

if ($InstallMethod -eq "git") {
    Install-FromGit
} else {
    Install-FromPyPI
}

Ensure-NanoclawPathNotice

if (Get-Command nanoclaw -ErrorAction SilentlyContinue) {
    try {
        $ver = (nanoclaw --version).Trim()
        Ok "nanoclaw version: $ver"
    } catch {
        Ok "nanoclaw installed"
    }
    Ok "Run: nanoclaw onboard"
} else {
    Ok "Install completed"
}
