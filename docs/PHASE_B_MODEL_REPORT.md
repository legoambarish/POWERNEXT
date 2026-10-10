# Phase B v3 ML model evaluation

This report evaluates the frozen train-only artifacts from the Phase B v3 run. Selection was frozen from validation evidence before the held-out test partition was read. No estimator was retrained or tuned for this report.

The registry loader checked each model's card hash, route metadata, runtime, and current predictive-source fingerprint. The strict v2 request oracle was then run for all 32 candidates. Its scientific fields match the earlier validation-oracle results; timing fields are reported separately because they depend on the evaluation process.

## Provenance

- Dataset: `93f3d521d171559d2b6bd9f30d657fb98d56a1922e53d6ca627805b83df4ebc4`; rows `e7da922ad701cedbee587178484ad5f476ee0977fe4e780cffce62b2211f4611`; `92662` canonical eligible rows.
- Training result: `15defa0844585080b5b3a55fcf03c7328d938adf004df7cdf153beabf657d024`; run manifest `f579130f9ebe77e96f7edfd688cebdf236b277091e4bc5f73464751b79b96854`.
- Oracle-v2 manifest: `687b421b9aab3ff5b676beef69bb2fdac4ab18e03036cf7b46b2c551345d2343`; requests `68fb2e93a5e255c12b865fd960b10d20dda221424c4cfaf6d17f3af93ff06c34`.
- Oracle scientific equivalence: `True` across `32` candidate-route evaluations.
- Raw hook schema audit: the first unnormalized comparison differed at the top-level key set because the training wrapper records selection annotations; those documented annotations and measured timing fields are retained in the JSON audit and excluded only from the scientific-field equality check.
- Runtime: Python `3.12.14`, NumPy `2.4.6`, scikit-learn `1.9.0`.

## Route selections and frozen test summary

Test metrics below are post-freeze evaluations. `Test norm` is the mean tolerance-normalized error across gain, front, and tail. Throughput is measured model prediction throughput in this sequential evaluator and is not a search-policy benchmark.

| Route | Selected candidate | Model | Validation norm | Test norm | Test OOD | Artifact KiB | Load ms | Test rows/s | Oracle retention |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| cpri_0p5uf:LI:GSHUNT_v0 | residual/extra_trees | `model_50ce98bc7b25be230187` | 0.055803 | 0.044176 | 18 | 3.186e+04 | 623.2 | 21638 | 1 |
| cpri_0p5uf:LI:OSHUNT_v0 | residual/extra_trees | `model_daa2cbadea54a3c3ef40` | 0.053386 | 0.047802 | 11 | 3.168e+04 | 508.9 | 24056 | 1 |
| cpri_0p5uf:SI:GSHUNT_v0 | residual/hist_gradient_boosting | `model_ecc53338e57d65f8e1c2` | 0.006882 | 0.006379 | 17 | 1054 | 129.3 | 22377 | 1 |
| cpri_0p5uf:SI:OSHUNT_v0 | residual/hist_gradient_boosting | `model_993e9005005e76a1836b` | 0.0067644 | 0.0056378 | 18 | 1047 | 122 | 22233 | 1 |
| research_3uf:LI:GSHUNT_v0 | residual/extra_trees | `model_550d023662e4e2021bd3` | 0.05251 | 0.049912 | 17 | 3.408e+04 | 544.1 | 23852 | 1 |
| research_3uf:LI:OSHUNT_v0 | residual/extra_trees | `model_a1588a432ca30b4eebdd` | 0.067626 | 0.062388 | 9 | 3.319e+04 | 541.7 | 24573 | unavailable |
| research_3uf:SI:GSHUNT_v0 | residual/extra_trees | `model_298ce67feab06f9bc47c` | 0.0032767 | 0.0033464 | 17 | 3.203e+04 | 607.4 | 20484 | 1 |
| research_3uf:SI:OSHUNT_v0 | residual/hist_gradient_boosting | `model_2846ce76b0e0873a5c17` | 0.0031321 | 0.0041954 | 1 | 1321 | 175.3 | 25937 | unavailable |

## All four candidates by route

