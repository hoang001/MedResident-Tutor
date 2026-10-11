# Teaching Dataset Pilot Report — FINAL VERIFIED

## 1. Final split read directly from JSONL

### Train
- Samples: **35**
- Question IDs: `Q_0001, Q_0003, Q_0004, Q_0006, Q_0007, Q_0010, Q_0011`
- `sufficient_evidence=false`: **0**

### Validation
- Samples: **10**
- Question IDs: `Q_0005, Q_0008`
- `sufficient_evidence=false`: **1**

### Test
- Samples: **10**
- Question IDs: `Q_0017, Q_0018`
- `sufficient_evidence=false`: **1**

## 2. Required split assertion
- Train exact match: **PASS**
- Validation exact match: **PASS**
- Test exact match: **PASS**
- Validation contains at least one `sufficient_evidence=false`: **PASS**
- Question leakage across splits: **0**
- Locked Medical test `Q_0002`, `Q_0009`: **absent**

## 3. SHA-256
- `teaching_train.jsonl`: `9a779d9d914f92b50b7f4ee6092f7f10921433d447dca6dfc9c35ae2b2f2e301`
- `teaching_validation.jsonl`: `076be17afc7fc4190e5e8729cc063e42a155f4ffc5fe8b71efd81612ef111456`
- `teaching_test.jsonl`: `0aa8e9547028984590a54c49df277b4929f06b40a8e0e125646dda4c33e5a774`

## 4. Validator
Deterministic Teaching validator v1 was executed against these exact files.

- V1 Schema validity: **PASS**
- V2 Output completeness: **PASS**
- V3 Medical/Teaching consistency: **PASS**
- V4 Score immutability: **PASS**
- V5 Learner-context influence: **PASS**
- V6 No hallucinated medical fact: **PASS**
- V7 Split leakage: **PASS**
- **OVERALL: PASS**

Test set is only checked for schema/invariants/leakage and is not used for model selection.
