# Build a USB-friendly portable package:
#   dist-portable/ODMR_Console/
#     双击启动.bat / 停止.bat
#     runtime/python/   (embeddable CPython + site-packages)
#     app/              (backend + frontend/dist)
#
# Requires network ONCE on the packer PC (Python embed + get-pip + wheels, npm build).
# Target PCs need NO Python/Node install.

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutRoot = Join-Path $Root "dist-portable\ODMR_Console"
$Cache = Join-Path $Root ".portable-cache"
$Runtime = Join-Path $OutRoot "runtime\python"
$AppDir = Join-Path $OutRoot "app"

Write-Host ""
Write-Host "=== Build ODMR portable package ===" -ForegroundColor Cyan
Write-Host "Project: $Root"
Write-Host "Output : $OutRoot"
Write-Host ""

function Assert-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Assert-Command python
Assert-Command npm.cmd

New-Item -ItemType Directory -Force -Path $Cache | Out-Null
if (Test-Path $OutRoot) {
    Write-Host "Removing previous package..."
    Remove-Item -Recurse -Force $OutRoot
}
New-Item -ItemType Directory -Force -Path $Runtime, $AppDir | Out-Null

# --- 1) Frontend production build ---
Write-Host "[1/5] Building frontend (npm run build)..." -ForegroundColor Yellow
Push-Location (Join-Path $Root "frontend")
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "  npm install..."
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Pop-Location
}
$DistSrc = Join-Path $Root "frontend\dist"
if (-not (Test-Path (Join-Path $DistSrc "index.html"))) {
    throw "frontend/dist/index.html missing after build"
}

# --- 2) Embeddable CPython ---
$PyVer = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
$PyShort = (& python -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')").Trim()
# Prefer same major.minor as packer; fall back to 3.12 embed if needed.
$EmbedCandidates = @(
    "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip"
)
# Known stable embeds if exact micro not published yet
$Mm = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($Mm -eq "3.13") {
    $EmbedCandidates += @(
        "https://www.python.org/ftp/python/3.13.2/python-3.13.2-embed-amd64.zip",
        "https://www.python.org/ftp/python/3.13.1/python-3.13.1-embed-amd64.zip",
        "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
    )
    $PyShortFallback = "313"
} else {
    $EmbedCandidates += @(
        "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip",
        "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
    )
    $PyShortFallback = "312"
}

Write-Host "[2/5] Preparing embeddable Python..." -ForegroundColor Yellow
$EmbedZip = $null
$UsedUrl = $null
foreach ($url in $EmbedCandidates) {
    $name = Split-Path $url -Leaf
    $zipPath = Join-Path $Cache $name
    if (-not (Test-Path $zipPath)) {
        Write-Host "  Downloading $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
        } catch {
            Write-Host "  skip: $($_.Exception.Message)"
            if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
            continue
        }
    } else {
        Write-Host "  Using cached $name"
    }
    if ((Test-Path $zipPath) -and ((Get-Item $zipPath).Length -gt 1MB)) {
        $EmbedZip = $zipPath
        $UsedUrl = $url
        if ($name -match "python-(\d+)\.(\d+)\.") {
            $PyShort = "$($Matches[1])$($Matches[2])"
        }
        break
    }
}
if (-not $EmbedZip) {
    throw "Could not download embeddable Python. Check network or place a zip in $Cache"
}
Write-Host "  Extracting to runtime\python ..."
Expand-Archive -Path $EmbedZip -DestinationPath $Runtime -Force

# Enable site-packages in embeddable layout
$PthFiles = Get-ChildItem $Runtime -Filter "python*._pth"
if (-not $PthFiles) { throw "python*._pth not found in embed package" }
foreach ($pth in $PthFiles) {
    $lines = Get-Content $pth.FullName
    $new = @()
    $hasSite = $false
    $hasLib = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*#\s*import site') {
            $new += "import site"
            $hasSite = $true
        } elseif ($line -match '^\s*import site') {
            $new += "import site"
            $hasSite = $true
        } else {
            $new += $line
        }
        if ($line -match 'Lib\\site-packages') { $hasLib = $true }
    }
    if (-not $hasSite) { $new += "import site" }
    if (-not $hasLib) { $new += "Lib\site-packages" }
    Set-Content -Path $pth.FullName -Value $new -Encoding ascii
}

# get-pip
$GetPip = Join-Path $Cache "get-pip.py"
if (-not (Test-Path $GetPip)) {
    Write-Host "  Downloading get-pip.py"
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
}
$PyExe = Join-Path $Runtime "python.exe"
& $PyExe $GetPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