### `cpri_0p5uf:LI:GSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_231bac656df9e7c60737` | 2.1318 | 2.6121 | 0.01093/0.038207 | 1.807/7.354 | 22.518/99.33 | 18 | 3.288e+04 | 543.2 | 23756 |
| physics_guided | hist_gradient_boosting |  | `model_4bc926438683efe1a39e` | 1.9584 | 2.5254 | 0.0042578/0.014232 | 2.1738/7.5551 | 11.943/58.376 | 18 | 1128 | 286.5 | 21897 |
| residual | extra_trees | yes | `model_50ce98bc7b25be230187` | 0.055803 | 0.044176 | 0.0011254/0.0049793 | 0.015855/0.056258 | 0.45182/1.4382 | 18 | 3.186e+04 | 623.2 | 21638 |
| residual | hist_gradient_boosting |  | `model_c084ce1ac55612018ac8` | 0.1646 | 0.1704 | 0.0014765/0.0063123 | 0.13513/0.65228 | 0.74489/2.3901 | 18 | 1137 | 177.6 | 22808 |

### `cpri_0p5uf:LI:OSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_62e6a6a143d9d1d7689e` | 2.7172 | 3.6474 | 0.010448/0.036456 | 2.2064/6.7394 | 40.695/178.94 | 11 | 3.266e+04 | 584.2 | 25755 |
| physics_guided | hist_gradient_boosting |  | `model_2aff581320f05d8f74ce` | 1.8021 | 3.1309 | 0.0038111/0.013017 | 2.6198/7.9672 | 17.717/49.217 | 11 | 1118 | 254.2 | 24342 |
| residual | extra_trees | yes | `model_daa2cbadea54a3c3ef40` | 0.053386 | 0.047802 | 0.0011226/0.0055409 | 0.019876/0.070784 | 0.36473/1.2164 | 11 | 3.168e+04 | 508.9 | 24056 |
| residual | hist_gradient_boosting |  | `model_284b6e92916fcafbc804` | 0.13894 | 0.19606 | 0.0013224/0.005865 | 0.16194/0.77069 | 0.72936/2.4398 | 11 | 1127 | 122.3 | 23453 |

### `cpri_0p5uf:SI:GSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_ed4ea63ae181a4fb09e8` | 0.1643 | 0.18047 | 0.0077832/0.035397 | 4.0362/10.939 | 35.342/121.52 | 17 | 3.095e+04 | 517.3 | 21641 |
| physics_guided | hist_gradient_boosting |  | `model_e2f7b078ad621e77a25a` | 0.095244 | 0.11326 | 0.0025651/0.0073026 | 2.7272/6.5154 | 11.849/31.539 | 17 | 1069 | 1782 | 23271 |
| residual | extra_trees |  | `model_cc0e02a02766a3acb5fa` | 0.0070831 | 0.0065612 | 0.00047795/0.0013826 | 0.024858/0.087955 | 0.24518/0.37319 | 17 | 2.889e+04 | 520.6 | 25511 |
| residual | hist_gradient_boosting | yes | `model_ecc53338e57d65f8e1c2` | 0.006882 | 0.006379 | 0.00040725/0.00127 | 0.062008/0.19152 | 0.32057/0.43479 | 17 | 1054 | 129.3 | 22377 |

### `cpri_0p5uf:SI:OSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_1b9be26f94c9caa8a61c` | 0.2507 | 0.26438 | 0.008358/0.032374 | 4.4361/13.824 | 50.467/172.98 | 18 | 3.091e+04 | 535.3 | 21730 |
| physics_guided | hist_gradient_boosting |  | `model_3dac4c2fe704fe5cf3c6` | 0.11896 | 0.11116 | 0.0017318/0.0045387 | 2.921/4.9792 | 14.317/33.138 | 18 | 1072 | 263.2 | 23518 |
| residual | extra_trees |  | `model_de5a3e9ea563e8287b1a` | 0.007973 | 0.0050576 | 0.00028189/0.00079569 | 0.029539/0.13811 | 0.20971/0.37684 | 18 | 2.886e+04 | 532.6 | 23678 |
| residual | hist_gradient_boosting | yes | `model_993e9005005e76a1836b` | 0.0067644 | 0.0056378 | 0.00027627/0.00083366 | 0.067957/0.30348 | 0.28876/0.62619 | 18 | 1047 | 122 | 22233 |

