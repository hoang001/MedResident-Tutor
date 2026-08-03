#!/usr/bin/env bash
set -u

ROOT="/kaggle/working/MedResident-Tutor"
LOG_DIR="$ROOT/model-training/outputs/benchmark-logs"
mkdir -p "$LOG_DIR"
cd "$ROOT"

echo "Bắt đầu hai benchmark trên hai GPU riêng..."

CUDA_VISIBLE_DEVICES=0 python model-training/src/test_medical_candidate.py > "$LOG_DIR/medical.log" 2>&1 &
MED_PID=$!

CUDA_VISIBLE_DEVICES=1 python model-training/src/test_teaching_candidate.py > "$LOG_DIR/teaching.log" 2>&1 &
TEACH_PID=$!

wait "$MED_PID"
MED_STATUS=$?
wait "$TEACH_PID"
TEACH_STATUS=$?

echo "Medical exit code: $MED_STATUS"
echo "Teaching exit code: $TEACH_STATUS"

echo
echo "===== MEDICAL LOG ====="
cat "$LOG_DIR/medical.log"

echo
echo "===== TEACHING LOG ====="
cat "$LOG_DIR/teaching.log"

if [ "$MED_STATUS" -ne 0 ] || [ "$TEACH_STATUS" -ne 0 ]; then
  exit 1
fi
