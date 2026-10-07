@echo off
setlocal
REM Portable Windows sm_89 / 8 GB profile. Keep this batch file ASCII-only.

set "REPO_DIR=%~dp0"
if not defined ASSET_DIR set "ASSET_DIR=%REPO_DIR%..\bonsai2-27b-ptq1-vision-8gb-assets"
for %%I in ("%ASSET_DIR%") do set "ASSET_DIR=%%~fI"
if not defined MODEL_PORT set "MODEL_PORT=18200"

set "MODEL=%ASSET_DIR%\models\bonsai2_27b_ptq1_native_mtp_vision.ninfer"
set "ENGINE_DIR=%ASSET_DIR%\engine"
set "ENGINE=%ENGINE_DIR%\ninfer-serve-89.exe"
if not exist "%MODEL%" (
  echo Missing model: "%MODEL%"
  exit /b 3
)
if not exist "%ENGINE%" (
  echo Missing engine: "%ENGINE%"
  exit /b 4
)

set "PATH=%ENGINE_DIR%;%PATH%"
set "LOCALAPPDATA=%REPO_DIR%.local\runtime"
if not exist "%LOCALAPPDATA%" mkdir "%LOCALAPPDATA%"
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
set "NINFER_TERNARY_PTQ1_FAST=1"
set "NINFER_TERNARY_KVMEM="
set "NINFER_TERNARY_KVMEM_SCORE="

echo Model: %MODEL%
echo API: http://127.0.0.1:%MODEL_PORT%/v1
if /i "%~1"=="--check" (
  echo PASS: model and engine found; no service started.
  exit /b 0
)
echo Press Ctrl+C to stop the server.

"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port %MODEL_PORT% --model-id qwen3.8-27b-long ^
  --max-context 262144 --kv-capacity 16000 --kv-dtype rk4v4 --host-kv-mib 8192 ^
  --prefill-chunk 128 --spec mtp --draft-tokens 4 --ngram-draft-tokens 0 ^
  --no-cuda-graph --recover-invariant-failures --kv-lease-growth ^
  --device-state-slots 0 --max-shared-prefixes 0 --max-concurrency 1 ^
  --vision --vision-residency overlay --vision-max-merged 8192 ^
  --default-max-tokens 32768 --default-reasoning-effort none ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo Engine exited with code %ERRORLEVEL%.
pause
