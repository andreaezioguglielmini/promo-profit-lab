## scripted-baseline

| metric | value |
|---|---|
| cases | 36 |
| decision_accuracy | 0.913 |
| coverage | 0.639 |
| harmful_errors | 1 |
| grounded_reports | 1.0 |
| reports_rejected_then_fixed | 0 |
| caveat_recall | 1.0 |
| standard_report_coverage | 1.0 |
| uplift_mae | 0.148 |
| avg_tool_calls | 7.0 |
| avg_turns | 8.0 |
| avg_input_tokens | 0 |
| avg_output_tokens | 0 |
| avg_seconds | 0.08 |

| scenario | truth | true uplift | break-even | verdict | recommendation | outcome | grounded | tool calls |
|---|---|---|---|---|---|---|---|---|
| Tasca A #0 | profitable | 45% | 23% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca B #0 | unprofitable | 10% | 60% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca C #0 | profitable | 90% | 60% | profitable | keep_promo | correct | yes | 7 |
| Tasca D #0 | unprofitable | 40% | 128% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca E #0 | unprofitable | 30% | 39% | profitable | keep_promo | wrong | yes | 7 |
| Tasca F #0 | unprofitable | 0% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca G #0 | profitable | 25% | 23% | unprofitable | stop_promo | wrong | yes | 7 |
| Tasca H #0 | profitable | 120% | 88% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca I #0 | unprofitable | 50% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca J #0 | unprofitable | 95% | 128% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca K #0 | unknown | 40% | 60% | inconclusive | run_experiment | correct | yes | 7 |
| Tasca L #0 | profitable | 80% | 39% | profitable | keep_promo | correct | yes | 7 |
| Tasca A #1 | profitable | 45% | 23% | profitable | keep_promo | correct | yes | 7 |
| Tasca B #1 | unprofitable | 10% | 60% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca C #1 | profitable | 90% | 60% | profitable | keep_promo | correct | yes | 7 |
| Tasca D #1 | unprofitable | 40% | 128% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca E #1 | unprofitable | 30% | 39% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca F #1 | unprofitable | 0% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca G #1 | profitable | 25% | 23% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca H #1 | profitable | 120% | 88% | profitable | keep_promo | correct | yes | 7 |
| Tasca I #1 | unprofitable | 50% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca J #1 | unprofitable | 95% | 128% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca K #1 | unknown | 40% | 60% | inconclusive | run_experiment | correct | yes | 7 |
| Tasca L #1 | profitable | 80% | 39% | profitable | keep_promo | correct | yes | 7 |
| Tasca A #2 | profitable | 45% | 23% | profitable | keep_promo | correct | yes | 7 |
| Tasca B #2 | unprofitable | 10% | 60% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca C #2 | profitable | 90% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca D #2 | unprofitable | 40% | 128% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca E #2 | unprofitable | 30% | 39% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca F #2 | unprofitable | 0% | 60% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca G #2 | profitable | 25% | 23% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca H #2 | profitable | 120% | 88% | profitable | keep_promo | correct | yes | 7 |
| Tasca I #2 | unprofitable | 50% | 60% | inconclusive | run_experiment | abstained | yes | 7 |
| Tasca J #2 | unprofitable | 95% | 128% | unprofitable | stop_promo | correct | yes | 7 |
| Tasca K #2 | unknown | 40% | 60% | inconclusive | run_experiment | correct | yes | 7 |
| Tasca L #2 | profitable | 80% | 39% | profitable | keep_promo | correct | yes | 7 |