### `research_3uf:LI:GSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_adf7dbfd42611f77086d` | 2.0837 | 3.5234 | 0.0054655/0.01737 | 2.8134/8.0564 | 25.191/124 | 17 | 3.51e+04 | 606.1 | 24305 |
| physics_guided | hist_gradient_boosting |  | `model_f2c003c9c41eb9986b38` | 2.7874 | 4.7298 | 0.0039488/0.012692 | 4.2266/10.969 | 22.044/102.67 | 17 | 1167 | 174.9 | 20749 |
| residual | extra_trees | yes | `model_550d023662e4e2021bd3` | 0.05251 | 0.049912 | 0.00083461/0.0037716 | 0.014476/0.051182 | 0.81032/1.6998 | 17 | 3.408e+04 | 544.1 | 23852 |
| residual | hist_gradient_boosting |  | `model_5fb562597ba15ecdd407` | 0.17263 | 0.19337 | 0.0013907/0.0066134 | 0.14702/0.68145 | 1.225/4.3028 | 17 | 1180 | 124 | 22330 |

### `research_3uf:LI:OSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_ee091f8eacdb318c9d40` | 3.4703 | 3.2388 | 0.0080689/0.027509 | 0.62387/1.7633 | 73.656/401.2 | 9 | 3.371e+04 | 569 | 26537 |
| physics_guided | hist_gradient_boosting |  | `model_847d3e07dfc569d09bf2` | 1.1315 | 1.1538 | 0.0027145/0.0081213 | 0.67421/1.2235 | 12.985/74.238 | 9 | 1131 | 2189 | 22539 |
| residual | extra_trees | yes | `model_a1588a432ca30b4eebdd` | 0.067626 | 0.062388 | 0.00074729/0.0034436 | 0.030711/0.11545 | 0.61513/1.506 | 9 | 3.319e+04 | 541.7 | 24573 |
| residual | hist_gradient_boosting |  | `model_2182ae8a29ced5996118` | 0.14891 | 0.15287 | 0.00094352/0.0042324 | 0.09704/0.30633 | 1.3527/4.6537 | 9 | 1145 | 119.3 | 24978 |

### `research_3uf:SI:GSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_3f870717fb0bcc311299` | 0.11802 | 0.12046 | 0.004886/0.015921 | 5.5389/12.76 | 37.747/132.58 | 17 | 3.436e+04 | 547.8 | 23135 |
| physics_guided | hist_gradient_boosting |  | `model_63756def05e367e4a037` | 0.091778 | 0.09394 | 0.0019581/0.0070952 | 5.4536/8.6567 | 21.131/51.935 | 17 | 1138 | 243.8 | 25524 |
| residual | extra_trees | yes | `model_298ce67feab06f9bc47c` | 0.0032767 | 0.0033464 | 0.00027115/0.00042178 | 0.02368/0.10873 | 0.3159/0.45961 | 17 | 3.203e+04 | 607.4 | 20484 |
| residual | hist_gradient_boosting |  | `model_02facba36db624707019` | 0.0035795 | 0.0036417 | 0.00026443/0.00061193 | 0.062744/0.23053 | 0.39737/0.78555 | 17 | 1112 | 156 | 21467 |

### `research_3uf:SI:OSHUNT_v0`

| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |
|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| physics_guided | extra_trees |  | `model_ed761ae686c0d7f64057` | 0.19266 | 0.1959 | 0.0056126/0.021858 | 2.6607/8.5807 | 73.878/268.15 | 1 | 4.314e+04 | 733.6 | 25619 |
| physics_guided | hist_gradient_boosting |  | `model_632b009ad246e02393ee` | 0.086201 | 0.085292 | 0.0014307/0.0037831 | 1.4788/3.7791 | 14.189/34.229 | 1 | 1333 | 290.4 | 24420 |
| residual | extra_trees |  | `model_9135aed5472dbf0f549c` | 0.0033993 | 0.0042406 | 0.00024222/0.00042365 | 0.03221/0.14732 | 0.33839/0.72906 | 1 | 4.049e+04 | 707.9 | 23691 |
| residual | hist_gradient_boosting | yes | `model_2846ce76b0e0873a5c17` | 0.0031321 | 0.0041954 | 0.00021198/0.00051826 | 0.083657/0.30308 | 0.39043/0.85253 | 1 | 1321 | 175.3 | 25937 |

## Selected-model test errors

These are the selected candidate's held-out errors. MAE, RMSE, P95, and maximum are in the target's native units; normalized values divide by the training tolerance scale.

