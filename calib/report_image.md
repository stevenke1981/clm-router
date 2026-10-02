# Image review calibration

48 cases (16 briefs x pass/local_edit/regenerate), split by brief.

## state format A_current

- raw choice v0: accuracy 0.65, macro-F1 0.52
- raw choice v1: accuracy 0.46, macro-F1 0.36
- AUC meets: 1.000
- AUC g0: 0.623
- AUC g1: 0.969
- region AUC r0: 0.845 (16 faulty / 88 regions)
- region AUC r1: 0.730 (16 faulty / 88 regions)

| tree (meets / global / region wording) | CV accuracy | CV macro-F1 | target precision | target recall (local_edit cases) |
|---|---|---|---|---|
| meets / g0 / r0 | 0.48 | 0.45 | 0.50 | 0.44 |
| meets / g0 / r1 | 0.46 | 0.41 | 0.39 | 0.69 |
| meets / g1 / r0 | 0.85 | 0.86 | 0.50 | 0.44 |
| meets / g1 / r1 | 0.79 | 0.79 | 0.39 | 0.69 |

## state format B_suffix

- raw choice v0: accuracy 0.62, macro-F1 0.51
- raw choice v1: accuracy 0.33, macro-F1 0.17
- AUC meets: 1.000
- AUC g0: 0.486
- AUC g1: 0.637
- region AUC r0: 0.707 (16 faulty / 88 regions)
- region AUC r1: 0.553 (16 faulty / 88 regions)

| tree (meets / global / region wording) | CV accuracy | CV macro-F1 | target precision | target recall (local_edit cases) |
|---|---|---|---|---|
| meets / g0 / r0 | 0.46 | 0.38 | 0.45 | 0.31 |
| meets / g0 / r1 | 0.46 | 0.38 | 0.39 | 0.56 |
| meets / g1 / r0 | 0.52 | 0.49 | 0.45 | 0.31 |
| meets / g1 / r1 | 0.46 | 0.37 | 0.39 | 0.56 |

## state format C_clean

- raw choice v0: accuracy 0.67, macro-F1 0.54
- raw choice v1: accuracy 0.33, macro-F1 0.17
- AUC meets: 1.000
- AUC g0: 0.447
- AUC g1: 0.402
- region AUC r0: 0.717 (16 faulty / 88 regions)
- region AUC r1: 0.604 (16 faulty / 88 regions)

| tree (meets / global / region wording) | CV accuracy | CV macro-F1 | target precision | target recall (local_edit cases) |
|---|---|---|---|---|
| meets / g0 / r0 | 0.38 | 0.28 | 0.46 | 0.38 |
| meets / g0 / r1 | 0.38 | 0.28 | 0.45 | 0.62 |
| meets / g1 / r0 | 0.42 | 0.33 | 0.46 | 0.38 |
| meets / g1 / r1 | 0.42 | 0.33 | 0.45 | 0.62 |
