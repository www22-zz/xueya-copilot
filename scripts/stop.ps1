$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& '.venv/Scripts/python.exe' -X utf8 -m backend.xueya.cli stop
if ($LASTEXITCODE -ne 0) { throw '服务停止失败。' }
