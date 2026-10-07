# Retrieval eval — phase5-understand

System: `v2` · created 2026-10-07T09:59:50

## Mode: player

Counts: {'positives': 629, 'negatives': 78, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.852 |
| recall@5 | 0.991 |
| mrr | 0.916 |
| shown@3 | 0.976 |
| coverage_accuracy | 0.992 |
| cite_accuracy | 0.852 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.051 |
| navigate_accuracy | 0.883 |
| fallback_rate | 0.006 |
| latency_p50_ms | 1917 |
| latency_p95_ms | 2886 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.750 | 0.971 | 0.849 | 0.984 | 0.111 | 0.771 |
| javascript-deep-dive | 0.930 | 1.000 | 0.965 | 1.000 | 0.000 | 1.000 |
| js-engine | 0.809 | 1.000 | 0.893 | 1.000 | 0.000 | 0.905 |
| product-engineering | 0.889 | 1.000 | 0.934 | 1.000 | 0.000 | 0.833 |
| programming-language | 0.879 | 1.000 | 0.937 | 1.000 | 0.000 | 0.895 |
| react-perf | 0.878 | 1.000 | 0.934 | 0.984 | 0.083 | 1.000 |
| real-time | 0.794 | 0.968 | 0.878 | 0.985 | 0.333 | 0.857 |
| state-management | 0.886 | 1.000 | 0.941 | 0.973 | 0.000 | 0.957 |
| web-apis | 0.920 | 0.980 | 0.950 | 1.000 | 0.000 | 0.800 |
| web-framework | 0.885 | 1.000 | 0.940 | 1.000 | 0.000 | 0.900 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 78, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.861 |
| recall@5 | 0.998 |
| mrr | 0.922 |
| shown@3 | 0.981 |
| coverage_accuracy | 0.989 |
| cite_accuracy | 0.860 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.051 |
| navigate_accuracy | 0.854 |
| fallback_rate | 0.004 |
| latency_p50_ms | 1917 |
| latency_p95_ms | 2942 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 8, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.740 |
| recall@5 | 0.971 |
| mrr | 0.844 |
| shown@3 | 0.942 |
| coverage_accuracy | 0.991 |
| cite_accuracy | 0.738 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.009 |
| latency_p50_ms | 1993 |
| latency_p95_ms | 2970 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.740 | 0.971 | 0.844 | 0.991 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 8, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.764 |
| recall@5 | 0.989 |
| mrr | 0.859 |
| shown@3 | 0.955 |
| coverage_accuracy | 0.990 |
| cite_accuracy | 0.761 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.010 |
| latency_p50_ms | 2006 |
| latency_p95_ms | 2998 |

## Mode: ask_all

Counts: {'positives': 629, 'negatives': 36, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.795 |
| recall@5 | 0.987 |
| mrr | 0.880 |
| shown@3 | 0.962 |
| coverage_accuracy | 0.996 |
| cite_accuracy | 0.795 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.111 |
| navigate_accuracy | — |
| fallback_rate | 0.003 |
| latency_p50_ms | 2179 |
| latency_p95_ms | 3148 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.712 | 0.990 | 0.824 | 1.000 | 0.125 | — |
| javascript-deep-dive | 0.842 | 1.000 | 0.901 | 1.000 | 0.000 | — |
| js-engine | 0.746 | 1.000 | 0.864 | 0.985 | 0.333 | — |
| product-engineering | 0.759 | 0.944 | 0.855 | 1.000 | 0.000 | — |
| programming-language | 0.845 | 0.983 | 0.905 | 1.000 | 0.000 | — |
| react-perf | 0.878 | 1.000 | 0.929 | 1.000 | 0.000 | — |
| real-time | 0.714 | 0.952 | 0.828 | 0.985 | 0.333 | — |
| state-management | 0.843 | 1.000 | 0.912 | 0.986 | 0.333 | — |
| web-apis | 0.820 | 1.000 | 0.903 | 1.000 | 0.000 | — |
| web-framework | 0.869 | 1.000 | 0.925 | 1.000 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 36, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.793 |
| recall@5 | 0.990 |
| mrr | 0.879 |
| shown@3 | 0.964 |
| coverage_accuracy | 0.994 |
| cite_accuracy | 0.793 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.111 |
| navigate_accuracy | — |
| fallback_rate | 0.004 |
| latency_p50_ms | 2179 |
| latency_p95_ms | 3148 |

Run configuration: {"modes": ["player", "ask", "ask_all"], "concurrency": 2, "limit": null, "only": null, "latency_sample": 60, "simulate_lecture": false, "git_sha": "3b14b60", "chunk_count": 1329, "launched": {"ask": ["custom-library"], "ask_all": ["custom-library", "javascript-deep-dive", "js-engine", "product-engineering", "programming-language", "react-perf", "real-time", "state-management", "web-apis", "web-framework"]}}

Targets (player): MISSED — false_cite_rate 0.051 (target <= 0.03); latency_p95_ms 2886.000 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask): MISSED — latency_p95_ms 2969.800 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask_all): MISSED — false_cite_rate 0.111 (target <= 0.03); latency_p95_ms 3148.100 (target <= 1500) [latency from a sequential sample of 60 decisions]

