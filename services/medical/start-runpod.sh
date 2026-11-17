#!/usr/bin/env bash
# Run on the GPU Pod. No dependency installation, model download or second server.
set +x
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Explicit environment (including a command-line API key) wins over the optional file.
declare -A explicit_env=()
config_names=(MODEL_SERVICE_API_KEY MEDICAL_API_KEY MODEL_SERVICE_PYTHON MODEL_SERVICE_LOG_FILE MODEL_SERVICE_STOP_TIMEOUT_SECONDS)
for stage in MEDICAL TEACHING; do
  for field in BASE_MODEL_PATH ADAPTER_PATH ADAPTER_SHA256 BASE_CONFIG_SHA256 ADAPTER_CONFIG_SHA256 MAX_BODY_BYTES MAX_INPUT_TOKENS MAX_CONTEXT_TOKENS; do
    config_names+=("${stage}_${field}")
  done
done
for name in "${config_names[@]}"; do
  if [[ -v "$name" ]]; then explicit_env["$name"]="${!name}"; fi
done
env_file="${MODEL_SERVICE_ENV_FILE:-/workspace/secrets/medresident-serving.env}"
if [[ -f "$env_file" ]]; then
  set -a
  source "$env_file"
  set +a
elif [[ -n "${MODEL_SERVICE_ENV_FILE:-}" ]]; then
  echo "MODEL_SERVICE_ENV_FILE_NOT_FOUND" >&2
  exit 1
fi
for name in "${!explicit_env[@]}"; do export "$name=${explicit_env[$name]}"; done
unset explicit_env config_names stage field name
umask 077
log_file="${MODEL_SERVICE_LOG_FILE:-/workspace/outputs/model-service.log}"
mkdir -p "$(dirname "$log_file")"
exec > >(tee -a "$log_file") 2>&1
export PYTHONPATH="${repo_root}/model-training:${repo_root}/services/medical${PYTHONPATH:+:${PYTHONPATH}}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export WEB_CONCURRENCY=1
export MEDICAL_BASE_MODEL_PATH="${MEDICAL_BASE_MODEL_PATH:-/workspace/models/qwen3-4b-instruct-2507}"
export MEDICAL_ADAPTER_PATH="${MEDICAL_ADAPTER_PATH:-/workspace/adapters/medical-v1}"
export TEACHING_BASE_MODEL_PATH="${TEACHING_BASE_MODEL_PATH:-/workspace/models/qwen2.5-7b-instruct}"
export TEACHING_ADAPTER_PATH="${TEACHING_ADAPTER_PATH:-/workspace/adapters/teaching-v1}"
exec "${MODEL_SERVICE_PYTHON:-python}" -u -m medical_service.bootstrap "$@"
