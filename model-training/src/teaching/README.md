# Teaching base-model benchmark

Run commands from the repository root. Source files remain in `data/training/`.
The selected model is fixed to `Qwen/Qwen2.5-7B-Instruct`; no training is performed.

```bash
python model-training/src/teaching/validate_dataset.py
python model-training/src/teaching/prepare_dataset.py
python model-training/src/teaching/test_pipeline.py
```

Validation and preparation process all three splits for schema, invariants,
leakage checks and format conversion only. They never evaluate a model. Source
Medical alignment uses Medical train/validation only; absence of both source
files is explicitly reported as skipped. Preparation preserves gold JSON values.

On Kaggle, enable a CUDA GPU and Internet access, then install dependencies in
a notebook cell (retain Kaggle's CUDA-enabled torch):

```python
%pip install "transformers>=4.57,<5" "accelerate>=1.10,<2" "bitsandbytes>=0.47,<1"
```

Restart the kernel if required by the installed packages. From the repo root:

```bash
python model-training/src/common/check_environment.py
python model-training/src/teaching/evaluate_baseline.py
```

Baseline reads only the fixed `teaching_validation_sft.jsonl` path and enforces
10 unique samples from Q_0005/Q_0008. Only system/user messages reach generation.
Greedy decoding uses `do_sample=False`, `temperature=0`, seed 42 and 1,600 maximum
new tokens, with NF4 4-bit weights on GPU 0. Exact reproducibility across hardware
and dependency versions is not guaranteed. No CPU fallback or adapter loading.

Report: `model-training/outputs/teaching-baseline/qwen2.5-7b-validation.json`.
It includes raw predictions, input, gold, per-sample metrics, errors, token counts,
generation configuration and a validation-file hash for manual review. Latency
measures synchronized GPU generation, excluding model loading/tokenization.
JSON parsing rejects markdown, extra prose, duplicate keys and NaN/Infinity.

Metrics reuse the locked validator's lexical similarity and anchor thresholds.
Strengths use one-to-one matching; corrections/missing focus require exact
Medical point coverage including multiplicity. Context usage is counted only
for nonempty context. Scores are forbidden recursively in output keys.
Learning priorities require anchored focus, valid enum values and unique focus.
Evidence guard requires cautious wording when sufficient_evidence is false.

These metrics are deterministic proxies, not a factuality guarantee. The V6
anchor guard covers strengths, correction feedback, missing feedback and follow-up
questions. Review free-form feedback, priority reasons, nuanced medical claims,
context-sensitive priority order, negation and truncated outputs manually.
Do not tune against the Teaching test split.
