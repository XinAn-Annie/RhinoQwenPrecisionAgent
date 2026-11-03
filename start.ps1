$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkRoot = Join-Path $ProjectRoot 'work'
$CacheRoot = Join-Path $ProjectRoot '.cache'
$VenvRoot = Join-Path $ProjectRoot '.venv'
$LogRoot = Join-Path $ProjectRoot 'logs'
$PredictorRoot = Join-Path $ProjectRoot 'curve_predictor'

New-Item -ItemType Directory -Force -Path $WorkRoot,$CacheRoot,$LogRoot | Out-Null
$env:TEMP = $WorkRoot
$env:TMP = $WorkRoot
$env:PIP_CACHE_DIR = Join-Path $CacheRoot 'pip'

if (-not (Test-Path (Join-Path $VenvRoot 'Scripts\python.exe'))) {
    python -m venv $VenvRoot
    & (Join-Path $VenvRoot 'Scripts\python.exe') -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
}

$Python = Join-Path $VenvRoot 'Scripts\python.exe'
& $Python -c 'import sklearn, scipy, joblib' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -r (Join-Path $PredictorRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'curve_predictor 依赖安装失败。' }
}
$EnvFile = Join-Path $ProjectRoot '.env'
if (-not (Test-Path $EnvFile) -and -not $env:QWEN_API_KEY -and -not $env:DASHSCOPE_API_KEY) {
    Write-Host '缺少 QWEN_API_KEY。请复制 .env.example 为 .env 并填写百炼 Key。' -ForegroundColor Red
    exit 2
}

$Old = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*RhinoQwenPrecisionAgent*app.main*' }
if ($Old) {
    Write-Host '服务似乎已在运行：http://127.0.0.1:8766'
    Start-Process 'http://127.0.0.1:8766'
    exit 0
}

try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8777/health' -TimeoutSec 2
} catch {
    $PredictorOut = Join-Path $LogRoot 'curve-predictor.out.log'
    $PredictorErr = Join-Path $LogRoot 'curve-predictor.err.log'
    $PredictorProcess = Start-Process -FilePath $Python -ArgumentList 'api.py' -WorkingDirectory $PredictorRoot -RedirectStandardOutput $PredictorOut -RedirectStandardError $PredictorErr -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath (Join-Path $LogRoot 'curve-predictor.pid') -Value $PredictorProcess.Id
    $PredictorReady = $false
    for ($i = 0; $i -lt 40; $i++) {
        try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8777/health' -TimeoutSec 2; $PredictorReady = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $PredictorReady) { Write-Host "curve_predictor 启动失败，请查看 $PredictorErr" -ForegroundColor Red; exit 4 }
}

$OutLog = Join-Path $LogRoot 'server.out.log'
$ErrLog = Join-Path $LogRoot 'server.err.log'
$Process = Start-Process -FilePath $Python -ArgumentList '-m','app.main' -WorkingDirectory $ProjectRoot -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru
Set-Content -LiteralPath (Join-Path $LogRoot 'server.pid') -Value $Process.Id

$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/status' -TimeoutSec 2
        $Ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $Ready) {
    Write-Host "启动失败，请查看 $ErrLog" -ForegroundColor Red
    exit 3
}
Start-Process 'http://127.0.0.1:8766'
Write-Host "Rhino Qwen Precision Agent 已启动（PID $($Process.Id)）。"
