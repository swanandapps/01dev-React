# Retrieval eval — phase3-hybrid

System: `legacy` · created 2026-10-06T18:25:07

## Mode: player

Counts: {'positives': 629, 'negatives': 75, 'navigate': 205, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.825 |
| recall@5 | 0.987 |
| mrr | 0.898 |
| shown@3 | 0.925 |
| coverage_accuracy | 0.754 |
| cite_accuracy | 0.847 |
| partial_rate_pos | 0.264 |
| false_cite_rate | 0.027 |
| navigate_accuracy | 0.776 |
| fallback_rate | 0.000 |
| latency_p50_ms | 943 |
| latency_p95_ms | 1152 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.731 | 0.971 | 0.837 | 0.798 | 0.067 | 0.686 |
| javascript-deep-dive | 0.947 | 1.000 | 0.974 | 0.750 | 0.000 | 0.882 |
| js-engine | 0.762 | 1.000 | 0.865 | 0.851 | 0.000 | 0.762 |
| product-engineering | 0.796 | 1.000 | 0.890 | 0.649 | 0.000 | 0.778 |
| programming-language | 0.845 | 0.983 | 0.904 | 0.818 | 0.000 | 0.789 |
| react-perf | 0.816 | 0.980 | 0.896 | 0.853 | 0.000 | 0.875 |
| real-time | 0.794 | 0.968 | 0.876 | 0.636 | 0.333 | 0.571 |
| state-management | 0.886 | 1.000 | 0.931 | 0.753 | 0.000 | 0.913 |
| web-apis | 0.900 | 1.000 | 0.945 | 0.792 | 0.000 | 0.800 |
| web-framework | 0.853 | 0.984 | 0.915 | 0.578 | 0.000 | 0.800 |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 75, 'navigate': 123, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.829 |
| recall@5 | 0.990 |
| mrr | 0.901 |
| shown@3 | 0.926 |
| coverage_accuracy | 0.720 |
| cite_accuracy | 0.828 |
| partial_rate_pos | 0.314 |
| false_cite_rate | 0.027 |
| navigate_accuracy | 0.715 |
| fallback_rate | 0.000 |
| latency_p50_ms | 944 |
| latency_p95_ms | 1177 |

## Mode: ask

Counts: {'positives': 104, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.731 |
| recall@5 | 0.971 |
| mrr | 0.837 |
| shown@3 | 0.663 |
| coverage_accuracy | 0.734 |
| cite_accuracy | 0.827 |
| partial_rate_pos | 0.173 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 642 |
| latency_p95_ms | 1209 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.731 | 0.971 | 0.837 | 0.734 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 89, 'negatives': 5, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.753 |
| recall@5 | 0.978 |
| mrr | 0.853 |
| shown@3 | 0.685 |
| coverage_accuracy | 0.755 |
| cite_accuracy | 0.833 |
| partial_rate_pos | 0.146 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 642 |
| latency_p95_ms | 1209 |

## Mode: ask_all

Counts: {'positives': 629, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | value |
|---|---|
| recall@1 | 0.766 |
| recall@5 | 0.976 |
| mrr | 0.857 |
| shown@3 | 0.647 |
| coverage_accuracy | 0.733 |
| cite_accuracy | 0.779 |
| partial_rate_pos | 0.191 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 686 |
| latency_p95_ms | 1051 |

| course | recall@1 | recall@5 | mrr | coverage_accuracy | false_cite_rate | navigate_accuracy |
|---|---|---|---|---|---|---|
| custom-library | 0.712 | 0.971 | 0.821 | 0.771 | 0.000 | — |
| javascript-deep-dive | 0.825 | 1.000 | 0.895 | 0.767 | 0.000 | — |
| js-engine | 0.698 | 0.984 | 0.827 | 0.818 | 0.000 | — |
| product-engineering | 0.704 | 0.944 | 0.811 | 0.632 | 0.000 | — |
| programming-language | 0.793 | 0.966 | 0.862 | 0.787 | 0.000 | — |
| react-perf | 0.816 | 0.980 | 0.896 | 0.792 | 0.000 | — |
| real-time | 0.682 | 0.952 | 0.801 | 0.651 | 0.000 | — |
| state-management | 0.843 | 0.986 | 0.907 | 0.753 | 0.000 | — |
| web-apis | 0.800 | 1.000 | 0.882 | 0.774 | 0.000 | — |
| web-framework | 0.836 | 0.984 | 0.896 | 0.562 | 0.000 | — |

Clean slice (no leaks, body lectures) counts: {'positives': 474, 'negatives': 33, 'navigate': 0, 'errors': 0}

| metric | clean |
|---|---|
| recall@1 | 0.770 |
| recall@5 | 0.977 |
| mrr | 0.859 |
| shown@3 | 0.603 |
| coverage_accuracy | 0.694 |
| cite_accuracy | 0.768 |
| partial_rate_pos | 0.217 |
| false_cite_rate | 0.000 |
| navigate_accuracy | — |
| fallback_rate | 0.000 |
| latency_p50_ms | 686 |
| latency_p95_ms | 1170 |

Run configuration: {"modes": ["player", "ask", "ask_all"], "concurrency": 6, "limit": null, "only": null, "latency_sample": 60, "git_sha": "1a3fcf3", "chunk_count": 1329, "launched": {"ask": ["custom-library"], "ask_all": ["custom-library", "javascript-deep-dive", "js-engine", "product-engineering", "programming-language", "react-perf", "real-time", "state-management", "web-apis", "web-framework"]}}

Targets (player): MISSED — coverage_accuracy 0.754 (target >= 0.9) [latency from a sequential sample of 60 decisions]

Targets (ask): MISSED — coverage_accuracy 0.734 (target >= 0.9) [latency from a sequential sample of 60 decisions]

Targets (ask_all): MISSED — coverage_accuracy 0.733 (target >= 0.9) [latency from a sequential sample of 60 decisions]

# Delta: phase2-enriched → phase3-hybrid

## Mode: player

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.816 | 0.825 | +0.009 |
| recall@5 | 0.979 | 0.987 | +0.008 |
| mrr | 0.888 | 0.898 | +0.010 |
| shown@3 | 0.925 | 0.925 | +0.000 |
| coverage_accuracy | 0.754 | 0.754 | +0.000 |
| cite_accuracy | 0.847 | 0.847 | +0.000 |
| partial_rate_pos | 0.264 | 0.264 | +0.000 |
| false_cite_rate | 0.027 | 0.027 | +0.000 |
| navigate_accuracy | 0.776 | 0.776 | +0.000 |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 1032 | 943 | -89 |
| latency_p95_ms | 3855 | 1152 | -2704 |

### player / clean slice

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.802 | 0.829 | +0.027 |
| recall@5 | 0.985 | 0.990 | +0.004 |
| mrr | 0.883 | 0.901 | +0.018 |
| shown@3 | 0.926 | 0.926 | +0.000 |
| coverage_accuracy | 0.720 | 0.720 | +0.000 |
| cite_accuracy | 0.828 | 0.828 | +0.000 |
| partial_rate_pos | 0.314 | 0.314 | +0.000 |
| false_cite_rate | 0.027 | 0.027 | +0.000 |
| navigate_accuracy | 0.715 | 0.715 | +0.000 |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 1026 | 944 | -82 |
| latency_p95_ms | 3737 | 1177 | -2560 |

### player / custom-library

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.750 | 0.731 | -0.019 |
| recall@5 | 0.990 | 0.971 | -0.019 |
| mrr | 0.850 | 0.837 | -0.013 |
| coverage_accuracy | 0.798 | 0.798 | +0.000 |
| false_cite_rate | 0.067 | 0.067 | +0.000 |
| navigate_accuracy | 0.686 | 0.686 | +0.000 |

### player / javascript-deep-dive

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.912 | 0.947 | +0.035 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.953 | 0.974 | +0.020 |
| coverage_accuracy | 0.750 | 0.750 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.882 | 0.882 | +0.000 |

### player / js-engine

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.682 | 0.762 | +0.079 |
| recall@5 | 0.984 | 1.000 | +0.016 |
| mrr | 0.816 | 0.865 | +0.049 |
| coverage_accuracy | 0.851 | 0.851 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.762 | 0.762 | +0.000 |

### player / product-engineering

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.815 | 0.796 | -0.018 |
| recall@5 | 1.000 | 1.000 | +0.000 |
| mrr | 0.889 | 0.890 | +0.001 |
| coverage_accuracy | 0.649 | 0.649 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.778 | 0.778 | +0.000 |

### player / programming-language

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.862 | 0.845 | -0.017 |
| recall@5 | 0.983 | 0.983 | +0.000 |
| mrr | 0.921 | 0.904 | -0.017 |
| coverage_accuracy | 0.818 | 0.818 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.789 | 0.789 | +0.000 |

### player / react-perf

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.816 | 0.816 | +0.000 |
| recall@5 | 0.959 | 0.980 | +0.020 |
| mrr | 0.886 | 0.896 | +0.010 |
| coverage_accuracy | 0.853 | 0.853 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.875 | 0.875 | +0.000 |

### player / real-time

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.794 | 0.794 | +0.000 |
| recall@5 | 0.968 | 0.968 | +0.000 |
| mrr | 0.866 | 0.876 | +0.010 |
| coverage_accuracy | 0.636 | 0.636 | +0.000 |
| false_cite_rate | 0.333 | 0.333 | +0.000 |
| navigate_accuracy | 0.571 | 0.571 | +0.000 |

### player / state-management

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.857 | 0.886 | +0.029 |
| recall@5 | 0.971 | 1.000 | +0.029 |
| mrr | 0.909 | 0.931 | +0.022 |
| coverage_accuracy | 0.753 | 0.753 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.913 | 0.913 | +0.000 |

### player / web-apis

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.860 | 0.900 | +0.040 |
| recall@5 | 0.960 | 1.000 | +0.040 |
| mrr | 0.909 | 0.945 | +0.036 |
| coverage_accuracy | 0.792 | 0.792 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

### player / web-framework

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.869 | 0.853 | -0.016 |
| recall@5 | 0.967 | 0.984 | +0.016 |
| mrr | 0.919 | 0.915 | -0.004 |
| coverage_accuracy | 0.578 | 0.578 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | 0.800 | 0.800 | +0.000 |

## Mode: ask

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.750 | 0.731 | -0.019 |
| recall@5 | 0.990 | 0.971 | -0.019 |
| mrr | 0.850 | 0.837 | -0.013 |
| shown@3 | 0.692 | 0.663 | -0.029 |
| coverage_accuracy | 0.761 | 0.734 | -0.028 |
| cite_accuracy | 0.833 | 0.827 | -0.007 |
| partial_rate_pos | 0.144 | 0.173 | +0.029 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 740 | 642 | -98 |
| latency_p95_ms | 1099 | 1209 | +110 |

### ask / clean slice

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.764 | 0.753 | -0.011 |
| recall@5 | 1.000 | 0.978 | -0.022 |
| mrr | 0.861 | 0.853 | -0.008 |
| shown@3 | 0.708 | 0.685 | -0.022 |
| coverage_accuracy | 0.787 | 0.755 | -0.032 |
| cite_accuracy | 0.826 | 0.833 | +0.007 |
| partial_rate_pos | 0.112 | 0.146 | +0.034 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 762 | 642 | -121 |
| latency_p95_ms | 1802 | 1209 | -593 |

### ask / custom-library

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.750 | 0.731 | -0.019 |
| recall@5 | 0.990 | 0.971 | -0.019 |
| mrr | 0.850 | 0.837 | -0.013 |
| coverage_accuracy | 0.761 | 0.734 | -0.028 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

## Mode: ask_all

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.750 | 0.766 | +0.016 |
| recall@5 | 0.959 | 0.976 | +0.017 |
| mrr | 0.841 | 0.857 | +0.015 |
| shown@3 | 0.641 | 0.647 | +0.006 |
| coverage_accuracy | 0.739 | 0.733 | -0.006 |
| cite_accuracy | 0.778 | 0.779 | +0.000 |
| partial_rate_pos | 0.184 | 0.191 | +0.006 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 753 | 686 | -66 |
| latency_p95_ms | 1086 | 1051 | -36 |

### ask_all / clean slice

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.736 | 0.770 | +0.034 |
| recall@5 | 0.958 | 0.977 | +0.019 |
| mrr | 0.832 | 0.859 | +0.027 |
| shown@3 | 0.595 | 0.603 | +0.009 |
| coverage_accuracy | 0.700 | 0.694 | -0.006 |
| cite_accuracy | 0.767 | 0.768 | +0.001 |
| partial_rate_pos | 0.211 | 0.217 | +0.006 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| latency_p50_ms | 773 | 686 | -86 |
| latency_p95_ms | 1086 | 1170 | +84 |

### ask_all / custom-library

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.692 | 0.712 | +0.019 |
| recall@5 | 0.971 | 0.971 | +0.000 |
| mrr | 0.811 | 0.821 | +0.010 |
| coverage_accuracy | 0.807 | 0.771 | -0.037 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / javascript-deep-dive

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.807 | 0.825 | +0.018 |
| recall@5 | 0.947 | 1.000 | +0.053 |
| mrr | 0.870 | 0.895 | +0.026 |
| coverage_accuracy | 0.767 | 0.767 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / js-engine

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.603 | 0.698 | +0.095 |
| recall@5 | 0.984 | 0.984 | +0.000 |
| mrr | 0.763 | 0.827 | +0.064 |
| coverage_accuracy | 0.818 | 0.818 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / product-engineering

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.685 | 0.704 | +0.018 |
| recall@5 | 0.944 | 0.944 | +0.000 |
| mrr | 0.788 | 0.811 | +0.023 |
| coverage_accuracy | 0.632 | 0.632 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / programming-language

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.828 | 0.793 | -0.034 |
| recall@5 | 0.948 | 0.966 | +0.017 |
| mrr | 0.889 | 0.862 | -0.027 |
| coverage_accuracy | 0.787 | 0.787 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / react-perf

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.775 | 0.816 | +0.041 |
| recall@5 | 0.959 | 0.980 | +0.020 |
| mrr | 0.865 | 0.896 | +0.031 |
| coverage_accuracy | 0.792 | 0.792 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / real-time

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.635 | 0.682 | +0.048 |
| recall@5 | 0.921 | 0.952 | +0.032 |
| mrr | 0.768 | 0.801 | +0.033 |
| coverage_accuracy | 0.651 | 0.651 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / state-management

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.829 | 0.843 | +0.014 |
| recall@5 | 0.971 | 0.986 | +0.014 |
| mrr | 0.888 | 0.907 | +0.019 |
| coverage_accuracy | 0.753 | 0.753 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / web-apis

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.840 | 0.800 | -0.040 |
| recall@5 | 0.960 | 1.000 | +0.040 |
| mrr | 0.888 | 0.882 | -0.006 |
| coverage_accuracy | 0.774 | 0.774 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

### ask_all / web-framework

| metric | phase2-enriched | phase3-hybrid | delta |
|---|---|---|---|
| recall@1 | 0.869 | 0.836 | -0.033 |
| recall@5 | 0.967 | 0.984 | +0.016 |
| mrr | 0.916 | 0.896 | -0.021 |
| coverage_accuracy | 0.562 | 0.562 | +0.000 |
| false_cite_rate | 0.000 | 0.000 | +0.000 |
| navigate_accuracy | — | — | — |

