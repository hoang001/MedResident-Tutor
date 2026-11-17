#!/usr/bin/env bash
# GitHub -> local Pod checkout -> install HTTP service only. Never starts inference.
set +x
set -euo pipefail
repo_dir="${MEDRESIDENT_REPO_DIR:-/root/MedResident-Tutor}"
repo_url="${MEDRESIDENT_REPOSITORY_URL:-https://github.com/hoang001/MedResident-Tutor.git}"
branch="${MEDRESIDENT_BRANCH:-main}"
python_bin="${MODEL_SERVICE_PYTHON:-python}"
if [[ -d "${repo_dir}/.git" ]]; then
  origin="$(git -C "$repo_dir" remote get-url origin)"
  if [[ "${origin%.git}" != "${repo_url%.git}" ]]; then
    echo "BOOTSTRAP_ORIGIN_MISMATCH" >&2
    exit 1
  fi
  if [[ "$(git -C "$repo_dir" branch --show-current)" != "$branch" ]]; then
    echo "BOOTSTRAP_BRANCH_MISMATCH" >&2
    exit 1
  fi
  git -C "$repo_dir" diff --quiet
  git -C "$repo_dir" diff --cached --quiet
  git -C "$repo_dir" fetch origin "$branch"
  git -C "$repo_dir" merge --ff-only FETCH_HEAD
else
  mkdir -p "$(dirname "$repo_dir")"
  git clone --branch "$branch" --single-branch "$repo_url" "$repo_dir"
fi
"$python_bin" -m pip install -e "${repo_dir}/services/medical"
git -C "$repo_dir" rev-parse --short HEAD
echo "BOOTSTRAP_READY_NO_INFERENCE_STARTED"