# --- 3) Install Python deps into embed ---
Write-Host "[3/5] Installing Python requirements into portable runtime..." -ForegroundColor Yellow
$Req = Join-Path $Root "requirements.txt"
& $PyExe -m pip install --upgrade pip --no-warn-script-location
& $PyExe -m pip install -r $Req --no-warn-script-location
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Full requirements failed; retry without zhinst-toolkit (can add later)..." -ForegroundColor DarkYellow
    $TmpReq = Join-Path $Cache "requirements-no-zhinst.txt"
    Get-Content $Req | Where-Object { $_ -notmatch 'zhinst' } | Set-Content $TmpReq
    & $PyExe -m pip install -r $TmpReq --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "pip install into portable python failed" }
    Write-Host "  NOTE: zhinst-toolkit not bundled; Zurich hardware drivers may need host install." -ForegroundColor DarkYellow
}

# --- 4) Copy application ---
Write-Host "[4/5] Copying application files..." -ForegroundColor Yellow
Copy-Item (Join-Path $Root "main.py") $AppDir
Copy-Item (Join-Path $Root "main_portable.py") $AppDir
Copy-Item (Join-Path $Root "requirements.txt") $AppDir
Copy-Item (Join-Path $Root "backend") (Join-Path $AppDir "backend") -Recurse -Force

# strip pycache
Get-ChildItem $AppDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$FeApp = Join-Path $AppDir "frontend"
New-Item -ItemType Directory -Force -Path $FeApp | Out-Null
Copy-Item $DistSrc (Join-Path $FeApp "dist") -Recurse -Force

# --- 5) Launchers ---
Write-Host "[5/5] Writing launchers..." -ForegroundColor Yellow

$StartBat = @'
@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python\python.exe"
set "APP=%ROOT%app"

if not exist "%PY%" (
  echo [ERROR] Embedded Python not found:
  echo   %PY%
  pause
  exit /b 1
)
if not exist "%APP%\main_portable.py" (
  echo [ERROR] App entry missing: %APP%\main_portable.py
  pause
  exit /b 1
)

rem Free port 8000 if something leftover is listening (best effort)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  taskkill /F /PID %%P >nul 2>&1
)

set "PYTHONPATH=%APP%"
set "PYTHONNOUSERSITE=1"
echo Starting ODMR portable console...
echo Browser will open http://127.0.0.1:8000/
echo Close this window to stop.
echo.
"%PY%" "%APP%\main_portable.py"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo Exited with code %EC%.
  pause
)
exit /b %EC%
'@
Set-Content -Path (Join-Path $OutRoot "双击启动.bat") -Value $StartBat -Encoding ascii

$StopBat = @'
@echo off
setlocal EnableExtensions
echo Stopping processes listening on port 8000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo kill PID %%P
  taskkill /F /PID %%P >nul 2>&1
)
echo Done.
pause
'@
Set-Content -Path (Join-Path $OutRoot "停止.bat") -Value $StopBat -Encoding ascii

# Also English names for non-Chinese systems
Set-Content -Path (Join-Path $OutRoot "START.bat") -Value $StartBat -Encoding ascii
Set-Content -Path (Join-Path $OutRoot "STOP.bat") -Value $StopBat -Encoding ascii

$Readme = @"
ODMR / NV Measurement Console — 便携版（免安装）
================================================

本文件夹可直接拷到 U 盘，在另一台 Windows 10/11 64 位电脑上使用。

【使用】
1. 整夹复制到对方电脑硬盘（推荐，比直接在 U 盘上跑更稳）
2. 双击「双击启动.bat」或 START.bat
3. 浏览器自动打开 http://127.0.0.1:8000/
4. 结束：关闭黑色窗口，或双击「停止.bat」

【无需安装】
- 不需要安装 Python
- 不需要安装 Node.js
- 不需要 npm

【注意】
- 仅支持 64 位 Windows
- 首次杀毒软件可能拦截 python.exe，请允许
- 连接 Zurich / Keysight 真机时，对方电脑仍需厂商驱动 / VISA（与是否便携无关）
- 不要只拷 bat，必须拷整个 ODMR_Console 文件夹

打包机 Python embed: $UsedUrl
生成时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@
Set-Content -Path (Join-Path $OutRoot "使用说明.txt") -Value $Readme -Encoding UTF8

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "Portable folder:"
Write-Host "  $OutRoot"
Write-Host ""
Write-Host "Copy the whole ODMR_Console folder to USB, then double-click 双击启动.bat"
Write-Host ""
