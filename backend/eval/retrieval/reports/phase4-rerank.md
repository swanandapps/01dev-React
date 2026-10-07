# Retrieval eval — phase4-rerank

System: `v2` · created 2026-10-07T08:21:28

## Mode: player

Counts: {'positives': 629, 'negatives': 78, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.855 |
| recall@5 | 0.991 |
| mrr | 0.918 |
| shown@3 | 0.957 |
| coverage_accuracy | 0.983 |
| cite_accuracy | 0.856 |
| partial_rate_pos | 0.003 |
| false_cite_rate | 0.013 |
| navigate_accuracy | 0.863 |
| fallback_rate | 0.052 |
| latency_p50_ms | 1514 |
| latency_p95_ms | 1945 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.760 | 0.962 | 0.855 | 0.984 | 0.000 | 0.771 |
| javascript-deep-dive | 0.930 | 1.000 | 0.965 | 0.983 | 0.000 | 0.882 |
| js-engine | 0.841 | 1.000 | 0.911 | 0.973 | 0.000 | 0.905 |
| product-engineering | 0.833 | 1.000 | 0.909 | 0.965 | 0.000 | 0.889 |
| programming-language | 0.862 | 1.000 | 0.924 | 1.000 | 0.000 | 0.895 |
| react-perf | 0.878 | 1.000 | 0.933 | 0.984 | 0.083 | 1.000 |
| real-time | 0.825 | 0.968 | 0.897 | 1.000 | 0.000 | 0.809 |
| state-management | 0.886 | 1.000 | 0.938 | 0.959 | 0.000 | 0.870 |
| web-apis | 0.940 | 1.000 | 0.965 | 0.981 | 0.000 | 0.800 |
| web-framework | 0.885 | 1.000 | 0.940 | 1.000 | 0.000 | 0.900 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 78, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.861 |
| recall@5 | 0.996 |
| mrr | 0.922 |
| shown@3 | 0.960 |
| coverage_accuracy | 0.980 |
| cite_accuracy | 0.862 |
| partial_rate_pos | 0.002 |
| false_cite_rate | 0.013 |
| navigate_accuracy | 0.837 |
| fallback_rate | 0.045 |
| latency_p50_ms | 1514 |
| latency_p95_ms | 1945 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 8, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.769 |
| recall@5 | 0.971 |
| mrr | 0.861 |
| shown@3 | 0.962 |
| coverage_accuracy | 0.982 |
| cite_accuracy | 0.765 |
| partial_rate_pos | 0.019 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.009 |
| latency_p50_ms | 1681 |
| latency_p95_ms | 2277 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.769 | 0.971 | 0.861 | 0.982 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 8, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.798 |
| recall@5 | 0.989 |
| mrr | 0.883 |
| shown@3 | 0.989 |
| coverage_accuracy | 0.990 |
| cite_accuracy | 0.795 |
| partial_rate_pos | 0.011 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.010 |
| latency_p50_ms | 1663 |
| latency_p95_ms | 2318 |

## Mode: ask_all

Counts: {'positives': 629, 'negatives': 36, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.800 |
| recall@5 | 0.983 |
| mrr | 0.883 |
| shown@3 | 0.967 |
| coverage_accuracy | 0.997 |
| cite_accuracy | 0.800 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.111 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 1899 |
| latency_p95_ms | 2175 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.702 | 0.962 | 0.820 | 1.000 | 0.125 | — |
| javascript-deep-dive | 0.860 | 1.000 | 0.916 | 1.000 | 0.000 | — |
| js-engine | 0.762 | 1.000 | 0.872 | 0.985 | 0.333 | — |
| product-engineering | 0.759 | 0.944 | 0.846 | 1.000 | 0.000 | — |
| programming-language | 0.828 | 0.983 | 0.896 | 1.000 | 0.000 | — |
| react-perf | 0.878 | 1.000 | 0.933 | 1.000 | 0.000 | — |
| real-time | 0.730 | 0.952 | 0.838 | 0.985 | 0.333 | — |
| state-management | 0.857 | 1.000 | 0.922 | 1.000 | 0.333 | — |
| web-apis | 0.840 | 1.000 | 0.917 | 1.000 | 0.000 | — |
| web-framework | 0.869 | 1.000 | 0.925 | 1.000 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 36, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.795 |
| recall@5 | 0.987 |
| mrr | 0.882 |
| shown@3 | 0.971 |
| coverage_accuracy | 0.996 |
| cite_accuracy | 0.795 |
| partial_rate_pos | 0.000 |
| false_cite_rate | 0.111 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 1906 |
| latency_p95_ms | 2192 |

Run configuration: {"modes": ["player", "ask", "ask_all"], "concurrency": 1, "limit": null, "only": null, "latency_sample": 60, "git_sha": "2717ab8", "chunk_count": 1329, "launched": {"ask": ["custom-library"], "ask_all": ["custom-library", "javascript-deep-dive", "js-engine", "product-engineering", "programming-language", "react-perf", "real-time", "state-management", "web-apis", "web-framework"]}}

Targets (player): MISSED — latency_p95_ms 1945.000 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask): MISSED — latency_p95_ms 2277.200 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask_all): MISSED — false_cite_rate 0.111 (target <= 0.03); latency_p95_ms 2174.700 (target <= 1500) [latency from a sequential sample of 60 decisions]

