# `next` as yes/no questions + decision tree

## without change signal

AUC of each yes/no question against its label (positive vs all other cases):

| question | AUC |
|---|---|
| done:d0_goal | 0.957 |
| done:d1_result | 0.842 |
| replan:p0_unexpected | 0.667 |
| replan:p1_wont_fix | 0.604 |
| retry:y0_small | 0.764 |

| picked variants | CV acc | CV macro-F1 | in-sample acc | in-sample macro-F1 | thresholds (all data) |
|---|---|---|---|---|---|
| d0_goal / p0_unexpected / y0_small | 0.76 | 0.68 | 0.77 | 0.70 | {"done": 0.5, "replan": 0.85, "retry": 0.85, "ok": 0.36} |
| d0_goal / p1_wont_fix / y0_small | 0.73 | 0.68 | 0.76 | 0.69 | {"done": 0.5, "replan": 0.85, "retry": 0.85, "ok": 0.36} |
| d1_result / p0_unexpected / y0_small | 0.72 | 0.65 | 0.74 | 0.65 | {"done": 0.7, "replan": 0.7, "retry": 0.85, "ok": 0.2} |
| d1_result / p1_wont_fix / y0_small | 0.69 | 0.64 | 0.69 | 0.64 | {"done": 0.7, "replan": 0.85, "retry": 0.85, "ok": 0.36} |

Best by CV macro-F1: {'done': 'done:d0_goal', 'replan': 'replan:p0_unexpected', 'retry': 'retry:y0_small'} thresholds {'done': 0.5, 'replan': 0.85, 'retry': 0.85, 'ok': 0.36}

Confusion matrix (in-sample):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 22 | 4 | 2 | 1 | 0 |
| retry | 2 | 5 | 1 | 0 | 0 |
| replan | 0 | 5 | 23 | 0 | 0 |
| ask_user | 0 | 0 | 0 | 25 | 0 |
| done | 6 | 0 | 0 | 3 | 5 |

## with change signal

AUC of each yes/no question against its label (positive vs all other cases):

| question | AUC |
|---|---|
| done:d0_goal | 0.957 |
| done:d1_result | 0.842 |
| replan:p0_unexpected | 0.667 |
| replan:p1_wont_fix | 0.604 |
| retry:y0_small | 0.764 |

| picked variants | CV acc | CV macro-F1 | in-sample acc | in-sample macro-F1 | thresholds (all data) |
|---|---|---|---|---|---|
| d0_goal / p0_unexpected / y0_small | 0.76 | 0.68 | 0.77 | 0.70 | {"done": 0.5, "replan": 0.85, "retry": 0.85, "ok": 0.36} |
| d0_goal / p1_wont_fix / y0_small | 0.73 | 0.68 | 0.76 | 0.69 | {"done": 0.5, "replan": 0.85, "retry": 0.85, "ok": 0.36} |
| d1_result / p0_unexpected / y0_small | 0.72 | 0.65 | 0.74 | 0.65 | {"done": 0.7, "replan": 0.7, "retry": 0.85, "ok": 0.2} |
| d1_result / p1_wont_fix / y0_small | 0.69 | 0.64 | 0.69 | 0.64 | {"done": 0.7, "replan": 0.85, "retry": 0.85, "ok": 0.36} |

Best by CV macro-F1: {'done': 'done:d0_goal', 'replan': 'replan:p0_unexpected', 'retry': 'retry:y0_small'} thresholds {'done': 0.5, 'replan': 0.85, 'retry': 0.85, 'ok': 0.36}

Confusion matrix (in-sample):

| true \ pred | continue | retry | replan | ask_user | done |
|---|---|---|---|---|---|
| continue | 22 | 4 | 2 | 1 | 0 |
| retry | 2 | 5 | 1 | 0 | 0 |
| replan | 0 | 5 | 23 | 0 | 0 |
| ask_user | 0 | 0 | 0 | 25 | 0 |
| done | 6 | 0 | 0 | 3 | 5 |
