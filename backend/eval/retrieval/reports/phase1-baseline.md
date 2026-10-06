# Retrieval eval — phase1-baseline

System: `legacy` · created 2026-10-06T16:29:39

## Mode: player

Counts: {'positives': 629, 'negatives': 75, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.761 |
| recall@5 | 0.981 |
| mrr | 0.855 |
| coverage_accuracy | 0.810 |
| cite_accuracy | 0.790 |
| partial_rate_pos | 0.205 |
| false_cite_rate | 0.040 |
| navigate_accuracy | 0.771 |
| fallback_rate | 0.000 |
| latency_p50_ms | 310 |
| latency_p95_ms | 1948 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.596 | 0.971 | 0.747 | 0.807 | 0.067 | 0.657 |
| javascript-deep-dive | 0.912 | 1.000 | 0.956 | 0.883 | 0.000 | 0.706 |
| js-engine | 0.730 | 0.952 | 0.830 | 0.919 | 0.000 | 0.667 |
| product-engineering | 0.852 | 1.000 | 0.918 | 0.772 | 0.000 | 0.944 |
| programming-language | 0.776 | 1.000 | 0.870 | 0.857 | 0.053 | 0.789 |
| react-perf | 0.755 | 0.959 | 0.848 | 0.869 | 0.000 | 0.938 |
| real-time | 0.746 | 0.984 | 0.839 | 0.682 | 0.333 | 0.619 |
| state-management | 0.829 | 0.986 | 0.895 | 0.740 | 0.000 | 0.913 |
| web-apis | 0.720 | 0.980 | 0.832 | 0.849 | 0.000 | 0.800 |
| web-framework | 0.820 | 0.984 | 0.900 | 0.719 | 0.000 | 0.800 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 75, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.757 |
| recall@5 | 0.981 |
| mrr | 0.853 |
| coverage_accuracy | 0.780 |
| cite_accuracy | 0.776 |
| partial_rate_pos | 0.247 |
| false_cite_rate | 0.040 |
| navigate_accuracy | 0.724 |
| fallback_rate | 0.000 |
| latency_p50_ms | 308 |
| latency_p95_ms | 1577 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.529 |
| recall@5 | 0.952 |
| mrr | 0.700 |
| coverage_accuracy | 0.752 |
| cite_accuracy | 0.623 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 799 |
| latency_p95_ms | 2092 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.529 | 0.952 | 0.700 | 0.752 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.528 |
| recall@5 | 0.944 |
| mrr | 0.698 |
| coverage_accuracy | 0.745 |
| cite_accuracy | 0.615 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 799 |
| latency_p95_ms | 1949 |

Targets (player): MISSED — coverage_accuracy 0.810 (target >= 0.9); false_cite_rate 0.040 (target <= 0.03); latency_p95_ms 1948.000 (target <= 1500)

Targets (ask): MISSED — coverage_accuracy 0.752 (target >= 0.9); latency_p95_ms 2092.400 (target <= 1500)
