# Closing-line (suffix) sensitivity

| suffix | risky AUC | stuck AUC | done AUC | last_ok AUC | decision accuracy | macro-F1 |
|---|---|---|---|---|---|---|
| none | 0.955 | 0.856 | 0.956 | 0.922 | 0.65 | 0.58 |
| unknown_line | 0.961 | 0.834 | 0.952 | 0.919 | 0.75 | 0.68 |
| task_question | 0.985 | 0.948 | 0.969 | 0.873 | 0.66 | 0.60 |
| end_marker | 0.942 | 0.832 | 0.973 | 0.893 | 0.70 | 0.64 |
| task_restated | 0.890 | 0.786 | 0.935 | 0.901 | 0.63 | 0.58 |