# Delta: phase1-baseline → phase4-rerank

WARNING: run configurations differ, so the numbers may not be comparable: concurrency: 6 → 1

## Mode: player

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.761 | 0.855 | +0.094 |
| recall@5 | 0.981 | 0.991 | +0.010 |
| mrr | 0.855 | 0.918 | +0.063 |
| shown@3 | 0.893 | 0.957 | +0.064 |
| coverage_accuracy | 0.811 | 0.983 | +0.172 |
| cite_accuracy | 0.790 | 0.856 | +0.066 |
| partial_rate_pos | 0.203 | 0.003 | -0.200 |
| false_cite_rate | 0.040 | 0.013 | -0.027 |
| navigate_accuracy | 0.771 | 0.863 | +0.093 |
| fallback_rate | 0.000 | 0.052 | +0.052 |
| latency_p50_ms | 917 | 1514 | +597 |
| latency_p95_ms | 1619 | 1945 | +326 |

### player / clean slice

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.757 | 0.861 | +0.103 |
| recall@5 | 0.981 | 0.996 | +0.015 |
| mrr | 0.853 | 0.922 | +0.069 |
| shown@3 | 0.892 | 0.960 | +0.068 |
| coverage_accuracy | 0.781 | 0.980 | +0.199 |
| cite_accuracy | 0.777 | 0.862 | +0.085 |
| partial_rate_pos | 0.245 | 0.002 | -0.243 |
| false_cite_rate | 0.040 | 0.013 | -0.027 |
| navigate_accuracy | 0.724 | 0.837 | +0.114 |
| fallback_rate | 0.000 | 0.045 | +0.045 |
| latency_p50_ms | 917 | 1514 | +597 |
| latency_p95_ms | 1477 | 1945 | +468 |

### player / custom-library

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.760 | +0.163 |
| recall@5 | 0.971 | 0.962 | -0.010 |
| mrr | 0.747 | 0.855 | +0.108 |
| coverage_accuracy | 0.807 | 0.984 | +0.177 |
| false_cite_rate | 0.067 | 0.000 | -0.067 |
| navigate_accuracy | 0.657 | 0.771 | +0.114 |

### player / javascript-deep-dive

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.912 | 0.930 | +0.017 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.956 | 0.965 | +0.009 |
| coverage_accuracy | 0.883 | 0.983 | +0.100 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.706 | 0.882 | +0.176 |

### player / js-engine

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.730 | 0.841 | +0.111 |
| recall@5 | 0.952 | 1.000 | +0.048 |
| mrr | 0.830 | 0.911 | +0.080 |
| coverage_accuracy | 0.919 | 0.973 | +0.054 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.667 | 0.905 | +0.238 |

### player / product-engineering

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.852 | 0.833 | -0.019 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.918 | 0.909 | -0.009 |
| coverage_accuracy | 0.772 | 0.965 | +0.193 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.944 | 0.889 | -0.055 |