| Route | Target | n | MAE | RMSE | P95 | Max | Norm MAE | Norm P95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cpri_0p5uf:LI:GSHUNT_v0 | gain | 2236 | 0.0011254 | 0.0031773 | 0.0049793 | 0.051783 | 0.043302 | 0.19825 |
| cpri_0p5uf:LI:GSHUNT_v0 | front_us | 2236 | 0.015855 | 0.028618 | 0.056258 | 0.3348 | 0.044042 | 0.15627 |
| cpri_0p5uf:LI:GSHUNT_v0 | tail_us | 2236 | 0.45182 | 2.5026 | 1.4382 | 45.872 | 0.045182 | 0.14382 |
| cpri_0p5uf:LI:OSHUNT_v0 | gain | 2369 | 0.0011226 | 0.0029136 | 0.0055409 | 0.028479 | 0.05172 | 0.25215 |
| cpri_0p5uf:LI:OSHUNT_v0 | front_us | 2369 | 0.019876 | 0.041729 | 0.070784 | 0.57757 | 0.055211 | 0.19662 |
| cpri_0p5uf:LI:OSHUNT_v0 | tail_us | 2369 | 0.36473 | 2.1446 | 1.2164 | 67.975 | 0.036473 | 0.12164 |
| cpri_0p5uf:SI:GSHUNT_v0 | gain | 2304 | 0.00040725 | 0.0024592 | 0.00127 | 0.060495 | 0.017683 | 0.059967 |
| cpri_0p5uf:SI:GSHUNT_v0 | front_us | 2304 | 0.062008 | 0.15536 | 0.19152 | 2.5656 | 0.0012402 | 0.0038304 |
| cpri_0p5uf:SI:GSHUNT_v0 | tail_us | 2304 | 0.32057 | 3.5646 | 0.43479 | 134.02 | 0.00021371 | 0.00028986 |
| cpri_0p5uf:SI:OSHUNT_v0 | gain | 2337 | 0.00027627 | 0.0017617 | 0.00083366 | 0.034872 | 0.015362 | 0.058868 |
| cpri_0p5uf:SI:OSHUNT_v0 | front_us | 2337 | 0.067957 | 0.18577 | 0.30348 | 2.7898 | 0.0013591 | 0.0060697 |
| cpri_0p5uf:SI:OSHUNT_v0 | tail_us | 2337 | 0.28876 | 1.7211 | 0.62619 | 40.941 | 0.00019251 | 0.00041746 |
| research_3uf:LI:GSHUNT_v0 | gain | 2383 | 0.00083461 | 0.0022702 | 0.0037716 | 0.028183 | 0.028492 | 0.1273 |
| research_3uf:LI:GSHUNT_v0 | front_us | 2383 | 0.014476 | 0.024218 | 0.051182 | 0.22495 | 0.040212 | 0.14217 |
| research_3uf:LI:GSHUNT_v0 | tail_us | 2383 | 0.81032 | 5.9741 | 1.6998 | 115.48 | 0.081032 | 0.16998 |
| research_3uf:LI:OSHUNT_v0 | gain | 2557 | 0.00074729 | 0.001922 | 0.0034436 | 0.031555 | 0.040342 | 0.17683 |
| research_3uf:LI:OSHUNT_v0 | front_us | 2557 | 0.030711 | 0.066712 | 0.11545 | 1.1739 | 0.085309 | 0.3207 |
| research_3uf:LI:OSHUNT_v0 | tail_us | 2557 | 0.61513 | 3.9117 | 1.506 | 85.926 | 0.061513 | 0.1506 |
| research_3uf:SI:GSHUNT_v0 | gain | 2550 | 0.00027115 | 0.0024151 | 0.00042178 | 0.069938 | 0.0093551 | 0.015985 |
| research_3uf:SI:GSHUNT_v0 | front_us | 2550 | 0.02368 | 0.1095 | 0.10873 | 1.5861 | 0.00047359 | 0.0021746 |
| research_3uf:SI:GSHUNT_v0 | tail_us | 2550 | 0.3159 | 2.8309 | 0.45961 | 58.5 | 0.0002106 | 0.00030641 |
| research_3uf:SI:OSHUNT_v0 | gain | 3413 | 0.00021198 | 0.0013981 | 0.00051826 | 0.024602 | 0.010653 | 0.028514 |
| research_3uf:SI:OSHUNT_v0 | front_us | 3413 | 0.083657 | 0.19393 | 0.30308 | 2.7352 | 0.0016731 | 0.0060617 |
| research_3uf:SI:OSHUNT_v0 | tail_us | 3413 | 0.39043 | 2.6526 | 0.85253 | 72.053 | 0.00026028 | 0.00056836 |

