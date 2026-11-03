# Hana task dataset (stage 2)

pskit version 2.10.0. Built by `tools/build_dataset.py` (seed 2200, 5% validation per category) from a_qa.jsonl, b_build.jsonl, c_fix.jsonl, d_debug.jsonl, e_safety.jsonl, f_explain.jsonl, g_hana.jsonl.

Providers: aws, azure, gcp, onprem only; left out 169 older records (alibaba 27, cloudflare 26, digitalocean 25, huawei 25, ibm 22, oracle 17, tencent 27).

- train: 2985
- val: 156

## Per category

| category | count |
|---|---|
| a_qa | 902 |
| b_build | 684 |
| c_fix | 707 |
| d_debug | 386 |
| e_safety | 205 |
| f_explain | 154 |
| g_hana | 103 |

## Per provider

| provider | count |
|---|---|
| aws | 687 |
| azure | 543 |
| gcp | 605 |
| onprem | 1306 |

## Per persona

| persona | count |
|---|---|
| aws_migrator | 309 |
| beginner | 612 |
| detailed_spec | 653 |
| informal_non_native | 621 |
| pasted_error | 411 |
| terse_expert | 535 |

## Per mode

| mode | count |
|---|---|
| ask | 2748 |
| auto | 393 |

## Per validate result

| result | count |
|---|---|
| fail | 36 |
| n/a | 1123 |
| pass | 1982 |

## Per invoke result

| result | count |
|---|---|
| fail | 8 |
| n/a | 2122 |
| pass | 1011 |
