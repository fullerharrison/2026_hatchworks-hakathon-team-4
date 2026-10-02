param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$repoRoot = Split-Path (Split-Path "$taskRoot" -Parent) -Parent
$basePython = Join-Path "$repoRoot" 'app/.venv/Scripts/python.exe'
$python = Join-Path "$taskRoot" '.venv/Scripts/python.exe'
$cache = Join-Path "$taskRoot" '.cache/uv'
$temporary = Join-Path "$taskRoot" '.cache/tmp'
$requirements = Join-Path "$taskRoot" 'requirements.in'
$lock = Join-Path "$taskRoot" 'requirements.lock.txt'

if ($DryRun) {
    [ordered]@{
        task_root = $taskRoot
        environment = Split-Path "$python" -Parent
        cache = $cache
        temporary = $temporary
        requirements = $requirements
        lock = $lock
        runtime = 'moonshine-voice==0.1.5'
        microphone = $false
        hosted_audio = $false
    } | ConvertTo-Json
    return
}

$previous = @{
    UV_CACHE_DIR = $env:UV_CACHE_DIR
    TEMP = $env:TEMP
    TMP = $env:TMP
    PYTHONDONTWRITEBYTECODE = $env:PYTHONDONTWRITEBYTECODE
}

try {
    $env:UV_CACHE_DIR = $cache
    $env:TEMP = $temporary
    $env:TMP = $temporary
    $env:PYTHONDONTWRITEBYTECODE = '1'
    if (-not (Test-Path -LiteralPath "$python")) {
        & uv venv --python "$basePython" --no-python-downloads "$taskRoot/.venv"
        if ($LASTEXITCODE -ne 0) { throw 'Task-local environment creation failed' }
    }
    & uv pip compile "$requirements" --python "$python" --generate-hashes `
        --no-header --no-annotate --output-file "$lock"
    if ($LASTEXITCODE -ne 0) { throw 'Research dependency resolution failed' }
    & uv pip sync --python "$python" --require-hashes "$lock"
    if ($LASTEXITCODE -ne 0) { throw 'Research dependency installation failed' }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable("$name", $previous[$name], 'Process')
    }
}