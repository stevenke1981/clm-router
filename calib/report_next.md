# next / last_action_ok calibration (104 cases)

Accuracy/macro-F1 are over all cases (raw = argmax of the choice question). 'e2e' applies the production overrides (risky > loop > continue-but-failed). 'CV' = per-class weights fitted on one half, scored on the other.

## without change signal

| variant | raw acc | raw macro-F1 | e2e acc | e2e macro-F1 | CV e2e acc | CV e2e macro-F1 |
|---|---|---|---|---|---|---|
| n0_current | 0.16 | 0.08 | 0.51 | 0.40 | 0.48 | 0.36 |
| n1_contrast | 0.28 | 0.17 | 0.57 | 0.46 | 0.56 | 0.39 |
| n2_done_explicit | 0.26 | 0.14 | 0.56 | 0.46 | 0.57 | 0.42 |
| n3_reordered | 0.17 | 0.14 | 0.52 | 0.44 | 0.51 | 0.37 |

Confusion matrix (e2e, n1_contrast):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 14 | 3 | 2 | 10 | 0 |
| retry | 6 | 2 | 0 | 0 | 0 |
| replan | 6 | 2 | 18 | 2 | 0 |
| ask_user | 1 | 0 | 0 | 24 | 0 |
| done | 9 | 0 | 0 | 4 | 1 |

### last_action_ok (label 1 = ok)

| variant | AUC | best-thr | precision(ok) | recall(ok) |
|---|---|---|---|---|
| k0_current | 0.922 | 0.32 | 0.87 | 0.97 |
| k1_result | 0.708 | 0.38 | 0.71 | 0.96 |
| k2_error | 0.726 | 0.42 | 0.72 | 1.00 |
| k3_choice | 0.851 | 0.01 | 0.79 | 1.00 |

## with change signal

| variant | raw acc | raw macro-F1 | e2e acc | e2e macro-F1 | CV e2e acc | CV e2e macro-F1 |
|---|---|---|---|---|---|---|
| n0_current | 0.16 | 0.08 | 0.51 | 0.40 | 0.48 | 0.36 |
| n1_contrast | 0.28 | 0.17 | 0.57 | 0.46 | 0.56 | 0.39 |
| n2_done_explicit | 0.26 | 0.14 | 0.56 | 0.46 | 0.57 | 0.42 |
| n3_reordered | 0.17 | 0.14 | 0.52 | 0.44 | 0.51 | 0.37 |

Confusion matrix (e2e, n1_contrast):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 14 | 3 | 2 | 10 | 0 |
| retry | 6 | 2 | 0 | 0 | 0 |
| replan | 6 | 2 | 18 | 2 | 0 |
| ask_user | 1 | 0 | 0 | 24 | 0 |
| done | 9 | 0 | 0 | 4 | 1 |

### last_action_ok (label 1 = ok)

| variant | AUC | best-thr | precision(ok) | recall(ok) |
|---|---|---|---|---|
| k0_current | 0.922 | 0.32 | 0.87 | 0.97 |
| k1_result | 0.708 | 0.38 | 0.71 | 0.96 |
| k2_error | 0.726 | 0.42 | 0.72 | 1.00 |
| k3_choice | 0.851 | 0.01 | 0.79 | 1.00 |
