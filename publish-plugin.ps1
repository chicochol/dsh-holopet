# publish-plugin.ps1
# 一键发布 dsh-pet-holocubic 到 npm。
# 用法：右键「使用 PowerShell 运行」，或在该目录打开 PowerShell 执行 .\publish-plugin.ps1
# 需要的 token：https://www.npmjs.com/settings/chicochol/tokens -> Generate New Token -> Classic -> Automation

$ErrorActionPreference = "Stop"
$node = "C:\Users\Chico\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
$pnpm = "C:\Users\Chico\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.cjs"

Write-Host ""
Write-Host "=== DSH-HoloPet 插件发布 ===" -ForegroundColor Cyan

if (-not (Test-Path $node)) {
  Write-Host "找不到 node：$node" -ForegroundColor Red
  exit 1
}

$token = Read-Host "粘贴 npm token（npm_ 开头，输入时不会显示）"
if ([string]::IsNullOrWhiteSpace($token)) {
  Write-Host "没有输入 token，退出。" -ForegroundColor Red
  exit 1
}
$token = $token.Trim()
if (-not $token.StartsWith("npm_")) {
  Write-Host "token 看起来不对（应以 npm_ 开头）。" -ForegroundColor Yellow
  $go = Read-Host "仍然继续？(y/N)"
  if ($go -ne "y") { exit 1 }
}

# 1. 写 .npmrc（覆盖旧的，避免残留错误配置）
$npmrc = Join-Path $env:USERPROFILE ".npmrc"
$content = "//registry.npmjs.org/:_authToken=$token"
[System.IO.File]::WriteAllText($npmrc, $content, [System.Text.Encoding]::ASCII)
Write-Host "已写入 $npmrc" -ForegroundColor Green

# 2. 验证登录
Write-Host "验证登录..." -ForegroundColor Cyan
& $node $pnpm whoami
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "登录验证失败。" -ForegroundColor Red
  Write-Host "请检查 token 类型是否为 Classic + Automation，或去 https://www.npmjs.com/settings/chicochol/tokens 重新生成。" -ForegroundColor Yellow
  exit 1
}

# 3. 发布
Write-Host ""
Write-Host "开始发布 dsh-pet-holocubic ..." -ForegroundColor Cyan
Push-Location (Join-Path $PSScriptRoot "plugin\dsh-pet-holocubic")
try {
  & $node $pnpm publish --access public --no-git-checks
  if ($LASTEXITCODE -ne 0) {
    Write-Host "发布失败，见上方输出。" -ForegroundColor Red
    exit 1
  }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "=== 发布完成 ===" -ForegroundColor Green
Write-Host "检查：https://www.npmjs.com/package/dsh-pet-holocubic" -ForegroundColor Cyan
Write-Host ""
Write-Host "安全提醒：发布成功后，去 https://www.npmjs.com/settings/chicochol/tokens 把这个 token 删掉。" -ForegroundColor Yellow
