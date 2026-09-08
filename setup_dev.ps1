<#
.SYNOPSIS
    One-Command Developer Environment Bootstrap for VMAF Quality Assessment Application.

.DESCRIPTION
    Bootstraps the local development environment:
    1. Detects or validates Python >= 3.10 runtime
    2. Creates or refreshes the local virtual environment (.venv)
    3. Installs and upgrades core dependencies from requirements.txt
    4. Executes preflight checks (FFmpeg, libvmaf, VMAF models, capture storage, Git hooks)
    5. Runs the regression test suite (69 tests)
    6. Emits developer quickstart instructions

.PARAMETER SkipTests
    Skip running regression tests.

.PARAMETER SkipHooks
    Skip installing the Git pre-commit hook.

.PARAMETER RecreateVenv
    Force deletion and clean recreation of the virtual environment (.venv).
    Use this to test and validate cold-start environment provisioning locally.

.PARAMETER PythonExe
    Explicit path to a Python >= 3.10 executable to use for venv creation.

.EXAMPLE
    .\setup_dev.ps1
    .\setup_dev.ps1 -SkipTests
    .\setup_dev.ps1 -RecreateVenv
#>

[CmdletBinding()]
param (
    [switch]$SkipTests,
    [switch]$SkipHooks,
    [switch]$RecreateVenv,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " VMAF APP -- ONE-COMMAND DEVELOPER BOOTSTRAP" -ForegroundColor Cyan
Write-Host " Workspace: $ProjectRoot" -ForegroundColor Gray
Write-Host "========================================================================" -ForegroundColor Cyan

# -------------------------------------------------------------------------
# Step 1: Detect Python 3.10+
# -------------------------------------------------------------------------
Write-Host "`n[1/5] Checking Python Runtime..." -ForegroundColor Yellow

function Find-HostPython {
    param([string]$ExplicitPath)

    if ($ExplicitPath -ne "") {
        if (-not (Test-Path $ExplicitPath)) {
            Write-Host " [FAIL] Specified -PythonExe '$ExplicitPath' not found." -ForegroundColor Red
            return $null
        }
        try {
            $ver = (& $ExplicitPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null)
            $exe = (& $ExplicitPath -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $ver) {
                return @{ Version = $ver.Trim(); Executable = $exe.Trim() }
            }
        } catch {}
        Write-Host " [FAIL] Specified -PythonExe '$ExplicitPath' is not a valid Python runtime." -ForegroundColor Red
        return $null
    }

    $Candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3.10") },
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )

    foreach ($cand in $Candidates) {
        $cmdName = $cand.Command
        if (Get-Command $cmdName -ErrorAction SilentlyContinue) {
            try {
                $argsList = $cand.Args
                $checkVer = (& $cmdName @argsList -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null)
                if ($LASTEXITCODE -eq 0 -and $checkVer) {
                    $parts = $checkVer.Trim().Split('.')
                    if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
                        $checkExe = (& $cmdName @argsList -c "import sys; print(sys.executable)" 2>$null)
                        return @{
                            Version = $checkVer.Trim()
                            Executable = $checkExe.Trim()
                        }
                    }
                }
            } catch {
                # Continue searching
            }
        }
    }
    return $null
}

$HostInfo = Find-HostPython -ExplicitPath $PythonExe

if ($null -eq $HostInfo) {
    Write-Host " [FAIL] Python >= 3.10 not detected in PATH or via Python Launcher (py)." -ForegroundColor Red
    Write-Host " Please install Python 3.10+ from https://www.python.org/downloads/ and retry." -ForegroundColor Yellow
    exit 1
}

$SelectedPython = $HostInfo.Executable
$SelectedVersion = $HostInfo.Version
Write-Host " [PASS] Found Python $SelectedVersion at: $SelectedPython" -ForegroundColor Green

# -------------------------------------------------------------------------
# Step 2: Virtual Environment (.venv)
# -------------------------------------------------------------------------
Write-Host "`n[2/5] Preparing Virtual Environment (.venv)..." -ForegroundColor Yellow

