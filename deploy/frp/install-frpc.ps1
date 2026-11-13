<#
.SYNOPSIS
  PULSE · 在 Windows 上安装 frpc，并注册为开机自启任务。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\frp\install-frpc.ps1 -ServerAddr 81.70.92.137 -Token 3f9c...

.NOTES
  需要管理员权限（注册 SYSTEM 启动任务）。
  默认安装到 C:\pulse\frp，连接 127.0.0.1:8000，映射到云端 18000。
#>
param(
    [Parameter(Mandatory = $true)][string]$ServerAddr,
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Version = "",
    [string]$ZipPath = "",
    [string]$InstallDir = "C:\pulse\frp",
    [int]$RemotePort = 18000,
    [int]$LocalPort = 8000,
    [string]$TaskName = "PULSE-frpc"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

function Info($m) { Write-Host "[frpc] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[frpc] $m" -ForegroundColor Red; exit 1 }

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Die "需要管理员权限：请运行 deploy\frp\install-windows.cmd <token>（会自动提权），或右键「以管理员身份运行」PowerShell"
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "v0.72.0"
    try {
        $latest = Invoke-RestMethod -Uri "https://api.github.com/repos/fatedier/frp/releases/latest" -TimeoutSec 10 -Headers @{ "User-Agent" = "pulse-installer" }
        if ($latest.tag_name) { $Version = $latest.tag_name }
    } catch {
        Info "获取最新版本失败，使用内置版本 $Version"
    }
}
$ver = $Version.TrimStart("v")
Info "frp 版本：$Version"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$tmp = Join-Path $env:TEMP ("frp-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$zipName = "frp_" + $ver + "_windows_amd64.zip"
$ghUrl = "https://github.com/fatedier/frp/releases/download/" + $Version + "/" + $zipName
$installedExe = Join-Path $InstallDir "frpc.exe"
$zip = Join-Path $tmp $zipName
$needDownload = $true
if (-not $PSBoundParameters.ContainsKey("Version") -and (Test-Path $installedExe)) {
    Info "已存在 frpc.exe，跳过下载（换版本请加 -Version vX.Y.Z）"
    $needDownload = $false
}

if ($needDownload) {
    if ($ZipPath -and (Test-Path $ZipPath)) {
        Info "使用本地压缩包 $ZipPath"
        Copy-Item $ZipPath $zip -Force
    } else {
        $candidates = @(
            $ghUrl,
            ("https://ghfast.top/" + $ghUrl),
            ("https://gh-proxy.com/" + $ghUrl),
            ("https://mirror.ghproxy.com/" + $ghUrl)
        )
        $ok = $false
        foreach ($u in $candidates) {
            Info ("下载 " + $u)
            try {
                $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
                if ($curl) {
                    & curl.exe -L --fail --connect-timeout 20 --max-time 600 -o $zip $u
                    if ($LASTEXITCODE -ne 0) { throw ("curl 退出码 " + $LASTEXITCODE) }
                } else {
                    Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 240
                }
                $fs = Get-Item $zip
                if ($fs.Length -lt 5MB) { throw ("文件过小（" + $fs.Length + " 字节），可能是错误页") }
                $ok = $true
                Info ("下载完成：" + [math]::Round($fs.Length / 1MB, 1) + " MB")
                break
            } catch {
                Info ("失败：" + $_.Exception.Message)
                if (Test-Path $zip) { Remove-Item $zip -Force -ErrorAction SilentlyContinue }
            }
        }
        if (-not $ok) {
            Die ("所有下载源都失败。可手动下载 " + $ghUrl + " 解压后把 frpc.exe 放到 " + $InstallDir + " 再运行 install-windows.cmd（已有 frpc.exe 会跳过下载）。")
        }
    }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
}

$exeSrc = Get-ChildItem -Path $tmp -Recurse -Filter "frpc.exe" | Select-Object -First 1
if ($exeSrc) {
    Copy-Item $exeSrc.FullName $installedExe -Force
} elseif (-not (Test-Path $installedExe)) {
    Die "没有可用的 frpc.exe：下载包解压失败，且安装目录里也没有"
}



$config = @"
# PULSE · frpc（本机引擎侧）—— 由 deploy/frp/install-frpc.ps1 生成
serverAddr = "$ServerAddr"
serverPort = 7000
auth.method = "token"
auth.token = "$Token"

transport.tls.enable = true
log.to = "console"
log.level = "info"

[[proxies]]
name = "pulse-api"
type = "tcp"
localIP = "127.0.0.1"
localPort = $LocalPort
remotePort = $RemotePort

healthCheck.type = "tcp"
healthCheck.timeoutSeconds = 3
healthCheck.maxFailed = 3
healthCheck.intervalSeconds = 10
"@
$configPath = Join-Path $InstallDir "frpc.toml"
Set-Content -Path $configPath -Value $config -Encoding utf8
Info "已写入 $configPath"

$action = New-ScheduledTaskAction -Execute (Join-Path $InstallDir "frpc.exe") -Argument ('-c "' + $configPath + '"')
$trigger = New-ScheduledTaskTrigger -AtStartup
$settingArgs = @{
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    StartWhenAvailable         = $true
    RestartCount               = 999
    RestartInterval            = (New-TimeSpan -Minutes 1)
    ExecutionTimeLimit         = [TimeSpan]::Zero
}
$settings = New-ScheduledTaskSettingsSet @settingArgs
$regArgs = @{
    TaskName  = $TaskName
    Action    = $action
    Trigger   = $trigger
    Settings  = $settings
    User      = "SYSTEM"
    RunLevel  = "Highest"
    Force     = $true
}
Register-ScheduledTask @regArgs | Out-Null
Info ("已注册开机自启任务：" + $TaskName)

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
$proc = Get-Process -Name "frpc" -ErrorAction SilentlyContinue
if ($proc) {
    Info ("frpc 已启动（PID " + $proc.Id + "）")
} else {
    Write-Host "[frpc] frpc 进程未出现，请检查：" -ForegroundColor Yellow
    Write-Host "  - 云服务器是否放行 TCP 7000"
    Write-Host "  - Token 是否与 /etc/frp/frps.toml 一致"
    Write-Host ("  - 手动前台排查：" + $InstallDir + "\frpc.exe -c " + $configPath)
}

Write-Host ""
Write-Host "下一步：" -ForegroundColor Green
Write-Host "  1) 确认本机后端已启动：python -m uvicorn api_server:app --host 127.0.0.1 --port 8000"
Write-Host "  2) 浏览器打开 https://pulse.ainavi.online/api/mobile/ping 应返回 JSON"
Write-Host "  3) 开机自启后端：deploy\frp\install-backend-task.ps1 -Python <python.exe 路径> -WorkDir <项目目录>"