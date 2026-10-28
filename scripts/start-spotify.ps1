$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) { throw '请先安装并启动 Docker Desktop（Linux 容器模式），再运行此脚本。' }
$mioSecret = Read-Host '请输入你自己 Spotify 会话的 SP_DC（不会显示，也不会写入项目文件）' -AsSecureString
$mioSecretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($mioSecret)
try {
    $env:SP_DC = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($mioSecretPointer)
    if ([string]::IsNullOrWhiteSpace($env:SP_DC)) { throw 'SP_DC 不能为空' }
    docker compose -f integrations/spotify-lyrics-api/compose.yaml up -d --build
    if ($LASTEXITCODE -ne 0) { throw '服务启动失败，请检查 Docker 输出。' }
    Write-Output '服务地址：http://127.0.0.1:8765/ 。在 Mio 的 Spotify 链接窗口中使用此地址。'
} finally {
    Remove-Item Env:SP_DC -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($mioSecretPointer)
    $mioSecret.Dispose()
}
