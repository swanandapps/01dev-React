# Retrieval eval — phase5-understand-lecture

System: `v2` · created 2026-10-07T10:22:05

## Mode: player

Counts: {'positives': 629, 'negatives': 78, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.851 |
| recall@5 | 0.994 |
| mrr | 0.913 |
| shown@3 | 0.968 |
| coverage_accuracy | 0.989 |
| cite_accuracy | 0.854 |
| partial_rate_pos | 0.002 |
| false_cite_rate | 0.051 |
| navigate_accuracy | 0.878 |
| fallback_rate | 0.017 |
| latency_p50_ms | 2483 |
| latency_p95_ms | 3259 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.721 | 0.990 | 0.833 | 0.967 | 0.167 | 0.771 |
| javascript-deep-dive | 0.930 | 1.000 | 0.962 | 1.000 | 0.000 | 1.000 |
| js-engine | 0.873 | 1.000 | 0.927 | 0.987 | 0.000 | 0.905 |
| product-engineering | 0.852 | 0.982 | 0.912 | 1.000 | 0.000 | 0.833 |
| programming-language | 0.914 | 1.000 | 0.951 | 1.000 | 0.000 | 0.895 |
| react-perf | 0.857 | 1.000 | 0.917 | 1.000 | 0.000 | 1.000 |
| real-time | 0.809 | 0.968 | 0.884 | 0.985 | 0.333 | 0.809 |
| state-management | 0.871 | 1.000 | 0.927 | 0.973 | 0.000 | 0.957 |
| web-apis | 0.920 | 1.000 | 0.957 | 1.000 | 0.000 | 0.800 |
| web-framework | 0.869 | 1.000 | 0.934 | 1.000 | 0.000 | 0.900 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 78, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.848 |
| recall@5 | 0.998 |
| mrr | 0.914 |
| shown@3 | 0.971 |
| coverage_accuracy | 0.986 |
| cite_accuracy | 0.853 |
| partial_rate_pos | 0.002 |
| false_cite_rate | 0.051 |
| navigate_accuracy | 0.846 |
| fallback_rate | 0.015 |
| latency_p50_ms | 2587 |
| latency_p95_ms | 3412 |

Run configuration: {"modes": ["player"], "concurrency": 2, "limit": null, "only": null, "latency_sample": 60, "simulate_lecture": true, "git_sha": "3b14b60+dirty", "chunk_count": 1329, "launched": {}}

Targets (player): MISSED — false_cite_rate 0.051 (target <= 0.03); latency_p95_ms 3258.700 (target <= 1500) [latency from a sequential sample of 60 decisions]

# Delta: phase5-understand → phase5-understand-lecture

WARNING: run configurations differ, so the numbers may not be comparable: launched: {'ask': ['custom-library'], 'ask_all': ['custom-library', 'javascript-deep-dive', 'js-engine', 'product-engineering', 'programming-language', 'react-perf', 'real-time', 'state-management', 'web-apis', 'web-framework']} → {}; modes: ['player', 'ask', 'ask_all'] → ['player']; simulate_lecture: False → True

Note: mode(s) present in only one run, not compared: ask, ask_all

## Mode: player

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.852 | 0.851 | -0.001 |
| recall@5 | 0.991 | 0.994 | +0.003 |
| mrr | 0.916 | 0.913 | -0.002 |
| shown@3 | 0.976 | 0.968 | -0.008 |
| coverage_accuracy | 0.992 | 0.989 | -0.003 |
| cite_accuracy | 0.852 | 0.854 | +0.003 |
| partial_rate_pos | 0.000 | 0.002 | +0.002 |
| false_cite_rate | 0.051 | 0.051 | +0.000 |
| navigate_accuracy | 0.883 | 0.878 | -0.005 |
| fallback_rate | 0.006 | 0.017 | +0.011 |
| latency_p50_ms | 1917 | 2483 | +566 |
| latency_p95_ms | 2886 | 3259 | +373 |

### player / clean slice

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.861 | 0.848 | -0.013 |
| recall@5 | 0.998 | 0.998 | +0.000 |
| mrr | 0.922 | 0.914 | -0.008 |
| shown@3 | 0.981 | 0.971 | -0.010 |
| coverage_accuracy | 0.989 | 0.986 | -0.004 |
| cite_accuracy | 0.860 | 0.853 | -0.007 |
| partial_rate_pos | 0.000 | 0.002 | +0.002 |
| false_cite_rate | 0.051 | 0.051 | +0.000 |
| navigate_accuracy | 0.854 | 0.846 | -0.008 |
| fallback_rate | 0.004 | 0.015 | +0.011 |
| latency_p50_ms | 1917 | 2587 | +670 |
| latency_p95_ms | 2942 | 3412 | +470 |

### player / custom-library

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.750 | 0.721 | -0.029 |
| recall@5 | 0.971 | 0.990 | +0.019 |
| mrr | 0.849 | 0.833 | -0.016 |
| coverage_accuracy | 0.984 | 0.967 | -0.016 |
| false_cite_rate | 0.111 | 0.167 | +0.056 |
| navigate_accuracy | 0.771 | 0.771 | +0.000 |

### player / javascript-deep-dive

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.930 | 0.930 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.965 | 0.962 | -0.003 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 1.000 | 1.000 | +0.000 |

### player / js-engine

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.809 | 0.873 | +0.064 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.893 | 0.927 | +0.034 |
| coverage_accuracy | 1.000 | 0.987 | -0.013 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.905 | 0.905 | +0.000 |

### player / product-engineering

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.889 | 0.852 | -0.037 |
| recall@5 | 1.000 | 0.982 | -0.018 |
| mrr | 0.934 | 0.912 | -0.022 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.833 | 0.833 | +0.000 |

### player / programming-language

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.879 | 0.914 | +0.034 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.937 | 0.951 | +0.014 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.895 | 0.895 | +0.000 |

### player / react-perf

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.878 | 0.857 | -0.021 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.934 | 0.917 | -0.017 |
| coverage_accuracy | 0.984 | 1.000 | +0.016 |
| false_cite_rate | 0.083 | 0.000 | -0.083 |
| navigate_accuracy | 1.000 | 1.000 | +0.000 |

### player / real-time

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.794 | 0.809 | +0.016 |
| recall@5 | 0.968 | 0.968 | +0.000 |
| mrr | 0.878 | 0.884 | +0.005 |
| coverage_accuracy | 0.985 | 0.985 | +0.000 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | 0.857 | 0.809 | -0.048 |

### player / state-management

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.886 | 0.871 | -0.014 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.941 | 0.927 | -0.013 |
| coverage_accuracy | 0.973 | 0.973 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.957 | 0.957 | +0.000 |

### player / web-apis

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.920 | 0.920 | +0.000 |
| recall@5 | 0.980 | 1.000 | +0.020 |
| mrr | 0.950 | 0.957 | +0.007 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

### player / web-framework

| metric | phase5-understand | phase5-understand-lecture | delta |
|---|---|---|---|
| recall@1 | 0.885 | 0.869 | -0.016 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.940 | 0.934 | -0.005 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.900 | 0.900 | +0.000 |

