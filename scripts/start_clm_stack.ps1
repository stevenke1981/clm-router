# Start existing local assets; reuse healthy services and bound startup waits.
[CmdletBinding()]
param([ValidateRange(1, 3600)][int]$TimeoutSeconds = 180)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

function Test-Healthy([string]$Url, [switch]$Clm) {
    try {
        $response = Invoke-RestMethod $Url -TimeoutSec 3
        if ($Clm) { return ($response.ok -eq $true -and $response.embedder -eq $true) }
        return $response.status -eq 'ok'
    } catch { return $false }
}

function Wait-Healthy([string]$Url, $Process, [switch]$Clm) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-Healthy $Url -Clm:$Clm) { return }
        if ($Process.HasExited) { throw "Service exited ($($Process.ExitCode)). See runtime startup logs." }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for $Url after $TimeoutSeconds seconds. See runtime startup logs."
}

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing required asset: $Path" }
}

$llamaHealth = 'http://127.0.0.1:8090/health'
$clmHealth = 'http://127.0.0.1:8700/health'
if (-not (Test-Healthy $llamaHealth)) {
    $llama = "$root\runtime\llama\llama-server.exe"
    $model = "$root\runtime\models\Qwen3-8B-Q8_0.gguf"
    Require-File $llama
    Require-File $model
    $process = Start-Process $llama -WindowStyle Hidden -WorkingDirectory "$root\runtime\llama" -PassThru -ArgumentList @(
        '-m', "`"$model`"", '--embeddings', '--pooling', 'last', '--alias', 'qwen3-8b',
        '-ngl', '99', '-c', '4096', '-b', '2048', '-ub', '2048', '-np', '2', '--port', '8090', '--host', '127.0.0.1') `
        -RedirectStandardOutput "$root\runtime\llama-start.stdout.log" -RedirectStandardError "$root\runtime\llama-start.stderr.log"
    Wait-Healthy $llamaHealth $process
}
if (-not (Test-Healthy $clmHealth -Clm)) {
    $python = "$root\.venv\Scripts\python.exe"
    Require-File $python
    $previousDevice = $env:CLM_DEVICE
    try {
        $env:CLM_DEVICE = 'cpu'
        $process = Start-Process $python -WindowStyle Hidden -WorkingDirectory $root -PassThru `
            -ArgumentList '-m', 'clm.server', '--host', '127.0.0.1', '--port', '8700', '--no-ui' `
            -RedirectStandardOutput "$root\runtime\clm-start.stdout.log" -RedirectStandardError "$root\runtime\clm-start.stderr.log"
    } finally { $env:CLM_DEVICE = $previousDevice }
    Wait-Healthy $clmHealth $process -Clm
}
"CLM stack ready: $clmHealth"
