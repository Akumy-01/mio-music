$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$pythonExe = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '请先创建 .venv 并安装依赖，见 README。' }
& $pythonExe -m PyInstaller --noconfirm --clean --windowed --onedir --name MioMusic --icon assets/mio.ico --collect-all pykakasi --collect-all jaconv --collect-all imageio_ffmpeg --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtPdf --add-data 'assets;assets' --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.md;.' main.py
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
Copy-Item -LiteralPath README.md -Destination dist/MioMusic/README.md -Force
Copy-Item -LiteralPath LICENSE -Destination dist/MioMusic/LICENSE -Force
Copy-Item -LiteralPath THIRD_PARTY_NOTICES.md -Destination dist/MioMusic/THIRD_PARTY_NOTICES.md -Force
& $pythonExe scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw '许可收集失败' }
Write-Output '生成完毕：dist/MioMusic/MioMusic.exe（分发时请打包整个 MioMusic 文件夹）'
