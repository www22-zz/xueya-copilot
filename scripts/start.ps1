$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.11 或更新版本。' }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建 Python 虚拟环境失败。' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败。' }
& '.venv/Scripts/python.exe' -m backend.xueya.cli doctor
if ($LASTEXITCODE -ne 0) { throw '环境检查失败。' }
& '.venv/Scripts/python.exe' -m backend.xueya.server
if ($LASTEXITCODE -ne 0) { throw '服务启动失败。' }
