# Retrieval eval history

| label | system | mode | recall@1 | recall@5 | mrr | shown@3 | coverage | false_cite | navigate | p50 ms | p95 ms | rows |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| phase1-baseline | legacy | player | 0.761 | 0.981 | 0.855 | 0.893 | 0.811 | 0.040 | 0.771 | 917 | 1619 | 909 |
| phase1-baseline | legacy | ask | 0.596 | 0.971 | 0.747 | 0.635 | 0.752 | 0.000 | — | 822 | 3331 | 109 |
| phase1-baseline | legacy | ask_all | 0.676 | 0.957 | 0.797 | 0.679 | 0.791 | 0.030 | — | 811 | 3523 | 662 |
| phase2-enriched | legacy | player | 0.816 | 0.979 | 0.888 | 0.925 | 0.754 | 0.027 | 0.776 | 1032 | 3855 | 909 |
| phase2-enriched | legacy | ask | 0.750 | 0.990 | 0.850 | 0.692 | 0.761 | 0.000 | — | 740 | 1099 | 109 |
| phase2-enriched | legacy | ask_all | 0.750 | 0.959 | 0.841 | 0.641 | 0.739 | 0.000 | — | 753 | 1086 | 662 |
| phase3-hybrid | legacy | player | 0.825 | 0.987 | 0.898 | 0.925 | 0.754 | 0.027 | 0.776 | 943 | 1152 | 909 |
| phase3-hybrid | legacy | ask | 0.731 | 0.971 | 0.837 | 0.663 | 0.734 | 0.000 | — | 642 | 1209 | 109 |
| phase3-hybrid | legacy | ask_all | 0.766 | 0.976 | 0.857 | 0.647 | 0.733 | 0.000 | — | 686 | 1051 | 662 |
| phase4-rerank | v2 | player | 0.855 | 0.991 | 0.918 | 0.957 | 0.983 | 0.013 | 0.863 | 1514 | 1945 | 912 |
| phase4-rerank | v2 | ask | 0.769 | 0.971 | 0.861 | 0.962 | 0.982 | 0.000 | — | 1681 | 2277 | 112 |
| phase4-rerank | v2 | ask_all | 0.800 | 0.983 | 0.883 | 0.967 | 0.997 | 0.111 | — | 1899 | 2175 | 665 |

## Notes — phase4-rerank (2026-10-07)

- The reranker now decides coverage everywhere. Coverage accuracy went from 0.75–0.81 to 0.98–1.00. shown@3 on Ask went from 0.64 to 0.96.
- **ask_all false_cite 0.111 = 2 rows, both label noise.** Both are off-topic negatives that were written before the real-time course transcripts existed:
  - `neg-06` "nginx as a reverse proxy" was cited to real-time 7.3, which does set up nginx in front of Pulse;
  - `neg-15` "Kafka consumer group" was cited to real-time 6.3, which teaches consumer groups with Redis Streams (partial at most).
  
  ask_all is an eval-only mode that treats every launched course as owned; real Ask scopes to owned courses, and its false_cite is 0.000. Relabel both rows in a separate, justified pass.
- **Fallback rate:** player 5.2%, ask 0.9%, ask_all 0.0%. All 52 fallbacks were rerank `TimeoutError`s at the 3 s cap; there were no parse failures.
- **Latency** comes from a single run (the user asked for speed; median-of-3 was skipped). p50 is 1.5–1.9 s and p95 is 1.9–2.3 s, above the 1.5 s target. The time is bound by the rerank call. Phase 5 adds a query-understanding call in parallel; Phase 6 moves search into SQL.
- **A/B on navigate** (205 rows, 2 runs each):
  - a stricter navigate prompt ("a ONLY for the 1–2 most direct passages") scored 0.8829 against 0.8683 for the current one, +1.5 pp, below the 2 pp bar, so it was reverted;
  - fused order within a tier scored 0.8683, the same as (title_matched, cosine), so it was reverted.
- **Demo checks** (real model): `--enroll 9,11` gave 11/11 no_match. `--enroll 2 --full` gave 5 enrolled_match with deep links (np 11.1, npm link 8.1, IIFE 6.5, prototype 3.6, ES modules 10.1) and 6 no_match, including the vague "what am I weak at?" and "what does this mean?" with no cards. `--player` gave 10/10 auto-ok: jumps to 11.1 @45s ×2 and to 10.1 @197s, and no jump on off-topic or vague questions.
| phase5-understand | v2 | player | 0.852 | 0.991 | 0.916 | 0.976 | 0.992 | 0.051 | 0.883 | 1917 | 2886 | 912 |
| phase5-understand | v2 | ask | 0.740 | 0.971 | 0.844 | 0.942 | 0.991 | 0.000 | — | 1993 | 2970 | 112 |
| phase5-understand | v2 | ask_all | 0.795 | 0.987 | 0.880 | 0.962 | 0.996 | 0.111 | — | 2179 | 3148 | 665 |
| phase5-understand-lecture | v2 | player | 0.851 | 0.994 | 0.913 | 0.968 | 0.989 | 0.051 | 0.878 | 2483 | 3259 | 912 |

## Notes — phase5-understand / phase5-understand-lecture (2026-10-07)

- **Quality, small gains.**
  - Navigate 0.863 → 0.883 (with a watched lecture, 0.878).
  - Player coverage 0.983 → 0.992; Ask coverage 0.982 → 0.991.
  - Player shown@3 0.957 → 0.976. Recall is flat.
  - The rerank fallback rate fell to 0.6–1.7%, against 5.2% in phase 4.
  - Ask recall@1 0.769 → 0.740 (−3 rows of 112, noise-level).
  - The hand rows `hand-followup-np`, `hand-followup-lecture` and `hand-iife` are covered with gold, as they were in phase 4.
- **Player false_cite 0.013 → 0.051 = 4 of 78 negatives; only 1 is a new genuine false cite.**
  - `hand-vague-example` "give me an example" @1.1 now cites 1.1 itself. That is the intended Phase 5 behaviour (an in-lecture vague rewrite), so the label predates Phase 5. Relabel it.
  - `neg-06` nginx is label noise: real-time 7.3 teaches nginx. See the phase 4 notes.
  - `cross-programming-language-1-1-q2-in-react-perf` was already cited in phase 4.
  - **NEW, genuine:** `cross-real-time-3-0-q2-in-custom-library` "data structures to track room membership" was cited to custom-library 5.1.
- **Latency is the cost** (single run each; main pass conc 2, sequential latency sample).
  - Player p50/p95: 1514/1945 → 1917/2886 ms. With a watched lecture, which is the real player case, **2483/3259 ms**.
  - Ask: 1681/2277 → 1993/2970 ms.
  - Why: in the player `lecture_title` is always set, so `needs_rewrite` calls the model on every question, even self-contained ones like "what is an IIFE?". About 0.8–1.0 s of understanding then sits ahead of the about 1.3 s rerank.
  - Proposed: call understanding only when the question is vague, deictic, a follow-up, or routed (account/navigate), whatever the lecture context.
