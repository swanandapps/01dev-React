# Retrieval eval — phase2-enriched

System: `legacy` · created 2026-10-06T17:36:35

## Mode: player

Counts: {'positives': 629, 'negatives': 75, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.816 |
| recall@5 | 0.979 |
| mrr | 0.888 |
| shown@3 | 0.925 |
| coverage_accuracy | 0.754 |
| cite_accuracy | 0.847 |
| partial_rate_pos | 0.264 |
| false_cite_rate | 0.027 |
| navigate_accuracy | 0.776 |
| fallback_rate | 0.000 |
| latency_p50_ms | 1032 |
| latency_p95_ms | 3855 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.750 | 0.990 | 0.850 | 0.798 | 0.067 | 0.686 |
| javascript-deep-dive | 0.912 | 1.000 | 0.953 | 0.750 | 0.000 | 0.882 |
| js-engine | 0.682 | 0.984 | 0.816 | 0.851 | 0.000 | 0.762 |
| product-engineering | 0.815 | 1.000 | 0.889 | 0.649 | 0.000 | 0.778 |
| programming-language | 0.862 | 0.983 | 0.921 | 0.818 | 0.000 | 0.789 |
| react-perf | 0.816 | 0.959 | 0.886 | 0.853 | 0.000 | 0.875 |
| real-time | 0.794 | 0.968 | 0.866 | 0.636 | 0.333 | 0.571 |
| state-management | 0.857 | 0.971 | 0.909 | 0.753 | 0.000 | 0.913 |
| web-apis | 0.860 | 0.960 | 0.909 | 0.792 | 0.000 | 0.800 |
| web-framework | 0.869 | 0.967 | 0.919 | 0.578 | 0.000 | 0.800 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 75, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.802 |
| recall@5 | 0.985 |
| mrr | 0.883 |
| shown@3 | 0.926 |
| coverage_accuracy | 0.720 |
| cite_accuracy | 0.828 |
| partial_rate_pos | 0.314 |
| false_cite_rate | 0.027 |
| navigate_accuracy | 0.715 |
| fallback_rate | 0.000 |
| latency_p50_ms | 1026 |
| latency_p95_ms | 3737 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.750 |
| recall@5 | 0.990 |
| mrr | 0.850 |
| shown@3 | 0.692 |
| coverage_accuracy | 0.761 |
| cite_accuracy | 0.833 |
| partial_rate_pos | 0.144 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 740 |
| latency_p95_ms | 1099 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.750 | 0.990 | 0.850 | 0.761 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.764 |
| recall@5 | 1.000 |
| mrr | 0.861 |
| shown@3 | 0.708 |
| coverage_accuracy | 0.787 |
| cite_accuracy | 0.826 |
| partial_rate_pos | 0.112 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 762 |
| latency_p95_ms | 1802 |

## Mode: ask_all

Counts: {'positives': 629, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.750 |
| recall@5 | 0.959 |
| mrr | 0.841 |
| shown@3 | 0.641 |
| coverage_accuracy | 0.739 |
| cite_accuracy | 0.778 |
| partial_rate_pos | 0.184 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 753 |
| latency_p95_ms | 1086 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.692 | 0.971 | 0.811 | 0.807 | 0.000 | — |
| javascript-deep-dive | 0.807 | 0.947 | 0.870 | 0.767 | 0.000 | — |
| js-engine | 0.603 | 0.984 | 0.763 | 0.818 | 0.000 | — |
| product-engineering | 0.685 | 0.944 | 0.788 | 0.632 | 0.000 | — |
| programming-language | 0.828 | 0.948 | 0.889 | 0.787 | 0.000 | — |
| react-perf | 0.775 | 0.959 | 0.865 | 0.792 | 0.000 | — |
| real-time | 0.635 | 0.921 | 0.768 | 0.651 | 0.000 | — |
| state-management | 0.829 | 0.971 | 0.888 | 0.753 | 0.000 | — |
| web-apis | 0.840 | 0.960 | 0.888 | 0.774 | 0.000 | — |
| web-framework | 0.869 | 0.967 | 0.916 | 0.562 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.736 |
| recall@5 | 0.958 |
| mrr | 0.832 |
| shown@3 | 0.595 |
| coverage_accuracy | 0.700 |
| cite_accuracy | 0.767 |
| partial_rate_pos | 0.211 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 773 |
| latency_p95_ms | 1086 |

Run configuration: {"modes": ["player", "ask", "ask_all"], "concurrency": 6, "limit": null, "only": null, "latency_sample": 60, "git_sha": "5ef78e1", "chunk_count": 1329, "launched": {"ask": ["custom-library"], "ask_all": ["custom-library", "javascript-deep-dive", "js-engine", "product-engineering", "programming-language", "react-perf", "real-time", "state-management", "web-apis", "web-framework"]}}

Targets (player): MISSED — coverage_accuracy 0.754 (target >= 0.9); latency_p95_ms 3855.300 (target <= 1500) [latency from a sequential sample of 60 decisions]

Targets (ask): MISSED — coverage_accuracy 0.761 (target >= 0.9) [latency from a sequential sample of 60 decisions]

Targets (ask_all): MISSED — coverage_accuracy 0.739 (target >= 0.9) [latency from a sequential sample of 60 decisions]

# Delta: phase1-baseline → phase2-enriched

## Mode: player

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.761 | 0.816 | +0.054 |
| recall@5 | 0.981 | 0.979 | -0.002 |
| mrr | 0.855 | 0.888 | +0.033 |
| shown@3 | 0.893 | 0.925 | +0.032 |
| coverage_accuracy | 0.811 | 0.754 | -0.057 |
| cite_accuracy | 0.790 | 0.847 | +0.056 |
| partial_rate_pos | 0.203 | 0.264 | +0.060 |
| false_cite_rate | 0.040 | 0.027 | -0.013 |
| navigate_accuracy | 0.771 | 0.776 | +0.005 |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 917 | 1032 | +115 |
| latency_p95_ms | 1619 | 3855 | +2236 |

### player / clean slice

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.757 | 0.802 | +0.044 |
| recall@5 | 0.981 | 0.985 | +0.004 |
| mrr | 0.853 | 0.883 | +0.030 |
| shown@3 | 0.892 | 0.926 | +0.034 |
| coverage_accuracy | 0.781 | 0.720 | -0.062 |
| cite_accuracy | 0.777 | 0.828 | +0.051 |
| partial_rate_pos | 0.245 | 0.314 | +0.070 |
| false_cite_rate | 0.040 | 0.027 | -0.013 |
| navigate_accuracy | 0.724 | 0.715 | -0.008 |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 917 | 1026 | +109 |
| latency_p95_ms | 1477 | 3737 | +2260 |

### player / custom-library

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.750 | +0.154 |
| recall@5 | 0.971 | 0.990 | +0.019 |
| mrr | 0.747 | 0.850 | +0.103 |
| coverage_accuracy | 0.807 | 0.798 | -0.008 |
| false_cite_rate | 0.067 | 0.067 | +0.000 |
| navigate_accuracy | 0.657 | 0.686 | +0.029 |

### player / javascript-deep-dive

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.912 | 0.912 | +0.000 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.956 | 0.953 | -0.003 |
| coverage_accuracy | 0.883 | 0.750 | -0.133 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.706 | 0.882 | +0.176 |

### player / js-engine

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.730 | 0.682 | -0.048 |
| recall@5 | 0.952 | 0.984 | +0.032 |
| mrr | 0.830 | 0.816 | -0.014 |
| coverage_accuracy | 0.919 | 0.851 | -0.068 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.667 | 0.762 | +0.095 |

### player / product-engineering

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.852 | 0.815 | -0.037 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.918 | 0.889 | -0.029 |
| coverage_accuracy | 0.772 | 0.649 | -0.123 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.944 | 0.778 | -0.167 |

### player / programming-language

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.776 | 0.862 | +0.086 |
| recall@5 | 1.000 | 0.983 | -0.017 |
| mrr | 0.870 | 0.921 | +0.050 |
| coverage_accuracy | 0.857 | 0.818 | -0.039 |
| false_cite_rate | 0.053 | 0.000 | -0.053 |
| navigate_accuracy | 0.789 | 0.789 | +0.000 |

### player / react-perf

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.755 | 0.816 | +0.061 |
| recall@5 | 0.959 | 0.959 | +0.000 |
| mrr | 0.848 | 0.886 | +0.038 |
| coverage_accuracy | 0.869 | 0.853 | -0.016 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.938 | 0.875 | -0.062 |

### player / real-time

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.746 | 0.794 | +0.048 |
| recall@5 | 0.984 | 0.968 | -0.016 |
| mrr | 0.839 | 0.866 | +0.026 |
| coverage_accuracy | 0.682 | 0.636 | -0.045 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | 0.619 | 0.571 | -0.048 |

### player / state-management

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.829 | 0.857 | +0.028 |
| recall@5 | 0.986 | 0.971 | -0.014 |
| mrr | 0.895 | 0.909 | +0.014 |
| coverage_accuracy | 0.740 | 0.753 | +0.014 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.913 | 0.913 | +0.000 |

### player / web-apis

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.720 | 0.860 | +0.140 |
| recall@5 | 0.980 | 0.960 | -0.020 |
| mrr | 0.832 | 0.909 | +0.078 |
| coverage_accuracy | 0.849 | 0.792 | -0.057 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

### player / web-framework

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.820 | 0.869 | +0.049 |
| recall@5 | 0.984 | 0.967 | -0.016 |
| mrr | 0.900 | 0.919 | +0.019 |
| coverage_accuracy | 0.734 | 0.578 | -0.156 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

## Mode: ask

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.750 | +0.154 |
| recall@5 | 0.971 | 0.990 | +0.019 |
| mrr | 0.747 | 0.850 | +0.103 |
| shown@3 | 0.635 | 0.692 | +0.058 |
| coverage_accuracy | 0.752 | 0.761 | +0.009 |
| cite_accuracy | 0.623 | 0.833 | +0.210 |
| partial_rate_pos | 0.183 | 0.144 | -0.039 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 822 | 740 | -82 |
| latency_p95_ms | 3331 | 1099 | -2232 |

### ask / clean slice

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.607 | 0.764 | +0.157 |
| recall@5 | 0.966 | 1.000 | +0.034 |
| mrr | 0.753 | 0.861 | +0.107 |
| shown@3 | 0.629 | 0.708 | +0.079 |
| coverage_accuracy | 0.745 | 0.787 | +0.042 |
| cite_accuracy | 0.615 | 0.826 | +0.211 |
| partial_rate_pos | 0.191 | 0.112 | -0.079 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 822 | 762 | -60 |
| latency_p95_ms | 3355 | 1802 | -1553 |

### ask / custom-library

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.596 | 0.750 | +0.154 |
| recall@5 | 0.971 | 0.990 | +0.019 |
| mrr | 0.747 | 0.850 | +0.103 |
| coverage_accuracy | 0.752 | 0.761 | +0.009 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

## Mode: ask_all

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.676 | 0.750 | +0.075 |
| recall@5 | 0.957 | 0.959 | +0.002 |
| mrr | 0.797 | 0.841 | +0.044 |
| shown@3 | 0.679 | 0.641 | -0.038 |
| coverage_accuracy | 0.791 | 0.739 | -0.053 |
| cite_accuracy | 0.705 | 0.778 | +0.073 |
| partial_rate_pos | 0.157 | 0.184 | +0.027 |
| false_cite_rate | 0.030 | 0.000 | -0.030 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 811 | 753 | -58 |
| latency_p95_ms | 3523 | 1086 | -2437 |

### ask_all / clean slice

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.665 | 0.736 | +0.072 |
| recall@5 | 0.952 | 0.958 | +0.006 |
| mrr | 0.789 | 0.832 | +0.043 |
| shown@3 | 0.639 | 0.595 | -0.044 |
| coverage_accuracy | 0.759 | 0.700 | -0.059 |
| cite_accuracy | 0.686 | 0.767 | +0.082 |
| partial_rate_pos | 0.179 | 0.211 | +0.032 |
| false_cite_rate | 0.030 | 0.000 | -0.030 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 842 | 773 | -70 |
| latency_p95_ms | 3676 | 1086 | -2590 |

### ask_all / custom-library

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.529 | 0.692 | +0.163 |
| recall@5 | 0.952 | 0.971 | +0.019 |
| mrr | 0.704 | 0.811 | +0.107 |
| coverage_accuracy | 0.771 | 0.807 | +0.037 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / javascript-deep-dive

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.807 | 0.807 | +0.000 |
| recall@5 | 1.000 | 0.947 | -0.053 |
| mrr | 0.889 | 0.870 | -0.019 |
| coverage_accuracy | 0.883 | 0.767 | -0.117 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / js-engine

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.619 | 0.603 | -0.016 |
| recall@5 | 0.936 | 0.984 | +0.048 |
| mrr | 0.751 | 0.763 | +0.012 |
| coverage_accuracy | 0.894 | 0.818 | -0.076 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / product-engineering

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.611 | 0.685 | +0.074 |
| recall@5 | 0.907 | 0.944 | +0.037 |
| mrr | 0.757 | 0.788 | +0.030 |
| coverage_accuracy | 0.807 | 0.632 | -0.175 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / programming-language

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.741 | 0.828 | +0.086 |
| recall@5 | 0.948 | 0.948 | +0.000 |
| mrr | 0.835 | 0.889 | +0.054 |
| coverage_accuracy | 0.803 | 0.787 | -0.016 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / react-perf

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.714 | 0.775 | +0.061 |
| recall@5 | 0.959 | 0.959 | +0.000 |
| mrr | 0.827 | 0.865 | +0.038 |
| coverage_accuracy | 0.849 | 0.792 | -0.057 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / real-time

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.635 | 0.635 | +0.000 |
| recall@5 | 0.968 | 0.921 | -0.048 |
| mrr | 0.766 | 0.768 | +0.002 |
| coverage_accuracy | 0.697 | 0.651 | -0.045 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / state-management

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.814 | 0.829 | +0.014 |
| recall@5 | 0.943 | 0.971 | +0.029 |
| mrr | 0.882 | 0.888 | +0.005 |
| coverage_accuracy | 0.712 | 0.753 | +0.041 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / web-apis

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.620 | 0.840 | +0.220 |
| recall@5 | 0.980 | 0.960 | -0.020 |
| mrr | 0.763 | 0.888 | +0.125 |
| coverage_accuracy | 0.830 | 0.774 | -0.057 |
| false_cite_rate | 0.333 | 0.000 | -0.333 |
| navigate_accuracy | — | — | — |

### ask_all / web-framework

| metric | phase1-baseline | phase2-enriched | delta |
|---|---|---|---|
| recall@1 | 0.754 | 0.869 | +0.115 |
| recall@5 | 0.984 | 0.967 | -0.016 |
| mrr | 0.858 | 0.916 | +0.058 |
| coverage_accuracy | 0.719 | 0.562 | -0.156 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

