[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$RhinoOnly,
    [ValidateRange(1024, 65535)]
    [int]$McpPort = 10500
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkRoot = 'D:\codex\work\RhinoQwenPrecisionAgent'
$CacheRoot = Join-Path $ProjectRoot '.cache'
$VenvRoot = Join-Path $ProjectRoot '.venv'
$LogRoot = Join-Path $ProjectRoot 'logs'
$LauncherLog = Join-Path $LogRoot 'launcher.log'
$ServerOutLog = Join-Path $LogRoot 'server.out.log'
$ServerErrLog = Join-Path $LogRoot 'server.err.log'
$AgentUrl = 'http://127.0.0.1:8765'

New-Item -ItemType Directory -Force -Path $WorkRoot,$CacheRoot,$LogRoot | Out-Null
$env:TEMP = $WorkRoot
$env:TMP = $WorkRoot
$env:PIP_CACHE_DIR = Join-Path $CacheRoot 'pip'

function Write-LauncherStatus {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $Message
    Add-Content -LiteralPath $LauncherLog -Value $line -Encoding utf8
}

function Find-RhinoExecutable {
    $candidates = @(
        'D:\xiazai\System\Rhino.exe',
        (Join-Path $env:ProgramFiles 'Rhino 8\System\Rhino.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Rhino 8\System\Rhino.exe')
    )
    try {
        $appPath = (Get-ItemProperty 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Rhino.exe' -ErrorAction Stop).'(default)'
        if ($appPath) { $candidates = @($appPath) + $candidates }
    } catch {}
    return $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
}

function Get-PortListener {
    param([int]$Port)
    return Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Test-RhinoMcpReady {
    param([int]$Port)
    $listener = Get-PortListener -Port $Port
    if (-not $listener) { return $false }
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    # Rhino's HttpListener can be reported as PID 4 (HTTP.sys) on Windows.
    $rhinoRunning = Get-Process -Name Rhino -ErrorAction SilentlyContinue
    $isRhinoListener = $owner -and ($owner.ProcessName -eq 'Rhino' -or ($owner.Id -eq 4 -and $rhinoRunning))
    if (-not $isRhinoListener) {
        throw "端口 $Port 已被非 Rhino 进程占用（PID $($listener.OwningProcess)）。"
    }
    return $true
}

function Wait-RhinoMcp {
    param([int]$Port, [int]$TimeoutSeconds = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-RhinoMcpReady -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-AgentStatus {
    try {
        return Invoke-RestMethod -Uri "$AgentUrl/api/status" -TimeoutSec 3
    } catch {
        return $null
    }
}

function Test-AgentReady {
    $status = Get-AgentStatus
    return $status -and $status.qwen.ok -and $status.mcp.connected -and $status.rhino.connected
}

try {
    Write-LauncherStatus '正在准备 Rhino Qwen 智能建模环境...'
    $RhinoExe = Find-RhinoExecutable
    if (-not $RhinoExe) {
        throw '未找到 Rhino 8。请确认 Rhino 已安装，或把 Rhino.exe 路径加入 launcher.ps1 的候选列表。'
    }

    if (-not (Test-RhinoMcpReady -Port $McpPort)) {
        Write-LauncherStatus "正在打开 Rhino 8 并启动 MCP（端口 $McpPort）..."
        $runScript = "/runscript=`"_MCPStart $McpPort _Enter`""
        $rhinoProcess = Start-Process -FilePath $RhinoExe -ArgumentList '/nosplash',$runScript -PassThru
        Add-Content -LiteralPath $LauncherLog -Value "Rhino PID=$($rhinoProcess.Id), Path=$RhinoExe" -Encoding utf8
        if (-not (Wait-RhinoMcp -Port $McpPort)) {
            throw "Rhino 已打开，但 MCP 未在 $McpPort 端口就绪。请在 Rhino 指令栏确认 MCPStart 是否成功。"
        }
    }
    Write-LauncherStatus 'Rhino MCP 已就绪。'

    if ($RhinoOnly) {
        Write-LauncherStatus 'Rhino-only 检查完成。'
        exit 0
    }

    $EnvFile = Join-Path $ProjectRoot '.env'
    if (-not (Test-Path -LiteralPath $EnvFile) -and -not $env:QWEN_API_KEY -and -not $env:DASHSCOPE_API_KEY) {
        throw '缺少 QWEN_API_KEY：请在项目 .env 中配置百炼 API Key。'
    }

    $Python = Join-Path $VenvRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Write-LauncherStatus '首次运行：正在创建 D 盘 Python 环境并安装依赖...'
        $systemPython = (Get-Command python.exe -ErrorAction Stop).Source
        & $systemPython -m venv $VenvRoot
        & $Python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败。' }
    }

    if (-not (Test-AgentReady)) {
        $stale = Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -like "*$ProjectRoot*" -and
            $_.CommandLine -like '*app.main*'
        }
        foreach ($process in $stale) {
            Write-LauncherStatus "正在重启未就绪的本地服务（PID $($process.ProcessId)）..."
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }

        Write-LauncherStatus '正在启动 Qwen 建模服务...'
        $server = Start-Process -FilePath $Python -ArgumentList '-m','app.main' -WorkingDirectory $ProjectRoot -RedirectStandardOutput $ServerOutLog -RedirectStandardError $ServerErrLog -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath (Join-Path $LogRoot 'server.pid') -Value $server.Id

        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-Date) -lt $deadline) {
            if (Test-AgentReady) { break }
            if ($server.HasExited) {
                $tail = if (Test-Path $ServerErrLog) { (Get-Content $ServerErrLog -Tail 20) -join [Environment]::NewLine } else { '' }
                throw "Qwen 建模服务提前退出。$([Environment]::NewLine)$tail"
            }
            Start-Sleep -Milliseconds 750
        }
    }

    if (-not (Test-AgentReady)) {
        $tail = if (Test-Path $ServerErrLog) { (Get-Content $ServerErrLog -Tail 20) -join [Environment]::NewLine } else { '' }
        throw "服务启动超时：Qwen、MCP 或 Rhino 未全部在线。$([Environment]::NewLine)$tail"
    }

    Write-LauncherStatus '启动成功：Qwen、MCP、Rhino 已全部在线。'
    if (-not $NoBrowser) {
        Start-Process $AgentUrl
        Write-LauncherStatus "已打开对话页面：$AgentUrl"
    }
    exit 0
} catch {
    Write-LauncherStatus ("启动失败：" + $_.Exception.Message)
    Write-Host "详细日志：$LauncherLog" -ForegroundColor Yellow
    exit 1
}