# Delta: phase4-rerank → phase5-understand

WARNING: run configurations differ, so the numbers may not be comparable: concurrency: 1 → 2; simulate_lecture: None → False

## Mode: player

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.855 | 0.852 | -0.003 |
| recall@5 | 0.991 | 0.991 | +0.000 |
| mrr | 0.918 | 0.916 | -0.002 |
| shown@3 | 0.957 | 0.976 | +0.019 |
| coverage_accuracy | 0.983 | 0.992 | +0.009 |
| cite_accuracy | 0.856 | 0.852 | -0.004 |
| partial_rate_pos | 0.003 | 0.000 | -0.003 |
| false_cite_rate | 0.013 | 0.051 | +0.038 |
| navigate_accuracy | 0.863 | 0.883 | +0.020 |
| fallback_rate | 0.052 | 0.006 | -0.047 |
| latency_p50_ms | 1514 | 1917 | +403 |
| latency_p95_ms | 1945 | 2886 | +941 |

### player / clean slice

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.861 | 0.861 | +0.000 |
| recall@5 | 0.996 | 0.998 | +0.002 |
| mrr | 0.922 | 0.922 | -0.000 |
| shown@3 | 0.960 | 0.981 | +0.021 |
| coverage_accuracy | 0.980 | 0.989 | +0.009 |
| cite_accuracy | 0.862 | 0.860 | -0.002 |
| partial_rate_pos | 0.002 | 0.000 | -0.002 |
| false_cite_rate | 0.013 | 0.051 | +0.038 |
| navigate_accuracy | 0.837 | 0.854 | +0.016 |
| fallback_rate | 0.045 | 0.004 | -0.042 |
| latency_p50_ms | 1514 | 1917 | +403 |
| latency_p95_ms | 1945 | 2942 | +997 |

### player / custom-library

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.760 | 0.750 | -0.010 |
| recall@5 | 0.962 | 0.971 | +0.010 |
| mrr | 0.855 | 0.849 | -0.007 |
| coverage_accuracy | 0.984 | 0.984 | +0.000 |
| false_cite_rate | 0.000 | 0.111 | +0.111 |
| navigate_accuracy | 0.771 | 0.771 | +0.000 |

### player / javascript-deep-dive

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.930 | 0.930 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.965 | 0.965 | +0.000 |
| coverage_accuracy | 0.983 | 1.000 | +0.017 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.882 | 1.000 | +0.118 |

### player / js-engine

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.841 | 0.809 | -0.032 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.911 | 0.893 | -0.017 |
| coverage_accuracy | 0.973 | 1.000 | +0.027 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.905 | 0.905 | +0.000 |

### player / product-engineering

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.833 | 0.889 | +0.056 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.909 | 0.934 | +0.025 |
| coverage_accuracy | 0.965 | 1.000 | +0.035 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.889 | 0.833 | -0.056 |

### player / programming-language

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.862 | 0.879 | +0.017 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.924 | 0.937 | +0.013 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.895 | 0.895 | +0.000 |

### player / react-perf

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.878 | 0.878 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.933 | 0.934 | +0.001 |
| coverage_accuracy | 0.984 | 0.984 | +0.000 |
| false_cite_rate | 0.083 | 0.083 | +0.000 |
| navigate_accuracy | 1.000 | 1.000 | +0.000 |

### player / real-time

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.825 | 0.794 | -0.032 |
| recall@5 | 0.968 | 0.968 | +0.000 |
| mrr | 0.897 | 0.878 | -0.019 |
| coverage_accuracy | 1.000 | 0.985 | -0.015 |
| false_cite_rate | 0.000 | 0.333 | +0.333 |
| navigate_accuracy | 0.809 | 0.857 | +0.048 |

### player / state-management

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.886 | 0.886 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.938 | 0.941 | +0.002 |
| coverage_accuracy | 0.959 | 0.973 | +0.014 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.870 | 0.957 | +0.087 |

### player / web-apis

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.940 | 0.920 | -0.020 |
| recall@5 | 1.000 | 0.980 | -0.020 |
| mrr | 0.965 | 0.950 | -0.015 |
| coverage_accuracy | 0.981 | 1.000 | +0.019 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