## Actual near-boundary errors

The near-boundary metric selects rows whose true value is within 25% of a tolerance half-width from either boundary, then reports absolute prediction-minus-truth error. This is separate from the legacy `boundary_errors` fields, which measure predicted distance outside the conformity band and are retained only as a diagnostic in the machine-readable evidence.

| Route | Partition | Target | Near-boundary n | MAE | P95 | Max | Norm P95 |
|---|---|---|---:|---:|---:|---:|---:|
| cpri_0p5uf:LI:GSHUNT_v0 | validation | front_us | 39 | 0.028904 | 0.091016 | 0.11658 | 0.25282 |
| cpri_0p5uf:LI:GSHUNT_v0 | validation | tail_us | 101 | 0.1371 | 0.75797 | 1.1288 | 0.075797 |
| cpri_0p5uf:LI:GSHUNT_v0 | validation | crest_V | 10 | 714.63 | 2921.9 | 4653.9 | 0.09461 |
| cpri_0p5uf:LI:GSHUNT_v0 | test | front_us | 39 | 0.031078 | 0.060854 | 0.3348 | 0.16904 |
| cpri_0p5uf:LI:GSHUNT_v0 | test | tail_us | 159 | 0.11424 | 0.35481 | 1.621 | 0.035481 |
| cpri_0p5uf:LI:GSHUNT_v0 | test | crest_V | 17 | 1176.4 | 4372.6 | 8074.8 | 0.25465 |
| cpri_0p5uf:LI:OSHUNT_v0 | validation | front_us | 69 | 0.03124 | 0.065158 | 0.43616 | 0.181 |
| cpri_0p5uf:LI:OSHUNT_v0 | validation | tail_us | 87 | 0.17535 | 0.58364 | 1.921 | 0.058364 |
| cpri_0p5uf:LI:OSHUNT_v0 | validation | crest_V | 6 | 850.48 | 2591.5 | 3173.5 | 0.10622 |
| cpri_0p5uf:LI:OSHUNT_v0 | test | front_us | 60 | 0.039013 | 0.12191 | 0.57757 | 0.33864 |
| cpri_0p5uf:LI:OSHUNT_v0 | test | tail_us | 166 | 0.17502 | 0.73106 | 1.6606 | 0.073106 |
| cpri_0p5uf:LI:OSHUNT_v0 | test | crest_V | 21 | 1315.6 | 5615.2 | 6027.7 | 0.16077 |
| cpri_0p5uf:SI:GSHUNT_v0 | validation | front_us | 69 | 0.022036 | 0.053329 | 0.059679 | 0.0010666 |
| cpri_0p5uf:SI:GSHUNT_v0 | validation | tail_us | 213 | 0.26029 | 1.1695 | 9.3823 | 0.00077964 |
| cpri_0p5uf:SI:GSHUNT_v0 | validation | crest_V | 9 | 21.139 | 64.427 | 76.921 | 0.0024 |
| cpri_0p5uf:SI:GSHUNT_v0 | test | front_us | 140 | 0.021838 | 0.049831 | 0.077208 | 0.00099661 |
| cpri_0p5uf:SI:GSHUNT_v0 | test | tail_us | 425 | 0.45523 | 0.423 | 134.02 | 0.000282 |
| cpri_0p5uf:SI:GSHUNT_v0 | test | crest_V | 20 | 53.844 | 212.52 | 687.52 | 0.010715 |
| cpri_0p5uf:SI:OSHUNT_v0 | validation | front_us | 103 | 0.040998 | 0.060461 | 0.9168 | 0.0012092 |
| cpri_0p5uf:SI:OSHUNT_v0 | validation | tail_us | 247 | 0.18551 | 0.43104 | 10.439 | 0.00028736 |
| cpri_0p5uf:SI:OSHUNT_v0 | validation | crest_V | 8 | 245.61 | 1055.6 | 1275 | 0.37416 |
| cpri_0p5uf:SI:OSHUNT_v0 | test | front_us | 176 | 0.029578 | 0.073527 | 0.93818 | 0.0014705 |
| cpri_0p5uf:SI:OSHUNT_v0 | test | tail_us | 411 | 0.25552 | 0.67698 | 13.978 | 0.00045132 |
| cpri_0p5uf:SI:OSHUNT_v0 | test | crest_V | 21 | 209.7 | 1018.7 | 1849.4 | 0.084893 |
| research_3uf:LI:GSHUNT_v0 | validation | front_us | 46 | 0.01846 | 0.052759 | 0.066249 | 0.14655 |
| research_3uf:LI:GSHUNT_v0 | validation | tail_us | 129 | 0.15252 | 0.64581 | 1.322 | 0.064581 |
| research_3uf:LI:GSHUNT_v0 | validation | crest_V | 14 | 218.76 | 1095.7 | 1585.6 | 0.031239 |
| research_3uf:LI:GSHUNT_v0 | test | front_us | 34 | 0.021364 | 0.054295 | 0.08146 | 0.15082 |
| research_3uf:LI:GSHUNT_v0 | test | tail_us | 191 | 0.11626 | 0.46303 | 1.4041 | 0.046303 |
| research_3uf:LI:GSHUNT_v0 | test | crest_V | 18 | 874.91 | 3639 | 4864 | 0.11091 |
| research_3uf:LI:OSHUNT_v0 | validation | front_us | 115 | 0.033227 | 0.084452 | 0.34474 | 0.23459 |
| research_3uf:LI:OSHUNT_v0 | validation | tail_us | 26 | 0.48082 | 1.983 | 3.2868 | 0.1983 |
| research_3uf:LI:OSHUNT_v0 | validation | crest_V | 12 | 1330.2 | 5105.4 | 8616.8 | 0.13649 |
| research_3uf:LI:OSHUNT_v0 | test | front_us | 132 | 0.027991 | 0.097442 | 0.21879 | 0.27067 |
| research_3uf:LI:OSHUNT_v0 | test | tail_us | 34 | 0.3555 | 1.0387 | 1.9875 | 0.10387 |
| research_3uf:LI:OSHUNT_v0 | test | crest_V | 14 | 1596 | 8269.7 | 16070 | 0.2072 |
| research_3uf:SI:GSHUNT_v0 | validation | front_us | 78 | 0.00085997 | 0.0024326 | 0.0083314 | 4.8652e-05 |
| research_3uf:SI:GSHUNT_v0 | validation | tail_us | 302 | 0.25398 | 0.51984 | 12.342 | 0.00034656 |
| research_3uf:SI:GSHUNT_v0 | validation | crest_V | 5 | 2036.1 | 8144.2 | 10180 | 0.45246 |
| research_3uf:SI:GSHUNT_v0 | test | front_us | 160 | 0.0014499 | 0.0066436 | 0.025037 | 0.00013287 |
| research_3uf:SI:GSHUNT_v0 | test | tail_us | 564 | 0.24842 | 0.2477 | 44.091 | 0.00016513 |
| research_3uf:SI:GSHUNT_v0 | test | crest_V | 18 | 405.99 | 2671.5 | 4288 | 0.087382 |
| research_3uf:SI:OSHUNT_v0 | validation | front_us | 140 | 0.044332 | 0.10139 | 0.18997 | 0.0020278 |
| research_3uf:SI:OSHUNT_v0 | validation | tail_us | 206 | 0.44337 | 0.98577 | 23.483 | 0.00065718 |
| research_3uf:SI:OSHUNT_v0 | validation | crest_V | 10 | 132.24 | 443.18 | 602.81 | 0.030491 |
| research_3uf:SI:OSHUNT_v0 | test | front_us | 297 | 0.057488 | 0.10207 | 1.626 | 0.0020413 |
| research_3uf:SI:OSHUNT_v0 | test | tail_us | 429 | 0.27479 | 0.68717 | 25.694 | 0.00045811 |
| research_3uf:SI:OSHUNT_v0 | test | crest_V | 18 | 96.836 | 415.53 | 1452.1 | 0.013195 |

