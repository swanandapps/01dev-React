# Retrieval eval — phase1-baseline

System: `legacy` · created 2026-10-06T16:50:49

## Mode: player

Counts: {'positives': 629, 'negatives': 75, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.761 |
| recall@5 | 0.981 |
| mrr | 0.855 |
| shown@3 | 0.893 |
| coverage_accuracy | 0.811 |
| cite_accuracy | 0.790 |
| partial_rate_pos | 0.203 |
| false_cite_rate | 0.040 |
| navigate_accuracy | 0.771 |
| fallback_rate | 0.000 |
| latency_p50_ms | 917 |
| latency_p95_ms | 1619 |

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
| web-framework | 0.820 | 0.984 | 0.900 | 0.734 | 0.000 | 0.800 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 75, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.757 |
| recall@5 | 0.981 |
| mrr | 0.853 |
| shown@3 | 0.892 |
| coverage_accuracy | 0.781 |
| cite_accuracy | 0.777 |
| partial_rate_pos | 0.245 |
| false_cite_rate | 0.040 |
| navigate_accuracy | 0.724 |
| fallback_rate | 0.000 |
| latency_p50_ms | 917 |
| latency_p95_ms | 1477 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.596 |
| recall@5 | 0.971 |
| mrr | 0.747 |
| shown@3 | 0.635 |
| coverage_accuracy | 0.752 |
| cite_accuracy | 0.623 |
| partial_rate_pos | 0.183 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 822 |
| latency_p95_ms | 3331 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.596 | 0.971 | 0.747 | 0.752 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.607 |
| recall@5 | 0.966 |
| mrr | 0.753 |
| shown@3 | 0.629 |
| coverage_accuracy | 0.745 |
| cite_accuracy | 0.615 |
| partial_rate_pos | 0.191 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 822 |
| latency_p95_ms | 3355 |

## Mode: ask_all

Counts: {'positives': 629, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.676 |
| recall@5 | 0.957 |
| mrr | 0.797 |
| shown@3 | 0.679 |
| coverage_accuracy | 0.791 |
| cite_accuracy | 0.705 |
| partial_rate_pos | 0.157 |
| false_cite_rate | 0.030 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 811 |
| latency_p95_ms | 3523 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.529 | 0.952 | 0.704 | 0.771 | 0.000 | — |
| javascript-deep-dive | 0.807 | 1.000 | 0.889 | 0.883 | 0.000 | — |
| js-engine | 0.619 | 0.936 | 0.751 | 0.894 | 0.000 | — |
| product-engineering | 0.611 | 0.907 | 0.757 | 0.807 | 0.000 | — |
| programming-language | 0.741 | 0.948 | 0.835 | 0.803 | 0.000 | — |
| react-perf | 0.714 | 0.959 | 0.827 | 0.849 | 0.000 | — |
| real-time | 0.635 | 0.968 | 0.766 | 0.697 | 0.000 | — |
| state-management | 0.814 | 0.943 | 0.882 | 0.712 | 0.000 | — |
| web-apis | 0.620 | 0.980 | 0.763 | 0.830 | 0.333 | — |
| web-framework | 0.754 | 0.984 | 0.858 | 0.719 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.665 |
| recall@5 | 0.952 |
| mrr | 0.789 |
| shown@3 | 0.639 |
| coverage_accuracy | 0.759 |
| cite_accuracy | 0.686 |
| partial_rate_pos | 0.179 |
| false_cite_rate | 0.030 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 842 |
| latency_p95_ms | 3676 |

Run configuration: {"modes": ["player", "ask", "ask_all"], "concurrency": 6, "limit": null, "only": null, "latency_sample": 60, "git_sha": "e4373ef+dirty", "chunk_count": 1329, "launched": {"ask": ["custom-library"], "ask_all": ["custom-library", "javascript-deep-dive", "js-engine", "product-engineering", "programming-language", "react-perf", "real-time", "state-management", "web-apis", "web-framework"]}}

Targets (player): MISSED — coverage_accuracy 0.811 (target >= 0.9); false_cite_rate 0.040 (target <= 0.03); latency_p95_ms 1619.100 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask): MISSED — coverage_accuracy 0.752 (target >= 0.9); latency_p95_ms 3330.600 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask_all): MISSED — coverage_accuracy 0.791 (target >= 0.9); false_cite_rate 0.030 (target <= 0.03); latency_p95_ms 3523.200 (target <= 1500) [latency from a sequential sample of 60 decisions]
