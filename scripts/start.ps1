$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
node -e "const [major,minor]=process.versions.node.split('.').map(Number);if(major<24||(major===24&&minor<4))process.exit(1);require('node:sqlite');"
if ($LASTEXITCODE -ne 0) { throw '需要 Node.js 24.4 或更新版本。' }
if (-not (Test-Path -LiteralPath 'node_modules/@modelcontextprotocol/client')) {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
}
node backend/platform/cli.js doctor
node backend/server.js
