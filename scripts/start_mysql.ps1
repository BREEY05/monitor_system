# 启动项目内的便携 MySQL 8.0（解压到 .local-mysql 后使用）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\start_mysql.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BaseDir = Join-Path $Root ".local-mysql\mysql-8.0.42-winx64"
$DataDir = Join-Path $Root ".local-mysql\data"
$Port = 3307
$Mysqld = Join-Path $BaseDir "bin\mysqld.exe"

if (-not (Test-Path $Mysqld)) {
    Write-Output "未找到便携 MySQL：$Mysqld"
    Write-Output "请先把 mysql-8.0.42-winx64.zip 解压到 .local-mysql\，或安装系统 MySQL 并修改 config.json 的 mysql_port。"
    exit 1
}

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Output "MySQL 已在 127.0.0.1:$Port 运行"
    exit 0
}

if (-not (Test-Path (Join-Path $DataDir "mysql"))) {
    Write-Output "初始化 MySQL 数据目录：$DataDir"
    New-Item -ItemType Directory -Force $DataDir | Out-Null
    & $Mysqld --initialize-insecure --basedir="$BaseDir" --datadir="$DataDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Output "MySQL 初始化失败，退出码 $LASTEXITCODE"
        exit 1
    }
}

Write-Output "启动 MySQL：127.0.0.1:$Port"
$mysqlArgs = @(
    "--basedir=$BaseDir",
    "--datadir=$DataDir",
    "--port=$Port",
    "--bind-address=127.0.0.1",
    "--character-set-server=utf8mb4",
    "--collation-server=utf8mb4_unicode_ci",
    "--console"
)
Start-Process -FilePath $Mysqld -ArgumentList $mysqlArgs -RedirectStandardOutput (Join-Path $Root ".local-mysql\mysql.out.log") -RedirectStandardError (Join-Path $Root ".local-mysql\mysql.err.log") -WindowStyle Hidden

for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    $ready = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($ready) {
        Write-Output "MySQL 已就绪：127.0.0.1:$Port（用户 root，空密码）"
        exit 0
    }
}
Write-Output "MySQL 启动超时，请查看 .local-mysql\mysql.err.log"
exit 1
