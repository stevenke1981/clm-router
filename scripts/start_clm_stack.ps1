# Starts the local CLM stack: llama.cpp (Qwen3-8B Q8_0 embeddings, :8090) + clm-serve (:8700).
# Needs runtime\llama (llama.cpp CUDA build), runtime\models\Qwen3-8B-Q8_0.gguf and .venv with contrastive-lm (--no-deps).
$root = Split-Path $PSScriptRoot -Parent
Start-Process "$root\runtime\llama\llama-server.exe" -WindowStyle Hidden -WorkingDirectory "$root\runtime\llama" -ArgumentList @(
  '-m', "$root\runtime\models\Qwen3-8B-Q8_0.gguf", '--embeddings', '--pooling', 'last', '--alias', 'qwen3-8b',
  '-ngl', '99', '-c', '4096', '-b', '2048', '-ub', '2048', '-np', '2', '--port', '8090', '--host', '127.0.0.1')
do { Start-Sleep 3 } until ((try { (Invoke-WebRequest http://127.0.0.1:8090/health -UseBasicParsing).StatusCode -eq 200 } catch { $false }))
$env:CLM_DEVICE = 'cpu'
Start-Process "$root\.venv\Scripts\python.exe" -WindowStyle Hidden -ArgumentList '-m', 'clm.server', '--host', '127.0.0.1', '--port', '8700', '--no-ui'
'CLM stack starting: http://127.0.0.1:8700/health'