### player / programming-language

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.776 | 0.862 | +0.086 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.870 | 0.924 | +0.054 |
| coverage_accuracy | 0.857 | 1.000 | +0.143 |
| false_cite_rate | 0.053 | 0.000 | -0.053 |
| navigate_accuracy | 0.789 | 0.895 | +0.105 |

### player / react-perf

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.755 | 0.878 | +0.123 |
| recall@5 | 0.959 | 1.000 | +0.041 |
| mrr | 0.848 | 0.933 | +0.085 |
| coverage_accuracy | 0.869 | 0.984 | +0.115 |
| false_cite_rate | 0.000 | 0.083 | +0.083 |
| navigate_accuracy | 0.938 | 1.000 | +0.062 |

### player / real-time

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.746 | 0.825 | +0.079 |
| recall@5 | 0.984 | 0.968 | -0.016 |
| mrr | 0.839 | 0.897 | +0.058 |
| coverage_accuracy | 0.682 | 1.000 | +0.318 |
| false_cite_rate | 0.333 | 0.000 | -0.333 |
| navigate_accuracy | 0.619 | 0.809 | +0.191 |

### player / state-management

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.829 | 0.886 | +0.057 |
| recall@5 | 0.986 | 1.000 | +0.014 |
| mrr | 0.895 | 0.938 | +0.043 |
| coverage_accuracy | 0.740 | 0.959 | +0.219 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.913 | 0.870 | -0.043 |

### player / web-apis

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.720 | 0.940 | +0.220 |
| recall@5 | 0.980 | 1.000 | +0.020 |
| mrr | 0.832 | 0.965 | +0.133 |
| coverage_accuracy | 0.849 | 0.981 | +0.132 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

### player / web-framework

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.820 | 0.885 | +0.066 |
| recall@5 | 0.984 | 1.000 | +0.016 |
| mrr | 0.900 | 0.940 | +0.040 |
| coverage_accuracy | 0.734 | 1.000 | +0.266 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.900 | +0.100 |

## Mode: ask

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.769 | +0.173 |
| recall@5 | 0.971 | 0.971 | +0.000 |
| mrr | 0.747 | 0.861 | +0.114 |
| shown@3 | 0.635 | 0.962 | +0.327 |
| coverage_accuracy | 0.752 | 0.982 | +0.230 |
| cite_accuracy | 0.623 | 0.765 | +0.141 |
| partial_rate_pos | 0.183 | 0.019 | -0.164 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.009 | +0.009 |
| latency_p50_ms | 822 | 1681 | +858 |
| latency_p95_ms | 3331 | 2277 | -1053 |

### ask / clean slice

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.607 | 0.798 | +0.191 |
| recall@5 | 0.966 | 0.989 | +0.022 |
| mrr | 0.753 | 0.883 | +0.130 |
| shown@3 | 0.629 | 0.989 | +0.360 |
| coverage_accuracy | 0.745 | 0.990 | +0.245 |
| cite_accuracy | 0.615 | 0.795 | +0.180 |
| partial_rate_pos | 0.191 | 0.011 | -0.180 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.010 | +0.010 |
| latency_p50_ms | 822 | 1663 | +841 |
| latency_p95_ms | 3355 | 2318 | -1037 |

### ask / custom-library

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.769 | +0.173 |
| recall@5 | 0.971 | 0.971 | +0.000 |
| mrr | 0.747 | 0.861 | +0.114 |
| coverage_accuracy | 0.752 | 0.982 | +0.230 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

## Mode: ask_all

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.676 | 0.800 | +0.124 |
| recall@5 | 0.957 | 0.983 | +0.025 |
| mrr | 0.797 | 0.883 | +0.086 |
| shown@3 | 0.679 | 0.967 | +0.288 |
| coverage_accuracy | 0.791 | 0.997 | +0.206 |
| cite_accuracy | 0.705 | 0.800 | +0.094 |
| partial_rate_pos | 0.157 | 0.000 | -0.157 |
| false_cite_rate | 0.030 | 0.111 | +0.081 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 811 | 1899 | +1088 |
| latency_p95_ms | 3523 | 2175 | -1348 |

