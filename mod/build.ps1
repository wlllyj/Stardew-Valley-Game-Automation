<#
.SYNOPSIS
    编译 AgentFarm.Bridge（Release）并安装到《星露谷》的 Mods\AgentFarm.Bridge\。

.DESCRIPTION
    流程：确定游戏目录 → dotnet build -c Release → 备份旧安装到 *.bak-<时间戳> → 复制
    manifest.json + AgentFarm.Bridge.dll → 校验哈希 → 打印结果。

    游戏目录解析顺序：
      1) 参数 -GamePath
      2) 环境变量 STARDEW_GAME_PATH
      3) csproj 里的默认值（本机实测路径）

    与旧项目 build.ps1 的差异：旧脚本手工列了 6 个 mod 目录，漏掉一个导致某个 mod
    从未被标准流程部署过。这里只有**一个**产物目录，且复制后立刻做字节级校验。

.PARAMETER GamePath
    游戏安装目录。留空则按上面的顺序解析。

.PARAMETER NoBackup
    不备份旧安装文件（默认会备份成 .bak-<yyyyMMdd-HHmmss>）。

.PARAMETER Rebuild
    先清理再整体重编译（等价于 dotnet build -t:Rebuild），用于从零验证。

.EXAMPLE
    .\build.ps1
    .\build.ps1 -GamePath 'D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley'
    .\build.ps1 -Rebuild -NoBackup

.NOTES
    本文件是 UTF-8 **带 BOM**（不是无 BOM）。
    原因：Windows PowerShell 5.1 读无 BOM 的 .ps1 时会按系统 ANSI 代码页解码，
    中文注释与提示会变成乱码并直接引发语法错误。这是 .ps1 特有的例外。
    若系统禁用了脚本执行，用：
        powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
#>
[CmdletBinding()]
param(
    [string]$GamePath,
    [switch]$NoBackup,
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Join-Path $scriptRoot 'AgentFarm.Bridge'
$csproj     = Join-Path $projectDir 'AgentFarm.Bridge.csproj'

function Write-Step([string]$text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok([string]$text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn2([string]$text){ Write-Host "    $text" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 前置检查
if (-not (Test-Path $csproj)) { throw "找不到工程文件：$csproj" }

# ---------------------------------------------------------------- 游戏目录
if (-not $GamePath) { $GamePath = $env:STARDEW_GAME_PATH }
if (-not $GamePath) { $GamePath = 'D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley' }

$GamePath = $GamePath.TrimEnd('\')
Write-Step "游戏目录：$GamePath"

$gameDll = Join-Path $GamePath 'Stardew Valley.dll'
if (-not (Test-Path $gameDll)) { throw "游戏程序集不存在：$gameDll（用 -GamePath 或 STARDEW_GAME_PATH 指定正确目录）" }
if (-not (Test-Path (Join-Path $GamePath 'StardewModdingAPI.dll'))) { throw "未找到 SMAPI：$GamePath\StardewModdingAPI.dll" }

# 游戏是否在运行（在跑的话装完不会热重载，必须重启才生效）
$running = Get-Process -Name 'Stardew Valley' -ErrorAction SilentlyContinue
if ($running) {
    Write-Warn2 "检测到《星露谷》正在运行（PID $($running.Id -join ',')）：文件会被覆盖，但 mod 只在下次启动时加载。"
}

# ---------------------------------------------------------------- 编译
$buildArgs = @('build', $csproj, '-c', 'Release', '--nologo')
if ($Rebuild) { $buildArgs += '-t:Rebuild' }
Write-Step ("dotnet " + ($buildArgs -join ' '))
$buildOutput = & dotnet @buildArgs 2>&1
$buildExit = $LASTEXITCODE
$buildOutput | ForEach-Object { "    $_" }
if ($buildExit -ne 0) { throw "编译失败（退出码 $buildExit）" }

$binDir = Join-Path $projectDir 'bin\Release'
$srcDll = Join-Path $binDir 'AgentFarm.Bridge.dll'
$srcManifest = Join-Path $binDir 'manifest.json'
if (-not (Test-Path $srcDll)) { throw "编译产物不存在：$srcDll" }
if (-not (Test-Path $srcManifest)) { $srcManifest = Join-Path $projectDir 'manifest.json' }
if (-not (Test-Path $srcManifest)) { throw "找不到 manifest.json（工程目录与输出目录都没有）" }

# ---------------------------------------------------------------- 安装
$targetDir = Join-Path $GamePath 'Mods\AgentFarm.Bridge'
Write-Step "安装到：$targetDir"

if (Test-Path $targetDir) {
    # 只备份本脚本自己的两个产物，避免把同目录里其他 mod 文件、日志一并打包
    $existing = Get-ChildItem $targetDir -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -in @('AgentFarm.Bridge.dll', 'manifest.json') }
    if ($existing -and -not $NoBackup) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        foreach ($f in $existing) {
            $bak = "$($f.FullName).bak-$stamp"
            Copy-Item $f.FullName $bak -Force
        }
        Write-Ok "已备份 $($existing.Count) 个旧文件为 *.bak-$stamp"
    }
} else {
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Write-Ok '已创建目标目录'
}

# 只复制这两个文件：其余依赖（游戏与 SMAPI 程序集）由 SMAPI 在运行期解析，
# 复制过去反而会引发版本冲突。
Copy-Item $srcDll      (Join-Path $targetDir 'AgentFarm.Bridge.dll') -Force
Copy-Item $srcManifest (Join-Path $targetDir 'manifest.json')        -Force

# ---------------------------------------------------------------- 校验
Write-Step '校验安装结果（字节级）'
$ok = $true
foreach ($pair in @(
    @{ Name = 'AgentFarm.Bridge.dll'; Src = $srcDll },
    @{ Name = 'manifest.json';        Src = $srcManifest }
)) {
    $dst = Join-Path $targetDir $pair.Name
    if (-not (Test-Path $dst)) { Write-Host "    [FAIL] 缺失 $($pair.Name)" -ForegroundColor Red; $ok = $false; continue }

    $h1 = (Get-FileHash $pair.Src -Algorithm SHA256).Hash
    $h2 = (Get-FileHash $dst      -Algorithm SHA256).Hash
    $size = (Get-Item $dst).Length

    if ($h1 -eq $h2) {
        Write-Ok ("{0}  {1,8} 字节  SHA256 {2}..." -f $pair.Name, $size, $h2.Substring(0, 12))
    } else {
        Write-Host "    [FAIL] $($pair.Name) 哈希不一致（复制损坏）" -ForegroundColor Red
        $ok = $false
    }
}

# ---------------------------------------------------------------- 汇总
$dllInfo = Get-Item (Join-Path $targetDir 'AgentFarm.Bridge.dll')
Write-Host ''
if ($ok) {
    Write-Host '安装成功。' -ForegroundColor Green
    Write-Host "  产物：$($dllInfo.FullName)  ($([math]::Round($dllInfo.Length/1KB,1)) KB, $($dllInfo.LastWriteTime))"
    Write-Host ''
    Write-Host '下一步（真机验证）：'
    Write-Host '  1) 启动 Stardew Valley（SMAPI）；'
    Write-Host '  2) 控制台应出现 “AgentFarm Bridge 已就绪”（版本号以日志为准，不要写死）；'
    Write-Host "  3) 读 %APPDATA%\StardewValley\AgentFarm\bridge.json 拿 port 与 token；"
    Write-Host '  4) curl http://127.0.0.1:<port>/v1/health'
    exit 0
} else {
    Write-Host '安装校验失败，请检查上面的 [FAIL] 行。' -ForegroundColor Red
    exit 1
}
