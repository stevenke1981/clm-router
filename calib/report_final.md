# Final calibration (per-question thresholds)

CV (2-fold): accuracy 0.80, macro-F1 0.69   |   in-sample: accuracy 0.85, macro-F1 0.79

| question | AUC | threshold (all data) | precision | recall |
|---|---|---|---|---|
| risky | 0.993 | 0.35 | 0.96 | 1.00 |
| stuck | 0.928 | 0.37 | 0.89 | 0.81 |
| done | 0.957 | 0.43 | 1.00 | 0.64 |
| unexpected | 0.954 | 0.67 | 0.55 | 0.75 |
| small_failure | 0.764 | 0.41 | 0.27 | 0.75 |
| failed | 0.904 | 0.68 | 0.93 | 0.72 |

Confusion matrix (in-sample):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 24 | 3 | 2 | 0 | 0 |
| retry | 1 | 5 | 2 | 0 | 0 |
| replan | 0 | 2 | 26 | 0 | 0 |
| ask_user | 0 | 0 | 0 | 25 | 0 |
| done | 4 | 1 | 0 | 1 | 8 |

Confusion matrix (CV):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 25 | 2 | 2 | 0 | 0 |
| retry | 2 | 1 | 5 | 0 | 0 |
| replan | 0 | 2 | 26 | 0 | 0 |
| ask_user | 1 | 0 | 0 | 24 | 0 |
| done | 5 | 1 | 0 | 1 | 7 |