### ask_all / clean slice

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.665 | 0.795 | +0.131 |
| recall@5 | 0.952 | 0.987 | +0.036 |
| mrr | 0.789 | 0.882 | +0.093 |
| shown@3 | 0.639 | 0.971 | +0.331 |
| coverage_accuracy | 0.759 | 0.996 | +0.237 |
| cite_accuracy | 0.686 | 0.795 | +0.110 |
| partial_rate_pos | 0.179 | 0.000 | -0.179 |
| false_cite_rate | 0.030 | 0.111 | +0.081 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 842 | 1906 | +1064 |
| latency_p95_ms | 3676 | 2192 | -1484 |

### ask_all / custom-library

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.529 | 0.702 | +0.173 |
| recall@5 | 0.952 | 0.962 | +0.010 |
| mrr | 0.704 | 0.820 | +0.116 |
| coverage_accuracy | 0.771 | 1.000 | +0.229 |
| false_cite_rate | 0.000 | 0.125 | +0.125 |
| navigate_accuracy | — | — | — |

### ask_all / javascript-deep-dive

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.807 | 0.860 | +0.053 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.889 | 0.916 | +0.027 |
| coverage_accuracy | 0.883 | 1.000 | +0.117 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / js-engine

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.619 | 0.762 | +0.143 |
| recall@5 | 0.936 | 1.000 | +0.064 |
| mrr | 0.751 | 0.872 | +0.121 |
| coverage_accuracy | 0.894 | 0.985 | +0.091 |
| false_cite_rate | 0.000 | 0.333 | +0.333 |
| navigate_accuracy | — | — | — |

### ask_all / product-engineering

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.611 | 0.759 | +0.148 |
| recall@5 | 0.907 | 0.944 | +0.037 |
| mrr | 0.757 | 0.846 | +0.089 |
| coverage_accuracy | 0.807 | 1.000 | +0.193 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / programming-language

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.741 | 0.828 | +0.086 |
| recall@5 | 0.948 | 0.983 | +0.034 |
| mrr | 0.835 | 0.896 | +0.062 |
| coverage_accuracy | 0.803 | 1.000 | +0.197 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / react-perf

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.714 | 0.878 | +0.163 |
| recall@5 | 0.959 | 1.000 | +0.041 |
| mrr | 0.827 | 0.933 | +0.105 |
| coverage_accuracy | 0.849 | 1.000 | +0.151 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / real-time

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.635 | 0.730 | +0.095 |
| recall@5 | 0.968 | 0.952 | -0.016 |
| mrr | 0.766 | 0.838 | +0.072 |
| coverage_accuracy | 0.697 | 0.985 | +0.288 |
| false_cite_rate | 0.000 | 0.333 | +0.333 |
| navigate_accuracy | — | — | — |

### ask_all / state-management

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.814 | 0.857 | +0.043 |
| recall@5 | 0.943 | 1.000 | +0.057 |
| mrr | 0.882 | 0.922 | +0.040 |
| coverage_accuracy | 0.712 | 1.000 | +0.288 |
| false_cite_rate | 0.000 | 0.333 | +0.333 |
| navigate_accuracy | — | — | — |

### ask_all / web-apis

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.620 | 0.840 | +0.220 |
| recall@5 | 0.980 | 1.000 | +0.020 |
| mrr | 0.763 | 0.917 | +0.154 |
| coverage_accuracy | 0.830 | 1.000 | +0.170 |
| false_cite_rate | 0.333 | 0.000 | -0.333 |
| navigate_accuracy | — | — | — |

### ask_all / web-framework

| metric | phase1-baseline | phase4-rerank | delta |
|---|---|---|---|
| recall@1 | 0.754 | 0.869 | +0.115 |
| recall@5 | 0.984 | 1.000 | +0.016 |
| mrr | 0.858 | 0.925 | +0.067 |
| coverage_accuracy | 0.719 | 1.000 | +0.281 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