## Learning curves

All candidates used the same nested grouped train subsets per route. Scores below are validation-only normalized error at 25%, 50%, and 100% of the canonical train partition. The 100% curve fit is the staged learning-curve fit; the frozen serving artifact is a separate full-capacity train fit whose row order can differ, so the 100% curve score is not asserted to be the serving artifact's score. The selected artifact's validation metrics above are authoritative for that frozen model.

| Route | Candidate | 25% | 50% | 100% |
|---|---|---:|---:|---:|
| cpri_0p5uf:LI:GSHUNT_v0 | physics_guided/extra_trees | 4.0772 | 2.8254 | 2.1923 |
| cpri_0p5uf:LI:GSHUNT_v0 | physics_guided/hist_gradient_boosting | 2.9813 | 1.9954 | 1.9584 |
| cpri_0p5uf:LI:GSHUNT_v0 | residual/extra_trees | 0.085831 | 0.077453 | 0.055456 |
| cpri_0p5uf:LI:GSHUNT_v0 | residual/hist_gradient_boosting | 0.16287 | 0.16414 | 0.1646 |
| cpri_0p5uf:LI:OSHUNT_v0 | physics_guided/extra_trees | 5.4613 | 3.4845 | 2.6845 |
| cpri_0p5uf:LI:OSHUNT_v0 | physics_guided/hist_gradient_boosting | 2.3614 | 2.0172 | 1.8021 |
| cpri_0p5uf:LI:OSHUNT_v0 | residual/extra_trees | 0.086646 | 0.072465 | 0.052821 |
| cpri_0p5uf:LI:OSHUNT_v0 | residual/hist_gradient_boosting | 0.18063 | 0.17805 | 0.13894 |
| cpri_0p5uf:SI:GSHUNT_v0 | physics_guided/extra_trees | 0.33284 | 0.21001 | 0.16305 |
| cpri_0p5uf:SI:GSHUNT_v0 | physics_guided/hist_gradient_boosting | 0.15662 | 0.12083 | 0.095244 |
| cpri_0p5uf:SI:GSHUNT_v0 | residual/extra_trees | 0.010238 | 0.0097643 | 0.0069134 |
| cpri_0p5uf:SI:GSHUNT_v0 | residual/hist_gradient_boosting | 0.014025 | 0.0098699 | 0.006882 |
| cpri_0p5uf:SI:OSHUNT_v0 | physics_guided/extra_trees | 0.44338 | 0.31081 | 0.24914 |
| cpri_0p5uf:SI:OSHUNT_v0 | physics_guided/hist_gradient_boosting | 0.17789 | 0.12524 | 0.11896 |
| cpri_0p5uf:SI:OSHUNT_v0 | residual/extra_trees | 0.010298 | 0.0098946 | 0.0078696 |
| cpri_0p5uf:SI:OSHUNT_v0 | residual/hist_gradient_boosting | 0.012967 | 0.0088054 | 0.0067644 |
| research_3uf:LI:GSHUNT_v0 | physics_guided/extra_trees | 6.9775 | 3.1384 | 2.0669 |
| research_3uf:LI:GSHUNT_v0 | physics_guided/hist_gradient_boosting | 5.1036 | 3.0614 | 2.7874 |
| research_3uf:LI:GSHUNT_v0 | residual/extra_trees | 0.091527 | 0.075685 | 0.052576 |
| research_3uf:LI:GSHUNT_v0 | residual/hist_gradient_boosting | 0.17612 | 0.1631 | 0.17263 |
| research_3uf:LI:OSHUNT_v0 | physics_guided/extra_trees | 7.1263 | 4.5277 | 3.4673 |
| research_3uf:LI:OSHUNT_v0 | physics_guided/hist_gradient_boosting | 2.1065 | 1.2559 | 1.1315 |
| research_3uf:LI:OSHUNT_v0 | residual/extra_trees | 0.1026 | 0.095366 | 0.067554 |
| research_3uf:LI:OSHUNT_v0 | residual/hist_gradient_boosting | 0.16154 | 0.14968 | 0.14891 |
| research_3uf:SI:GSHUNT_v0 | physics_guided/extra_trees | 0.236 | 0.15017 | 0.12089 |
| research_3uf:SI:GSHUNT_v0 | physics_guided/hist_gradient_boosting | 0.17734 | 0.093846 | 0.091778 |
| research_3uf:SI:GSHUNT_v0 | residual/extra_trees | 0.0069993 | 0.0046538 | 0.0032935 |
| research_3uf:SI:GSHUNT_v0 | residual/hist_gradient_boosting | 0.0092649 | 0.005082 | 0.0035795 |
| research_3uf:SI:OSHUNT_v0 | physics_guided/extra_trees | 0.35201 | 0.23058 | 0.19283 |
| research_3uf:SI:OSHUNT_v0 | physics_guided/hist_gradient_boosting | 0.10589 | 0.089656 | 0.086201 |
| research_3uf:SI:OSHUNT_v0 | residual/extra_trees | 0.0052334 | 0.0044998 | 0.0033824 |
| research_3uf:SI:OSHUNT_v0 | residual/hist_gradient_boosting | 0.0059076 | 0.0040005 | 0.0031321 |

