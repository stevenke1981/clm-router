# Attack-surface reduction

104 screens as UIA-style dumps; mean state size: full 251 chars, ui 62 chars, ui+text 155 chars

## clean accuracy (pooled AUC per question; risky also 2-fold CV precision/recall at its own best threshold)

| mode | risky | stuck | done | unexpected | small_failure | failed | risky CV P | risky CV R |
|---|---|---|---|---|---|---|---|---|
| full | 0.992 | 0.945 | 0.961 | 0.935 | 0.799 | 0.908 | 0.88 | 0.92 |
| ui | 0.953 | 0.936 | 0.802 | 0.562 | 0.691 | 0.710 | 0.72 | 0.84 |
| ui+text | 0.993 | 0.928 | 0.957 | 0.954 | 0.764 | 0.904 | 0.96 | 0.96 |

## injection: risky screens still flagged (risky >= 0.3); clean = no injected text

| mode | clean | text (worst of 3) | link (worst of 3) | button (worst of 3) |
|---|---|---|---|---|
| full | 25/25 | 6/25 | 9/25 | 10/25 |
| ui | 20/25 | 20/25 | 10/25 | 11/25 |
| ui+text | 25/25 | 25/25 | 21/25 | 20/25 |