### player / web-framework

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.885 | 0.885 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.940 | 0.940 | +0.000 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.900 | 0.900 | +0.000 |

## Mode: ask

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.769 | 0.740 | -0.029 |
| recall@5 | 0.971 | 0.971 | +0.000 |
| mrr | 0.861 | 0.844 | -0.017 |
| shown@3 | 0.962 | 0.942 | -0.019 |
| coverage_accuracy | 0.982 | 0.991 | +0.009 |
| cite_accuracy | 0.765 | 0.738 | -0.027 |
| partial_rate_pos | 0.019 | 0.000 | -0.019 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.009 | 0.009 | +0.000 |
| latency_p50_ms | 1681 | 1993 | +312 |
| latency_p95_ms | 2277 | 2970 | +693 |

### ask / clean slice

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.798 | 0.764 | -0.034 |
| recall@5 | 0.989 | 0.989 | +0.000 |
| mrr | 0.883 | 0.859 | -0.024 |
| shown@3 | 0.989 | 0.955 | -0.034 |
| coverage_accuracy | 0.990 | 0.990 | +0.000 |
| cite_accuracy | 0.795 | 0.761 | -0.034 |
| partial_rate_pos | 0.011 | 0.000 | -0.011 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.010 | 0.010 | +0.000 |
| latency_p50_ms | 1663 | 2006 | +343 |
| latency_p95_ms | 2318 | 2998 | +680 |

### ask / custom-library

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.769 | 0.740 | -0.029 |
| recall@5 | 0.971 | 0.971 | +0.000 |
| mrr | 0.861 | 0.844 | -0.017 |
| coverage_accuracy | 0.982 | 0.991 | +0.009 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

## Mode: ask_all

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.800 | 0.795 | -0.005 |
| recall@5 | 0.983 | 0.987 | +0.005 |
| mrr | 0.883 | 0.880 | -0.003 |
| shown@3 | 0.967 | 0.962 | -0.005 |
| coverage_accuracy | 0.997 | 0.996 | -0.001 |
| cite_accuracy | 0.800 | 0.795 | -0.005 |
| partial_rate_pos | 0.000 | 0.000 | +0.000 |
| false_cite_rate | 0.111 | 0.111 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.003 | +0.003 |
| latency_p50_ms | 1899 | 2179 | +280 |
| latency_p95_ms | 2175 | 3148 | +973 |

### ask_all / clean slice

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.795 | 0.793 | -0.002 |
| recall@5 | 0.987 | 0.990 | +0.002 |
| mrr | 0.882 | 0.879 | -0.002 |
| shown@3 | 0.971 | 0.964 | -0.006 |
| coverage_accuracy | 0.996 | 0.994 | -0.002 |
| cite_accuracy | 0.795 | 0.793 | -0.003 |
| partial_rate_pos | 0.000 | 0.000 | +0.000 |
| false_cite_rate | 0.111 | 0.111 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.004 | +0.004 |
| latency_p50_ms | 1906 | 2179 | +272 |
| latency_p95_ms | 2192 | 3148 | +956 |

### ask_all / custom-library

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.702 | 0.712 | +0.010 |
| recall@5 | 0.962 | 0.990 | +0.029 |
| mrr | 0.820 | 0.824 | +0.004 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.125 | 0.125 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / javascript-deep-dive

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.860 | 0.842 | -0.018 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.916 | 0.901 | -0.015 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / js-engine

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.762 | 0.746 | -0.016 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.872 | 0.864 | -0.008 |
| coverage_accuracy | 0.985 | 0.985 | +0.000 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / product-engineering

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.759 | 0.759 | +0.000 |
| recall@5 | 0.944 | 0.944 | +0.000 |
| mrr | 0.846 | 0.855 | +0.009 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / programming-language

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.828 | 0.845 | +0.017 |
| recall@5 | 0.983 | 0.983 | +0.000 |
| mrr | 0.896 | 0.905 | +0.009 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / react-perf

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.878 | 0.878 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.933 | 0.929 | -0.003 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / real-time

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.730 | 0.714 | -0.016 |
| recall@5 | 0.952 | 0.952 | +0.000 |
| mrr | 0.838 | 0.828 | -0.010 |
| coverage_accuracy | 0.985 | 0.985 | +0.000 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / state-management

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.857 | 0.843 | -0.014 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.922 | 0.912 | -0.010 |
| coverage_accuracy | 1.000 | 0.986 | -0.014 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / web-apis

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.840 | 0.820 | -0.020 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.917 | 0.903 | -0.013 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / web-framework

| metric | phase4-rerank | phase5-understand | delta |
|---|---|---|---|
| recall@1 | 0.869 | 0.869 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.925 | 0.925 | +0.000 |
| coverage_accuracy | 1.000 | 1.000 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