$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if ($RecreateVenv -and (Test-Path $VenvDir)) {
    Write-Host " Removing existing virtual environment (-RecreateVenv)..." -ForegroundColor DarkGray
    Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $VenvPython)) {
    Write-Host " Creating new virtual environment at $VenvDir..." -ForegroundColor Cyan
    & $SelectedPython -m venv "$VenvDir"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Write-Host " [FAIL] Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host " [PASS] Virtual environment created successfully." -ForegroundColor Green
} else {
    Write-Host " [PASS] Virtual environment exists at $VenvDir" -ForegroundColor Green
}

# -------------------------------------------------------------------------
# Step 3: Install & Upgrade Dependencies
# -------------------------------------------------------------------------
Write-Host "`n[3/5] Installing Dependencies from requirements.txt..." -ForegroundColor Yellow

Write-Host " Upgrading pip..." -ForegroundColor DarkGray
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Host " [WARN] pip upgrade exited with code $LASTEXITCODE" -ForegroundColor DarkYellow
}

$ReqFile = Join-Path $ProjectRoot "requirements.txt"
if (Test-Path $ReqFile) {
    Write-Host " Installing packages from requirements.txt..." -ForegroundColor Cyan
    & $VenvPython -m pip install -r "$ReqFile"
    if ($LASTEXITCODE -ne 0) {
        Write-Host " [FAIL] Package installation failed with exit code $LASTEXITCODE." -ForegroundColor Red
        exit 1
    }
    Write-Host " [PASS] Requirements installed." -ForegroundColor Green
} else {
    Write-Host " [WARN] requirements.txt not found at $ReqFile" -ForegroundColor DarkYellow
}

# -------------------------------------------------------------------------
# Step 4: Run Preflight Checks (Toolchain, Storage, Git Hooks)
# -------------------------------------------------------------------------
Write-Host "`n[4/5] Executing Preflight Checks..." -ForegroundColor Yellow

$PreflightScript = Join-Path $ProjectRoot "scripts\preflight_check.py"
if (-not $SkipHooks) {
    & $VenvPython "$PreflightScript" --install-hooks
} else {
    & $VenvPython "$PreflightScript"
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n [FAIL] Preflight validation failed (exit code $LASTEXITCODE)." -ForegroundColor Red
    Write-Host " Please resolve the preflight failures before continuing." -ForegroundColor Yellow
    exit 1
}

# -------------------------------------------------------------------------
# Step 5: Run Regression Test Suite
# -------------------------------------------------------------------------
if ($SkipTests) {
    Write-Host "`n[5/5] Skipping Test Suite (-SkipTests specified)." -ForegroundColor DarkYellow
} else {
    Write-Host "`n[5/5] Running Regression Test Suite..." -ForegroundColor Yellow
    $TestRunner = Join-Path $ProjectRoot "run_tests.py"
    & $VenvPython "$TestRunner"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n [FAIL] Regression test suite failed (exit code $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
    Write-Host " [PASS] All regression tests passed!" -ForegroundColor Green
}

# -------------------------------------------------------------------------
# Summary & Developer Quickstart
# -------------------------------------------------------------------------
Write-Host "`n========================================================================" -ForegroundColor Cyan
Write-Host " BOOTSTRAP COMPLETE -- READY TO DEVELOP!" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " Python Runtime: $VenvPython" -ForegroundColor White
Write-Host "`n Developer Quickstart:" -ForegroundColor Yellow
Write-Host "   Launch GUI Application:     .\run_app.bat" -ForegroundColor Cyan
Write-Host "                               (or: .\.venv\Scripts\python.exe main.py)" -ForegroundColor Gray
Write-Host "   Run Regression Tests:       .\.venv\Scripts\python.exe run_tests.py" -ForegroundColor Cyan
Write-Host "                               (or: .\.venv\Scripts\pytest.exe)" -ForegroundColor Gray
Write-Host "   Run Gage R&R Baseline:      .\.venv\Scripts\python.exe scripts\run_gage_rr_baseline.py" -ForegroundColor Cyan
Write-Host "   Run Preflight Checks:       .\.venv\Scripts\python.exe scripts\preflight_check.py" -ForegroundColor Cyan
Write-Host "========================================================================`n" -ForegroundColor Cyan

exit 0
