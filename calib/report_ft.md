# Zero-shot vs fine-tuned heads (out-of-fold)

Heads fine-tuned on 52 rows (about 360 questions) of the other fold, scored on the 52 unseen rows; both folds pooled = 104 out-of-fold rows. Folds are grouped by task. Labels are the assistant's own.

| question | zero-shot AUC | fine-tuned AUC |
|---|---|---|
| risky | 0.993 | 0.999 |
| stuck | 0.927 | 0.924 |
| done | 0.957 | 0.954 |
| unexpected | 0.954 | 0.936 |
| small_failure | 0.764 | 0.701 |
| last_action_ok | 0.904 | 0.862 |

| 5-way `next5` (abstract options) | accuracy | macro-F1 |
|---|---|---|
| zero | 0.33 | 0.21 |
| tuned | 0.34 | 0.26 |