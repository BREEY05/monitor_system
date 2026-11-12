<#
.SYNOPSIS
  PULSE · 把本机后端（uvicorn api_server:app）注册成开机自启任务。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\frp\install-backend-task.ps1 -Python "D:\anaconda\envs\agent\python.exe" -WorkDir "D:\anaconda\envs\agent\monitor_system"

.NOTES
  只监听 127.0.0.1:8000，公网入口只经过 frp 隧道 + 云端 nginx，本机 8000 不直接暴露。
#>
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [int]$Port = 8000,
    [string]$TaskName = "PULSE-backend"
)

$ErrorActionPreference = "Stop"

function Info($m) { Write-Host "[backend] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[backend] $m" -ForegroundColor Red; exit 1 }

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Die "请用管理员 PowerShell 运行"
}
if (-not (Test-Path $Python)) { Die ("找不到 Python：" + $Python) }
$apiFile = Join-Path $WorkDir "api_server.py"
if (-not (Test-Path $apiFile)) { Die ($WorkDir + " 下没有 api_server.py") }

$argument = "-m uvicorn api_server:app --host 127.0.0.1 --port " + $Port + " --proxy-headers --forwarded-allow-ips=127.0.0.1"
$action = New-ScheduledTaskAction -Execute $Python -Argument $argument -WorkingDirectory $WorkDir
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
Info ("已注册：" + $TaskName)

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5
try {
    $ping = Invoke-RestMethod -Uri ("http://127.0.0.1:" + $Port + "/api/mobile/ping") -TimeoutSec 10
    Info ("后端可用：" + $ping.server.name + " " + $ping.server.version)
} catch {
    Write-Host ("[backend] 启动检查失败：" + $_.Exception.Message) -ForegroundColor Yellow
    Write-Host ("  手动排查：cd " + $WorkDir + "; & '" + $Python + "' -m uvicorn api_server:app --host 127.0.0.1 --port " + $Port)
}