## Oracle-v2 selection recheck

The strict v2 oracle was run against all four frozen candidates on each route. Scientific fields exclude only measured prediction-time fields. Selection keys were recomputed with the v2 hook, including the explicit fallback when a route has no true-feasible request.

| Route | All candidate oracle fields match | Selection unchanged | Feasible requests | Missed feasible at 5 | Retention | Selection basis |
|---|:---:|:---:|---:|---:|---:|---|
| cpri_0p5uf:LI:GSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| cpri_0p5uf:LI:OSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| cpri_0p5uf:SI:GSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| cpri_0p5uf:SI:OSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| research_3uf:LI:GSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| research_3uf:LI:OSHUNT_v0 | yes | yes | 0 | 0 | unavailable | REGRESSION_VALIDATION_FALLBACK |
| research_3uf:SI:GSHUNT_v0 | yes | yes | 2 | 0 | 1 | INDEPENDENT_REQUEST_ORACLE |
| research_3uf:SI:OSHUNT_v0 | yes | yes | 0 | 0 | unavailable | REGRESSION_VALIDATION_FALLBACK |

## Interpretation and limits

- The selected artifacts remain the original train-only models; this evaluation performs no refit, calibration, or tuning.
- The two research 3 µF O-shunt routes have zero true-feasible candidates in their frozen validation oracle requests. Their feasible retention and regret are undefined, so selection explicitly falls back to validation regression evidence; this is not evidence of perfect retention.
- OOD counts are reported for the selected model and every candidate as a disclosure and prioritization signal. They are not a hard serving gate and do not provide an accuracy guarantee.
- Artifact load and prediction throughput are sequential measurements from this evaluator. Search-policy timing and any broader speed claim belong to the separate controlled benchmark.
- The test partition is one finite synthetic held-out partition from this run; it does not establish laboratory accuracy or universal optimizer performance.

