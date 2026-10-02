# Jev-skill practices on the real CLM

104 cases.

## A/C. yes/no questions: plain statement vs true/false criteria with examples

| target | variant | pooled AUC | CV precision | CV recall |
|---|---|---|---|---|
| risky | plain | 0.985 | 0.88 | 0.92 |
| risky | jev | 0.947 | 0.68 | 0.84 |
| stuck | plain | 0.948 | 0.63 | 0.81 |
| stuck | jev | 0.800 | 0.72 | 0.62 |
| unexpected | plain | 0.943 | 0.23 | 0.38 |
| unexpected | jev | 0.741 | 0.38 | 0.38 |
| small_failure | plain | 0.785 | 0.25 | 0.38 |
| small_failure | jev | 0.746 | 0.29 | 0.25 |
| done | plain | 0.969 | 0.91 | 0.71 |
| done | jev | 0.931 | 0.90 | 0.64 |
| failed | plain | 0.731 | 0.48 | 0.56 |
| failed | jev | 0.639 | 0.40 | 0.75 |
| failed | score3 (Score primitive) | 0.779 | - | - |

## B. 5-way `next`: one-line options vs object options (what / not_for / examples)

| variant | accuracy | macro-F1 |
|---|---|---|
| plain | 0.26 | 0.18 |
| jev | 0.15 | 0.08 |

## D. prompt injection: text appended to the screen of the 25 risky cases (risky score; threshold 0.30)

| question wording | no injection | direct | screenreader | system | positives still flagged (worst case) |
|---|---|---|---|---|---|
| plain | 0.49 | 0.20 | 0.18 | 0.44 | 3/25 (was 23) |
| jev | 0.91 | 0.77 | 0.71 | 0.76 | 24/25 (was 25) |