## Two/three-module supported-scope held-out accuracy

This is a post-hoc stratification of the frozen canonical held-out test partition. It reuses the selected model's original `results.json` predictions; it performs no fitting, model loading, new inference, timing run, or waveform regeneration. The trained artifacts remain mixed 1–4-module models. The two active strata are `max(front_network_module_count, tail_network_module_count) <= 2` and exactly `== 3`; rows with a larger maximum are historical four-module data and are excluded from both columns.

The exact module fields come from the immutable paired `design.jsonl`: `front_network_module_count` and `tail_network_module_count`. Each matched test row's counts were checked against the leaf counts of `configuration.front_network` and `configuration.tail_network` in `rows.jsonl`. The rows themselves carry the equivalent-resistance network trees and do not carry those two scalar module-count fields.

The v3 feature contract uses equivalent resistance and physics baseline columns; recipe/tree identity, charge, target crest, and polarity are excluded. Therefore these results describe mixed-model accuracy when the forward search is restricted to 2/3-module candidates, not a separately trained 2/3-only model.

| Route | max ≤2 n | max ≤2 norm | max =3 n | max =3 norm | max >3 excluded |
|---|---:|---:|---:|---:|---:|
| cpri_0p5uf:LI:GSHUNT_v0 | 560 | 0.0404147 | 726 | 0.0521972 | 950 |
| cpri_0p5uf:LI:OSHUNT_v0 | 605 | 0.0377707 | 764 | 0.0524259 | 1000 |
| cpri_0p5uf:SI:GSHUNT_v0 | 570 | 0.00465053 | 727 | 0.00603229 | 1007 |
| cpri_0p5uf:SI:OSHUNT_v0 | 595 | 0.00559934 | 731 | 0.00613034 | 1011 |
| research_3uf:LI:GSHUNT_v0 | 594 | 0.0455753 | 745 | 0.0562414 | 1044 |
| research_3uf:LI:OSHUNT_v0 | 612 | 0.0408467 | 832 | 0.0650459 | 1113 |
| research_3uf:SI:GSHUNT_v0 | 636 | 0.00213644 | 755 | 0.00325977 | 1159 |
| research_3uf:SI:OSHUNT_v0 | 815 | 0.00460914 | 1062 | 0.00395478 | 1536 |

Target-level MAE/RMSE/P95/max and tolerance-normalized metrics for both strata are in [`two_three_model_scope.json`](../evidence/phase_b/two_three_model_scope.json). The source and prediction hashes, row-join checks, canonical split counts, and four-module exclusions are recorded there.
