# Autonomous Observability Intelligence Report

| | |
| :--- | :--- |
| **Playbook** | `overview` |
| **Time Range** | `2026-02-18 22:00:00 to 2026-02-25 22:00:00` |
| **Datastore ID** | `logging` |
| **Table ID** | `agent_events_demo` |
| **Generated** | `2026-02-25 21:59:12 UTC` |
| **Agent Version** | `0.0.1` |

---

## Executive Summary

This report provides an overview of the autonomous agent system's performance from 2026-02-18 22:00:00 to 2026-02-25 22:00:00.

Overall, the system is experiencing significant performance and reliability challenges. The **knowledge_qa_supervisor** root agent shows a **🔴 P95.5 Latency Exceeded** status and a **🔴 Error Rate Exceeded** status, indicating severe user-facing issues. Several sub-agents, including `adk_documentation_agent`, `ai_observability_agent`, `config_test_agent_wrong_candidate_count_config`, `config_test_agent_wrong_max_output_tokens_count_config`, and `unreliable_tool_agent`, are exhibiting high error rates. `config_test_agent_wrong_max_output_tokens_count_config` stands out with a **100% error rate**. High latencies are prevalent across many agents, notably `bigquery_data_agent` with the highest average latency.

Key findings indicate that "Agent span PENDING for > 5 minutes (Timed Out)" is a recurring error message, suggesting widespread timeout issues affecting multiple agents and the overall system. Several LLM models, particularly `gemini-2.5-pro` and `gemini-3-pro-preview`, also show elevated error rates, further contributing to the system's instability. The `flaky_tool_simulation` tool is also contributing to errors.

Performance bottlenecks are primarily driven by specific LLM invocations and agents generating large response sizes or simulating slow actions, as evidenced by the root cause analyses of the slowest queries.

---

## Performance

This section provides a high-level scorecard for End to End, Sub Agent, Tool, and LLM levels, assessing compliance against defined Service Level Objectives (SLOs).

---

### End to End

This shows user-facing performance from start to end of an invocation, which is critical for user satisfaction.

| Name | Requests | % | Mean (s) | P95.5 (s) | Target (s) | Status | Err % | Target (%) | Status | Input Tok (Avg/P95) | Output Tok (Avg/P95) | Thought Tok (Avg/P95) | Tokens Consumed (Avg/P95) | Overall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| knowledge_qa_supervisor | 249 | 100.0 | 25.821 | 78.926 | 10.000 | 🔴 | 20.48 | 5.0 | 🔴 | 6390/16331 | 107/675 | 362/1416 | 6875/16606 | 🔴 |

<br>
<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#ef4444", "pie2": "#22c55e" } } }%%
pie title Latency Status (Root Agents)
    "knowledge_qa_supervisor (Exceeded)" : 78.926
    "knowledge_qa_supervisor (OK)" : 0.0
</code></pre>


<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#ef4444", "pie2": "#22c55e" } } }%%
pie title Error Status (Root Agents)
    "knowledge_qa_supervisor (Exceeded)" : 20.48
    "knowledge_qa_supervisor (OK)" : 0.0
</code></pre>


---

### Agent Level

This section details the performance of internal delegate agents called by the root agent. Several agents are exceeding latency targets and exhibiting high error rates. Specifically, `config_test_agent_wrong_max_output_tokens_count_config` has a 100% error rate, and `adk_documentation_agent`, `ai_observability_agent`, and `unreliable_tool_agent` also show significant error rates.

| Name | Requests | % | Mean (s) | P95.5 (s) | Target (s) | Status | Err % | Target (%) | Status | Input Tok (Avg/P95) | Output Tok (Avg/P95) | Thought Tok (Avg/P95) | Tokens Consumed (Avg/P95) | Overall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| adk_documentation_agent | 43 | 6.77 | 24.718 | 46.225 | 8.000 | 🔴 | 41.86 | 5.0 | 🔴 | 953/1480 | 614/1263 | 1291/2170 | 3189/5366 | 🔴 |
| ai_observability_agent | 64 | 10.06 | 22.892 | 40.651 | 8.000 | 🔴 | 26.56 | 5.0 | 🔴 | 359/803 | 586/1042 | 826/1838 | 1741/2896 | 🔴 |
| bigquery_data_agent | 48 | 7.55 | 25.497 | 73.714 | 8.000 | 🔴 | 2.08 | 5.0 | 🟢 | 24429/105502 | 43/101 | 330/1272 | 24802/105636 | 🔴 |
| config_test_agent_high_temp | 8 | 1.26 | 8.736 | 13.593 | 8.000 | 🔴 | 0.00 | 5.0 | 🟢 | 1166/1182 | 47/82 | 286/442 | 1499/1620 | 🔴 |
| config_test_agent_wrong_candidate_count_config | 10 | 1.57 | 11.887 | 38.328 | 8.000 | 🔴 | 10.00 | 5.0 | 🔴 | 1602/4789 | 352/3185 | 1362/5625 | 2862/9390 | 🔴 |
| config_test_agent_wrong_max_output_tokens_count_config | 10 | 1.57 | N/A | N/A | 8.000 | 🔴 | 100.00 | 5.0 | 🔴 | -/- | -/- | -/- | -/- | 🔴 |
| google_search_agent | 35 | 5.50 | 13.938 | 34.549 | 8.000 | 🔴 | 0.00 | 5.0 | 🟢 | 798/4143 | 582/1291 | 445/1646 | 1919/5916 | 🔴 |
| lookup_worker_1 | 26 | 4.09 | 15.291 | 30.677 | 8.000 | 🔴 | 3.85 | 5.0 | 🟢 | 263/699 | 34/61 | 233/745 | 516/1399 | 🔴 |
| lookup_worker_2 | 26 | 4.09 | 14.481 | 24.341 | 8.000 | 🔴 | 3.85 | 5.0 | 🟢 | 318/478 | 32/54 | 284/642 | 627/2427 | 🔴 |
| lookup_worker_3 | 27 | 4.25 | 17.231 | 26.397 | 8.000 | 🔴 | 3.70 | 5.0 | 🟢 | 617/1041 | 35/54 | 385/743 | 1013/9470 | 🔴 |
| parallel_db_lookup | 26 | 4.09 | 22.237 | 37.641 | 8.000 | 🔴 | 3.85 | 5.0 | 🟢 | -/- | -/- | -/- | -/- | 🔴 |
| unreliable_tool_agent | 24 | 3.78 | 18.461 | 93.167 | 8.000 | 🔴 | 29.17 | 5.0 | 🔴 | 2585/7646 | 18/43 | 234/562 | 2798/7775 | 🔴 |

<br>
<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#ef4444", "pie2": "#ef4444", "pie3": "#ef4444", "pie4": "#ef4444", "pie5": "#ef4444", "pie6": "#ef4444", "pie7": "#ef4444", "pie8": "#ef4444", "pie9": "#ef4444", "pie10": "#ef4444", "pie11": "#ef4444", "pie12": "#ef4444" } } }%%
pie title Sub Agent Latency Status (P95.5)
    "adk_documentation_agent (Exceeded)" : 46.225
    "ai_observability_agent (Exceeded)" : 40.651
    "bigquery_data_agent (Exceeded)" : 73.714
    "config_test_agent_high_temp (Exceeded)" : 13.593
    "config_test_agent_wrong_candidate_count_config (Exceeded)" : 38.328
    "config_test_agent_wrong_max_output_tokens_count_config (Exceeded)" : 0.0
    "google_search_agent (Exceeded)" : 34.549
    "lookup_worker_1 (Exceeded)" : 30.677
    "lookup_worker_2 (Exceeded)" : 24.341
    "lookup_worker_3 (Exceeded)" : 26.397
    "parallel_db_lookup (Exceeded)" : 37.641
    "unreliable_tool_agent (Exceeded)" : 93.167
</code></pre>


<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#ef4444", "pie2": "#ef4444", "pie3": "#22c55e", "pie4": "#22c55e", "pie5": "#ef4444", "pie6": "#ef4444", "pie7": "#22c55e", "pie8": "#22c55e", "pie9": "#22c55e", "pie10": "#22c55e", "pie11": "#22c55e", "pie12": "#ef4444" } } }%%
pie title Sub Agent Error Status (5.0%)
    "adk_documentation_agent (Exceeded)" : 41.86
    "ai_observability_agent (Exceeded)" : 26.56
    "bigquery_data_agent (OK)" : 2.08
    "config_test_agent_high_temp (OK)" : 0.0
    "config_test_agent_wrong_candidate_count_config (Exceeded)" : 10.0
    "config_test_agent_wrong_max_output_tokens_count_config (Exceeded)" : 100.0
    "google_search_agent (OK)" : 0.0
    "lookup_worker_1 (OK)" : 3.85
    "lookup_worker_2 (OK)" : 3.85
    "lookup_worker_3 (OK)" : 3.7
    "parallel_db_lookup (OK)" : 3.85
    "unreliable_tool_agent (Exceeded)" : 29.17
</code></pre>


---

### Tool Level

This section breaks down the performance of each tool called by agents. The `flaky_tool_simulation` tool is a significant concern, exhibiting a 25% error rate. The `simulated_db_lookup` tool, while having no errors, still shows a P95.5 latency exceeding the target.

| Name | Requests | % | Mean (s) | P95.5 (s) | Target (s) | Status | Err % | Target (%) | Status | Overall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| complex_calculation | 10 | 4.35 | 1.967 | 2.739 | 3.000 | 🟢 | 0.00 | 5.0 | 🟢 | 🟢 |
| execute_sql | 53 | 23.04 | 0.888 | 1.511 | 3.000 | 🟢 | 0.00 | 5.0 | 🟢 | 🟢 |
| flaky_tool_simulation | 16 | 6.96 | 3.360 | 6.306 | 3.000 | 🔴 | 25.00 | 5.0 | 🔴 | 🔴 |
| get_table_info | 31 | 13.48 | 0.284 | 0.420 | 3.000 | 🟢 | 0.00 | 5.0 | 🟢 | 🟢 |
| list_dataset_ids | 6 | 2.61 | 0.329 | 0.456 | 3.000 | 🟢 | 0.00 | 5.0 | 🟢 | 🟢 |
| list_table_ids | 27 | 11.74 | 0.351 | 0.492 | 3.000 | 🟢 | 0.00 | 5.0 | 🟢 | 🟢 |
| simulated_db_lookup | 160 | 69.57 | 1.023 | 4.220 | 3.000 | 🔴 | 0.00 | 5.0 | 🟢 | 🔴 |

<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#22c55e", "pie2": "#22c55e", "pie3": "#ef4444", "pie4": "#22c55e", "pie5": "#22c55e", "pie6": "#22c55e", "pie7": "#ef4444" } } }%%
pie title Tools Latency Status (P95.5)
    "complex_calculation (OK)" : 2.739
    "execute_sql (OK)" : 1.511
    "flaky_tool_simulation (Exceeded)" : 6.306
    "get_table_info (OK)" : 0.420
    "list_dataset_ids (OK)" : 0.456
    "list_table_ids (OK)" : 0.492
    "simulated_db_lookup (Exceeded)" : 4.220
</code></pre>


<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#22c55e", "pie2": "#22c55e", "pie3": "#ef4444", "pie4": "#22c55e", "pie5": "#22c55e", "pie6": "#22c55e", "pie7": "#22c55e" } } }%%
pie title Tools Error Status (5.0%)
    "complex_calculation (OK)" : 0.0
    "execute_sql (OK)" : 0.0
    "flaky_tool_simulation (Exceeded)" : 25.0
    "get_table_info (OK)" : 0.0
    "list_dataset_ids (OK)" : 0.0
    "list_table_ids (OK)" : 0.0
    "simulated_db_lookup (OK)" : 0.0
</code></pre>


---

### Model Level

This section isolates valid LLM inference time from agent overhead and breaks down the performance of each LLM. All models are currently failing their P95.5 latency targets. `gemini-2.5-pro` and `gemini-3-pro-preview` also exceed the error rate target.

| Name | Requests | % | Mean (s) | P95.5 (s) | Target (s) | Status | Err % | Target (%) | Status | Input Tok (Avg/P95) | Output Tok (Avg/P95) | Thought Tok (Avg/P95) | Tokens Consumed (Avg/P95) | Overall |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| gemini-2.5-flash | 235 | 34.35 | 3.652 | 11.938 | 5.000 | 🔴 | 4.68 | 5.0 | 🟢 | 12317/105235 | 83/440 | 219/569 | 12640/105390 | 🔴 |
| gemini-2.5-pro | 234 | 34.20 | 8.498 | 22.389 | 5.000 | 🔴 | 7.69 | 5.0 | 🔴 | 4945/15772 | 88/776 | 336/1069 | 5421/15939 | 🔴 |
| gemini-3-pro-preview | 139 | 20.32 | 12.335 | 36.625 | 5.000 | 🔴 | 11.51 | 5.0 | 🔴 | 4130/13315 | 181/1039 | 643/1726 | 4953/13707 | 🔴 |
| gemini-3.1-pro-preview | 167 | 24.45 | 8.690 | 34.090 | 5.000 | 🔴 | 0.60 | 5.0 | 🟢 | 1949/13375 | 106/644 | 363/1630 | 2414/13731 | 🔴 |

<br>
<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#ef4444", "pie2": "#ef4444", "pie3": "#ef4444", "pie4": "#ef4444" } } }%%
pie title Model Latency Status (P95.5)
    "gemini-2.5-flash (Exceeded)" : 11.938
    "gemini-2.5-pro (Exceeded)" : 22.389
    "gemini-3-pro-preview (Exceeded)" : 36.625
    "gemini-3.1-pro-preview (Exceeded)" : 34.090
</code></pre>


<pre><code class="language-mermaid">%%{init: {"theme": "base", "themeVariables": { "pie1": "#22c55e", "pie2": "#ef4444", "pie3": "#ef4444", "pie4": "#22c55e" } } }%%
pie title Model Error Status (5.0%)
    "gemini-2.5-flash (OK)" : 4.68
    "gemini-2.5-pro (Exceeded)" : 7.69
    "gemini-3-pro-preview (Exceeded)" : 11.51
    "gemini-3.1-pro-preview (OK)" : 0.6
</code></pre>

---

## Agent Composition

### Distribution
| Name | Requests | % |
| :--- | :--- | :--- | 
| adk_documentation_agent | 43 | 6.77 | 
| ai_observability_agent | 64 | 10.06 | 
| bigquery_data_agent | 48 | 7.55 | 
| config_test_agent_high_temp | 8 | 1.26 |
| config_test_agent_wrong_candidate_count_config | 10 | 1.57 |
| config_test_agent_wrong_max_output_tokens_count_config | 10 | 1.57 | 
| google_search_agent | 35 | 5.50 |
| lookup_worker_1 | 26 | 4.09 | 
| lookup_worker_2 | 26 | 4.09 | 
| lookup_worker_3 | 27 | 4.25 |
| parallel_db_lookup | 26 | 4.09 |
| unreliable_tool_agent | 24 | 3.78 |

### Model Traffic

This table shows the volume of requests routed to each model per agent.

| Agent Name | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| adk_documentation_agent | 11 (25%) | 16 (37%) | 9 (21%) | 7 (16%) |
| ai_observability_agent | 2 (3%) | 25 (39%) | 28 (44%) | 8 (13%) |
| bigquery_data_agent | 27 (56%) | 10 (21%) | 9 (19%) | 2 (4%) |
| config_test_agent_high_temp | - | - | - | 8 (100%) |
| config_test_agent_wrong_candidate_count_config | 7 (70%) | 1 (10%) | 2 (20%) | - |
| config_test_agent_wrong_max_output_tokens_count_config | 9 (90%) | - | - | 1 (10%) |
| google_search_agent | 15 (43%) | 9 (26%) | 8 (23%) | 3 (9%) |
| lookup_worker_1 | 3 (12%) | 7 (27%) | 1 (4%) | 15 (58%) |
| lookup_worker_2 | 2 (8%) | 8 (31%) | 1 (4%) | 15 (58%) |
| lookup_worker_3 | 3 (11%) | 7 (26%) | 1 (4%) | 15 (56%) |
| parallel_db_lookup | - | - | - | - |
| unreliable_tool_agent | 7 (29%) | 17 (71%) | - | - |

---

### Model Performance

This table compares how specific agents perform when running on different models, highlighting optimal model choices.

| Agent Name | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| adk_documentation_agent | 21.558s (18.18%) 🔴 |  | 51.512s (0%) 🔴 | 38.374s (0%) 🔴 |
| ai_observability_agent | 5.862s (0%) 🔴 | 46.519s (8.0%) 🔴 | 37.774s (50.0%) 🔴 | 40.651s (0%) 🔴 |
| bigquery_data_agent | 26.060s (3.7%) 🔴 | 73.714s (0%) 🔴 | 120.422s (0%) 🔴 | 84.880s (0%) 🔴 |
| config_test_agent_high_temp | | | | 13.593s (0%) 🔴 |
| config_test_agent_wrong_candidate_count_config | 7.004s (0%) 🟢 | 38.328s (0%) 🔴 | 24.945s (50.0%) 🔴 | |
| config_test_agent_wrong_max_output_tokens_count_config |  | | | |
| google_search_agent | 13.630s (0%) 🔴 | 28.381s (0%) 🔴 | 21.610s (0%) 🔴 | 37.116s (0%) 🔴 |
| lookup_worker_1 | 12.924s (0%) 🔴 | 37.640s (0%) 🔴 |  | 30.677s (0%) 🔴 |
| lookup_worker_2 | 29.304s (0%) 🔴 | 24.341s (0%) 🔴 |  | 18.785s (0%) 🔴 |
| lookup_worker_3 | 12.050s (0%) 🔴 | 116.662s (0%) 🔴 |  | 16.358s (0%) 🔴 |
| parallel_db_lookup | | | | |
| unreliable_tool_agent | 13.268s (14.29%) 🔴 | 93.167s (35.29%) 🔴 | | |

---
<br>

### Token Statistics

**adk_documentation_agent**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 311 | N/A | 957 | 564 |
| Median Output Tokens | 70 | N/A | 1039 | 550 |
| Min Output Tokens | 40 | N/A | 463 | 511 |
| Max Output Tokens | 908 | N/A | 1280 | 644 |
| Latency vs Output Corr. | -0.900 | N/A | -0.748 | -0.939 |
| Latency vs Output+Thinking Corr. | 0.848 | N/A | 0.908 | -0.472 |
| Correlation Strength | 🟧 **Strong** | N/A | 🟧 **Strong** | 🟧 **Strong** |

<br>

**ai_observability_agent**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 164 | 356 | 665 | 639 |
| Median Output Tokens | 101 | 453 | 843 | 648 |
| Min Output Tokens | 101 | 38 | 266 | 583 |
| Max Output Tokens | 227 | 578 | 1186 | 675 |
| Latency vs Output Corr. | 1.000 | 0.257 | 0.124 | -0.620 |
| Latency vs Output+Thinking Corr. | 1.000 | 0.939 | 0.782 | -0.208 |
| Correlation Strength | 🟧 **Strong** | 🟧 **Strong** | 🟧 **Strong** | Weak |

<br>

**bigquery_data_agent**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 123 | 127 | 188 | 381 |
| Median Output Tokens | 121 | 148 | 164 | 266 |
| Min Output Tokens | 14 | 21 | 18 | 266 |
| Max Output Tokens | 346 | 226 | 543 | 495 |
| Latency vs Output Corr. | -0.246 | -0.625 | -0.815 | -1.000 |
| Latency vs Output+Thinking Corr. | 0.545 | 0.460 | 0.925 | 1.000 |
| Correlation Strength | Moderate | Moderate | 🟧 **Strong** | 🟧 **Strong** |

<br>

**config_test_agent_high_temp**
| Metric | gemini-3.1-pro-preview |
| :--- | :--- |
| Mean Output Tokens | 58 |
| Median Output Tokens | 56 |
| Min Output Tokens | 33 |
| Max Output Tokens | 82 |
| Latency vs Output Corr. | -0.671 |
| Latency vs Output+Thinking Corr. | -0.697 |
| Correlation Strength | Moderate |

<br>

**config_test_agent_wrong_candidate_count_config**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview |
| :--- | :--- | :--- | :--- |
| Mean Output Tokens | 252 | 3961 | 302 |
| Median Output Tokens | 195 | 3961 | 85 |
| Min Output Tokens | 80 | 3961 | 85 |
| Max Output Tokens | 470 | 3961 | 520 |
| Latency vs Output Corr. | -0.399 | N/A | N/A |
| Latency vs Output+Thinking Corr. | -0.242 | N/A | N/A |
| Correlation Strength | Weak | N/A | N/A |

<br>

**config_test_agent_wrong_max_output_tokens_count_config**
| Metric | gemini-2.5-flash | gemini-3.1-pro-preview |
| :--- | :--- | :--- |
| Mean Output Tokens | N/A | N/A |
| Median Output Tokens | N/A | N/A |
| Min Output Tokens | N/A | N/A |
| Max Output Tokens | N/A | N/A |
| Latency vs Output Corr. | N/A | N/A |
| Latency vs Output+Thinking Corr. | N/A | N/A |
| Correlation Strength | N/A | N/A |

<br>

**google_search_agent**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 573 | 951 | 127 | 734 |
| Median Output Tokens | 145 | 1040 | 51 | 732 |
| Min Output Tokens | 28 | 122 | 48 | 535 |
| Max Output Tokens | 1425 | 1256 | 650 | 936 |
| Latency vs Output Corr. | 0.814 | 0.174 | -0.863 | -0.980 |
| Latency vs Output+Thinking Corr. | 0.972 | 0.752 | 0.904 | 0.916 |
| Correlation Strength | 🟧 **Strong** | 🟧 **Strong** | 🟧 **Strong** | 🟧 **Strong** |

<br>

**lookup_worker_1**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 70 | 37 | 39 | 96 |
| Median Output Tokens | 57 | 43 | 39 | 97 |
| Min Output Tokens | 55 | 19 | 39 | 65 |
| Max Output Tokens | 97 | 46 | 39 | 111 |
| Latency vs Output Corr. | -0.944 | -0.913 | N/A | -0.741 |
| Latency vs Output+Thinking Corr. | 0.939 | 0.157 | N/A | 0.542 |
| Correlation Strength | 🟧 **Strong** | 🟧 **Strong** | N/A | 🟧 **Strong** |

<br>

**lookup_worker_2**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 68 | 52 | 24 | 94 |
| Median Output Tokens | 65 | 46 | 24 | 94 |
| Min Output Tokens | 65 | 43 | 24 | 67 |
| Max Output Tokens | 70 | 64 | 24 | 108 |
| Latency vs Output Corr. | -1.000 | -0.258 | N/A | -0.783 |
| Latency vs Output+Thinking Corr. | -1.000 | -0.595 | N/A | 0.327 |
| Correlation Strength | 🟧 **Strong** | Moderate | N/A | 🟧 **Strong** |

<br>

**lookup_worker_3**
| Metric | gemini-2.5-flash | gemini-2.5-pro | gemini-3-pro-preview | gemini-3.1-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| Mean Output Tokens | 61 | 53 | 39 | 96 |
| Median Output Tokens | 59 | 43 | 39 | 100 |
| Min Output Tokens | 56 | 40 | 39 | 68 |
| Max Output Tokens | 67 | 79 | 39 | 107 |
| Latency vs Output Corr. | -0.539 | -0.995 | N/A | -0.393 |
| Latency vs Output+Thinking Corr. | -0.615 | 0.319 | N/A | 0.159 |
| Correlation Strength | Moderate | 🟧 **Strong** | N/A | Weak |

<br>

**unreliable_tool_agent**
| Metric | gemini-2.5-flash | gemini-2.5-pro |
| :--- | :--- | :--- |
| Mean Output Tokens | 35 | 23 |
| Median Output Tokens | 37 | 14 |
| Min Output Tokens | 12 | 11 |
| Max Output Tokens | 44 | 55 |
| Latency vs Output Corr. | 0.399 | -0.084 |
| Latency vs Output+Thinking Corr. | -0.258 | 0.215 |
| Correlation Strength | Weak | Weak |

## Model Composition

### Distribution

Here will be table and chart showing % and number of requests routed to each model corresponingly.
TODO


### Model Performance

Overall token usage is varied across models. `gemini-2.5-flash` processes the highest average input tokens, possibly due to longer prompts. Output and thought token correlations with latency indicate that for `gemini-3-pro-preview` and `gemini-3.1-pro-preview`, larger output/thought token counts are strongly associated with increased latency. `gemini-2.5-flash` also shows a strong correlation between latency and output/thought tokens.

| Metric                         | gemini-3-pro-preview | gemini-3.1-pro-preview | gemini-2.5-pro | gemini-2.5-flash |
|:-------------------------------| :--- | :--- | :--- | :--- |
| Total Requests                 | 139 | 167 | 234 | 235 |
| Mean Latency (s)               | 116| 8.569 | 8.256 | 3 |
| Std Deviation (s)              | 101 | 8.697 | 15.564 | 3 |
| Median Latency (s)             | 72 | 5.000 | 4.000 | 2 |
| P95 Latency (s)                | 35 | 33.000 | 2.000 | 99.000 |
| P99 Latency (s)                | 46 | 38.000 | 8.000 | 20.000 |
| Max Latency (s)                | 51 | 40.000 | 17.000 | 27 |
| Outliers 2 STD Count (Percent) | 10 (7.2%) | 16 (9.6%) | 5 (2.1%) | 11 (4.7%) |
| Outliers 3 STD Count (Percent) | 2 (1.4%) | 4 (2.4%) | 4 (1.7%) | 6 (2.6%) |

### Token Statistics
| Metric | gemini-2.5-pro | gemini-2.5-flash | gemini-3.1-pro-preview | gemini-3-pro-preview |
| :--- | :--- | :--- | :--- | :--- |
| **Mean Output Tokens** | 88 | 83 | 106 | 181 |
| **Median Output Tokens** | 14 | 25 | 43 | 24 |
| **Min Output Tokens** | 6 | 12 | 10 | 17 |
| **Max Output Tokens** | 3,185 | 1,425 | 936 | 1,280 |
| **Latency vs Output Corr.** | 0.264 | 0.637 | 0.931 | 0.887 |
| **Latency vs Output+Thinking Corr.** | 0.461 | 0.905 | 0.966 | 0.859 |
| **Correlation Strength** | Weak | Moderate | Very Strong | Strong |

### Requests Distribution

**gemini-3-pro-preview**

| Category | Count | Percentage |
| :--- | :--- | :--- |
| Very Fast (< 1s) | 0 | 0.0% |
| Fast (1-2s) | 1 | 0.7% |
| Medium (2-3s) | 1 | 0.7% |
| Slow (3-5s) | 26 | 18.7% |
| Very Slow (5-8s) | 48 | 34.5% |
| Outliers (8s+) | 63 | 45.3% |

<pre><code class="language-mermaid">xychart-beta
        title "Latency Distribution: gemini-3-pro-preview"
        x-axis ["0-1s", "1-2s", "2-3s", "3-5s", "5-8s", "8s+"]
        y-axis "Count" 0 --> 63
        bar [0, 1, 1, 26, 48, 63]
</code></pre>


**gemini-2.5-pro**

| Category | Count | Percentage |
| :--- | :--- | :--- |
| Very Fast (< 1s) | 0 | 0.0% |
| Fast (1-2s) | 0 | 0.0% |
| Medium (2-3s) | 42 | 17.9% |
| Slow (3-5s) | 75 | 32.1% |
| Very Slow (5-8s) | 64 | 27.4% |
| Outliers (8s+) | 53 | 22.6% |

<pre><code class="language-mermaid">xychart-beta
        title "Latency Distribution: gemini-2.5-pro"
        x-axis ["0-1s", "1-2s", "2-3s", "3-5s", "5-8s", "8s+"]
        y-axis "Count" 0 --> 75
        bar [0, 0, 42, 75, 64, 53]
</code></pre>


**gemini-2.5-flash**

| Category | Count | Percentage |
| :--- | :--- | :--- |
| Very Fast (< 1s) | 2 | 0.9% |
| Fast (1-2s) | 56 | 23.8% |
| Medium (2-3s) | 89 | 37.9% |
| Slow (3-5s) | 54 | 23.0% |
| Very Slow (5-8s) | 18 | 7.7% |
| Outliers (8s+) | 16 | 6.8% |

<pre><code class="language-mermaid">xychart-beta
        title "Latency Distribution: gemini-2.5-flash"
        x-axis ["0-1s", "1-2s", "2-3s", "3-5s", "5-8s", "8s+"]
        y-axis "Count" 0 --> 89
        bar [2, 56, 89, 54, 18, 16]
</code></pre>


**gemini-3.1-pro-preview**

| Category | Count | Percentage |
| :--- | :--- | :--- |
| Very Fast (< 1s) | 1 | 0.6% |
| Fast (1-2s) | 0 | 0.0% |
| Medium (2-3s) | 3 | 1.8% |
| Slow (3-5s) | 58 | 34.7% |
| Very Slow (5-8s) | 72 | 43.1% |
| Outliers (8s+) | 33 | 19.8% |

<pre><code class="language-mermaid">xychart-beta
        title "Latency Distribution: gemini-3.1-pro-preview"
        x-axis ["0-1s", "1-2s", "2-3s", "3-5s", "5-8s", "8s+"]
        y-axis "Count" 0 --> 72
        bar [1, 0, 3, 58, 72, 33]
</code></pre>


---

## Root Cause Insights

*   **🔴 Red Flag:** `config_test_agent_wrong_max_output_tokens_count_config` has a **100% error rate**. This is a critical configuration issue. The errors are primarily due to "Agent span PENDING for > 5 minutes (Timed Out)".
*   **🔴 Red Flag:** `adk_documentation_agent` has a **41.86% error rate**, and `ai_observability_agent` has a **26.56% error rate**. These agents are also frequently timing out.
*   **🔴 Red Flag:** `unreliable_tool_agent` has a **29.17% error rate**, with timeouts and quota issues reported for `flaky_tool_simulation`.
*   **🔴 Red Flag:** `knowledge_qa_supervisor` is experiencing significant timeouts, leading to PENDING statuses for agent spans, and ultimately, invocation errors.
*   **Trace Analysis for Slowest LLM Queries:**
    *   **Span ID:** `5f1efe0671a78fb7` in trace `844d33bab4c069bf005ece6b9c112f12` (`ai_observability_agent`, 172.517s): The long duration was due to a substantial amount of context included in the prompt (803 prompt tokens, 1438 total tokens), built up from many tool calls and worker results.
    *   **Span ID:** `b359b5b4a187f790` in trace `7ea524f3af9eb39fb531333ceb19b7cd` (`lookup_worker_3`, 98.609s): High latency caused by a very large LLM output (`thoughts_token_count` of 9316 tokens) despite a small prompt. The entire delay occurred before the first token was received.
    *   **Span ID:** `4d9f939b30b330d8` in trace `2cf2baefdda0e144915410461a4feaba` (`unreliable_tool_agent`, 89.067s): This delay is explicitly due to the `unreliable_tool_agent` simulating a slow tool response, as instructed by its system prompt ("Simulate a flaky action" via `flaky_tool_simulation` tool).
*   **Trace Analysis for Slowest End-to-End Invocations:**
    *   **Invocation ID:** `e-eba986bf-08c3-419c-a636-7a4ac4264139` in trace `844d33bab4c069bf005ece6b9c112f12` (`knowledge_qa_supervisor`, 176.677s): The high latency is likely due to delays within the agent's internal operations or external API calls, despite a short prompt and successful completion.
    *   **Invocation ID:** `e-5054b4e8-e7f7-4c7e-a8a0-a9e2ad2aa459` in trace `c9f325d3ea9bddccb75a164ffc5fd14a` (`knowledge_qa_supervisor`, 127.054s): The long duration is attributed to external API calls to retrieve BigQuery errors and search online for solutions.
    *   **Invocation ID:** `e-00a22c0c-da69-413c-8ff9-778265fb6933` in trace `7ea524f3af9eb39fb531333ceb19b7cd` (`knowledge_qa_supervisor`, 122.414s): The request successfully completed but had a lengthy duration, indicating a performance bottleneck.

---

## System Bottlenecks & Impact
### Top Bottlenecks

| Rank | Timestamp | Type | Latency (s) | Name | Details (Trunk) | RCA | Session ID | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24T17:48:56.790000 | agent | 176.677 | knowledge_qa_supervisor | [LARGE PAYLOAD: 1325 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | The request "Explain the benefits of AI agent tracing" for the `knowledge_qa_supervisor` agent took 176677 ms to complete. The prompt was short and the status was "OK", with no error message. Therefore, the high latency is likely due to delays within the agent's internal operations or external API calls not reflected in the log. | `0211bbc5-c4e0-4f44-9c32-7515b43ae0b0` | [`844d33bab4c069bf005ece6b9c112f12`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12?project=agent-operations-ek-01) | [`4b0c64e78f42a161`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12;spanId=4b0c64e78f42a161?project=agent-operations-ek-01) |
| 2 | 2026-02-24T17:49:00.938000 | agent | 172.527 | ai_observability_agent | "You are an expert assistant specializing in AI Observability. Use the Vertex AI Search datastore at projects/agent-operations-ek-01/locations/global/collections/default_collection/dataStores/adk-web-docs via the 'search_web_data_tool' to extract information to answer questions. Always search first, and then formulate a helpful, professional response based on what you find." | N/A | `0211bbc5-c4e0-4f44-9c32-7515b43ae0b0` | [`844d33bab4c069bf005ece6b9c112f12`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12?project=agent-operations-ek-01) | [`2595d3f89c40d5a6`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12;spanId=2595d3f89c40d5a6?project=agent-operations-ek-01) |
| 3 | 2026-02-24T08:15:52.301000 | agent | 127.054 | knowledge_qa_supervisor | [LARGE PAYLOAD: 1325 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | The `knowledge_qa_supervisor` agent took 127054 ms (over 2 minutes) to complete. The agent's stated content indicates it retrieves BigQuery errors and then searches for solutions online. This suggests the long duration could be caused by delays from external API calls to retrieve data from BigQuery or search the internet. | `5be5fd3f-f0fe-4533-8348-956e96f6a0bf` | [`c9f325d3ea9bddccb75a164ffc5fd14a`](https://console.cloud.google.com/traces/explorer;traceId=c9f325d3ea9bddccb75a164ffc5fd14a?project=agent-operations-ek-01) | [`2cc2b504bd3c8107`](https://console.cloud.google.com/traces/explorer;traceId=c9f325d3ea9bddccb75a164ffc5fd14a;spanId=2cc2b504bd3c8107?project=agent-operations-ek-01) |
| 4 | 2026-02-24T17:46:53.873000 | agent | 122.413 | knowledge_qa_supervisor | [LARGE PAYLOAD: 1325 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | The request for "item_1, large_record_F" by the agent `knowledge_qa_supervisor` took 122414 ms (over 2 minutes). The status is OK, so it completed successfully. The lengthy duration is the primary factor. | `0211bbc5-c4e0-4f44-9c32-7515b43ae0b0` | [`7ea524f3af9eb39fb531333ceb19b7cd`](https://console.cloud.google.com/traces/explorer;traceId=7ea524f3af9eb39fb531333ceb19b7cd?project=agent-operations-ek-01) | [`2d0d495fe83d1eee`](https://console.cloud.google.com/traces/explorer;traceId=7ea524f3af9eb39fb531333ceb19b7cd;spanId=2d0d495fe83d1eee?project=agent-operations-ek-01) |
| 5 | 2026-02-24T08:15:58.933000 | agent | 120.422 | bigquery_data_agent | "You are a data analyst. Use the BigQuery tools to answer questions about data in `agent-operations-ek-01.logging`. The main table for events is `agent_events_demo`. Use `list_tables` if needed." | N/A | `5be5fd3f-f0fe-4533-8348-956e96f6a0bf` | [`c9f325d3ea9bddccb75a164ffc5fd14a`](https://console.cloud.google.com/traces/explorer;traceId=c9f325d3ea9bddccb75a164ffc5fd14a?project=agent-operations-ek-01) | [`edf19dd3a8b01b56`](https://console.cloud.google.com/traces/explorer;traceId=c9f325d3ea9bddccb75a164ffc5fd14a;spanId=edf19dd3a8b01b56?project=agent-operations-ek-01) |

---

### LLM Bottlenecks

| Rank | Timestamp | LLM (s) | TTFT (s) | Model | LLM Status | Input | Output | Thought | Total Tokens | Impact % | RCA | Agent | Agent (s) | Agent Status | Root Agent | E2E (s) | Root Status | User Message | Session ID | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24T17:49:00.941000+00:00 | 172.517 | 172.517 | gemini-2.5-pro | OK 🟢 | 803 | 0 | 257 | 1438 | 97.65 | The `ai_observability_agent` experienced a long `duration_ms` (172517), matching the `time_to_first_token_ms`. The prompt included a context section built up from many tool calls and results of various workers. The `prompt_token_count` was 803, and the `total_token_count` was 1438, indicating a substantial amount of context was included in the prompt. The large amount of context might have contributed to the duration. | ai_observability_agent | 172.527 | OK 🟢 | knowledge_qa_supervisor | 176.677 | OK 🟢 | Explain the benefits of AI agent tracing. | `0211bbc5-c4e0-4f44-9c32-7515b43ae0b0` | [`844d33bab4c069bf005ece6b9c112f12`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12?project=agent-operations-ek-01) | [`5f1efe0671a78fb7`](https://console.cloud.google.com/traces/explorer;traceId=844d33bab4c069bf005ece6b9c112f12;spanId=5f1efe0671a78fb7?project=agent-operations-ek-01) |
| 2 | 2026-02-24T17:46:59.625000+00:00 | 98.609 | 98.609 | gemini-2.5-pro | OK 🟢 | 140 | 14 | 9316 | 9470 | 80.55 | The `lookup_worker_3` agent experienced a high latency of 98609ms. The `time_to_first_token_ms` matches the total `duration_ms`, indicating the entire delay occurred before the first token was received. The prompt was relatively small at 140 tokens, but the LLM output `thoughts_token_count` was very large at 9316 tokens, resulting in a total `token_count` of 9470. The large response size likely contributed significantly to the latency. | lookup_worker_3 | 116.662 | OK 🟢 | knowledge_qa_supervisor | 122.414 | OK 🟢 | Get item_1, large_record_F. | `0211bbc5-c4e0-4f44-9c32-7515b43ae0b0` | [`7ea524f3af9eb39fb531333ceb19b7cd`](https://console.cloud.google.com/traces/explorer;traceId=7ea524f3af9eb39fb531333ceb19b7cd?project=agent-operations-ek-01) | [`b359b5b4a187f790`](https://console.cloud.google.com/traces/explorer;traceId=7ea524f3af9eb39fb531333ceb19b7cd;spanId=b359b5b4a187f790?project=agent-operations-ek-01) |
| 3 | 2026-02-24T18:17:54.853000+00:00 | 89.067 | 89.067 | gemini-2.5-pro | OK 🟢 | 1194 | 11 | 128 | 1333 | 92.50 | The `duration_ms` was 89067 (89 seconds). The `time_to_first_token_ms` also aligns with this, indicating the total time to get the first output. The agent, `unreliable_tool_agent`, was instructed to "Simulate a flaky action". The system prompt indicates the agent uses a simulated tool that is "potentially slow". Therefore, the delay is due to the agent simulating a slow tool response as requested by the prompt. | unreliable_tool_agent | 93.167 | OK 🟢 | knowledge_qa_supervisor | 96.284 | OK 🟢 | Simulate a flaky action for 'test case 1'. | `a90aa3a5-4cda-4496-bae5-568b438ed53a` | [`2cf2baefdda0e144915410461a4feaba`](https://console.cloud.google.com/traces/explorer;traceId=2cf2baefdda0e144915410461a4feaba?project=agent-operations-ek-01) | [`4d9f939b30b330d8`](https://console.cloud.google.com/traces/explorer;traceId=2cf2baefdda0e144915410461a4feaba;spanId=4d9f939b30b330d8?project=agent-operations-ek-01) |
| 4 | 2026-02-24T18:11:33.496000+00:00 | 68.323 | 68.323 | gemini-2.5-pro | OK 🟢 | 1401 | 13 | 460 | 1874 | 64.47 | N/A | knowledge_qa_supervisor | 105.970 | OK 🟢 | knowledge_qa_supervisor | 105.971 | OK 🟢 | Get item_1, large_record_F. | `32bada90-68fc-41b8-bf26-25dda1f25587` | [`da2332ca93b91bac6cf7afc54a31c848`](https://console.cloud.google.com/traces/explorer;traceId=da2332ca93b91bac6cf7afc54a31c848?project=agent-operations-ek-01) | [`f44babdce1635b31`](https://console.cloud.google.com/traces/explorer;traceId=da2332ca93b91bac6cf7afc54a31c848;spanId=f44babdce1635b31?project=agent-operations-ek-01) |
| 5 | 2026-02-24T18:11:33.496000+00:00 | 68.323 | 68.323 | gemini-2.5-pro | OK 🟢 | 1401 | 13 | 460 | 1874 | 64.47 | N/A | knowledge_qa_supervisor | 105.970 | OK 🟢 | knowledge_qa_supervisor | 105.971 | OK 🟢 | Get item_1, large_record_F. | `32bada90-68fc-41b8-bf26-25dda1f25587` | [`da2332ca93b91bac6cf7afc54a31c848`](https://console.cloud.google.com/traces/explorer;traceId=da2332ca93b91bac6cf7afc54a31c848?project=agent-operations-ek-01) | [`f44babdce1635b31`](https://console.cloud.google.com/traces/explorer;traceId=da2332ca93b91bac6cf7afc54a31c848;spanId=f44babdce1635b31?project=agent-operations-ek-01) |

---

### Tool Bottlenecks

| Rank | Timestamp | Tool (s) | Tool Name | Tool Status | Tool Args | Impact % | Agent | Agent (s) | Agent Status | Root Agent | E2E (s) | Root Status | User Message | Session ID | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24T18:09:24.281000+00:00 | 9.416 | flaky_tool_simulation | ERROR 🔴 | {"query":"very_slow_topic"} | 0.00 | unreliable_tool_agent | 0.000 | ERROR 🔴 | knowledge_qa_supervisor | 0.000 | ERROR 🔴 | Try the unreliable tool with very_slow_topic input. | `9ec1a54f-52c9-4659-906e-15e7e0380fed` | [`bf46dbf39dc20547ec31b2e3ae73c6be`](https://console.cloud.google.com/traces/explorer;traceId=bf46dbf39dc20547ec31b2e3ae73c6be?project=agent-operations-ek-01) | [`8f579c4071f0b24a`](https://console.cloud.google.com/traces/explorer;traceId=bf46dbf39dc20547ec31b2e3ae73c6be;spanId=8f579c4071f0b24a?project=agent-operations-ek-01) |
| 2 | 2026-02-24T17:44:20.112000+00:00 | 6.306 | flaky_tool_simulation | OK 🟢 | {"query":"very_slow_topic"} | 41.86 | unreliable_tool_agent | 13.268 | OK 🟢 | knowledge_qa_supervisor | 15.064 | OK 🟢 | Try the unreliable tool with very_slow_topic input. | `6fbf143d-81aa-4463-b1db-57e25e979085` | [`81609a6be7bf2b1f6e170df45a76a266`](https://console.cloud.google.com/traces/explorer;traceId=81609a6be7bf2b1f6e170df45a76a266?project=agent-operations-ek-01) | [`1e738ab3bfbe0c05`](https://console.cloud.google.com/traces/explorer;traceId=81609a6be7bf2b1f6e170df45a76a266;spanId=1e738ab3bfbe0c05?project=agent-operations-ek-01) |
| 3 | 2026-02-24T18:08:47.351000+00:00 | 6.222 | flaky_tool_simulation | OK 🟢 | {"query":"very_slow_topic"} | 47.56 | unreliable_tool_agent | 10.159 | OK 🟢 | knowledge_qa_supervisor | 13.081 | OK 🟢 | Try the unreliable tool with very_slow_topic input. | `8a2023d6-8b63-4a7a-8855-d6ee7def251f` | [`3b8c10c1fd8f88b341a1d5966c706c07`](https://console.cloud.google.com/traces/explorer;traceId=3b8c10c1fd8f88b341a1d5966c706c07?project=agent-operations-ek-01) | [`dd451a6d489f21a6`](https://console.cloud.google.com/traces/explorer;traceId=3b8c10c1fd8f88b341a1d5966c706c07;spanId=dd451a6d489f21a6?project=agent-operations-ek-01) |
| 4 | 2026-02-24T18:17:57.819000+00:00 | 5.975 | flaky_tool_simulation | ERROR 🔴 | {"query":"Simulate a flaky action for 'test case 1'"} | 0.00 | unreliable_tool_agent | 0.000 | ERROR 🔴 | knowledge_qa_supervisor | 0.000 | ERROR 🔴 | Simulate a flaky action for 'test case 1'. | `7f22ec4f-15c2-45e3-9f2f-30950f9a82c3` | [`c1a31dc41240d3f36d968c9a340b4e78`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78?project=agent-operations-ek-01) | [`df8428b97374a906`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78;spanId=df8428b97374a906?project=agent-operations-ek-01) |
| 5 | 2026-02-24T18:17:57.819000+00:00 | 5.975 | flaky_tool_simulation | ERROR 🔴 | {"query":"Simulate a flaky action for 'test case 1'"} | 21.65 | unreliable_tool_agent | 0.000 | ERROR 🔴 | knowledge_qa_supervisor | 27.600 | OK 🟢 | Describe event logging in AI agents. | `7f22ec4f-15c2-45e3-9f2f-30950f9a82c3` | [`c1a31dc41240d3f36d968c9a340b4e78`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78?project=agent-operations-ek-01) | [`df8428b97374a906`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78;spanId=df8428b97374a906?project=agent-operations-ek-01) |

---

## Error Analysis
### Root Agent Errors

| Rank | Timestamp | Root Agent | Error Message | User Message | Trace ID | Invocation ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24 18:30:40.380000+00:00 | knowledge_qa_supervisor | Invocation PENDING for > 5 minutes (Timed Out) | Explain real-time monitoring for AI agents. | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | `e-6ce539c9-8cc1-4b0c-8ff1-45019ee3d958` |
| 2 | 2026-02-24 18:30:25.216000+00:00 | knowledge_qa_supervisor | Invocation PENDING for > 5 minutes (Timed Out) | What are the key metrics for AI agent health? | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | `e-d55b11c7-ad1b-487f-acda-630a43bea877` |
| 3 | 2026-02-24 18:23:32.576000+00:00 | knowledge_qa_supervisor | Invocation PENDING for > 5 minutes (Timed Out) | Using config WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG, calculate for 'test A'. | [`738cf9dfc51da4180ec63fbea6c53a04`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04?project=agent-operations-ek-01) | `e-fac82a1e-e297-4d17-80d9-0db8e7e32263` |
| 4 | 2026-02-24 18:20:10.204000+00:00 | knowledge_qa_supervisor | Invocation PENDING for > 5 minutes (Timed Out) | Explain real-time monitoring for AI agents. | [`dbbf171351937900fcae0f2cd05d45ff`](https://console.cloud.google.com/traces/explorer;traceId=dbbf171351937900fcae0f2cd05d45ff?project=agent-operations-ek-01) | `e-23493f19-2e72-482f-b880-773fcc057abe` |
| 5 | 2026-02-24 18:20:10.151000+00:00 | knowledge_qa_supervisor | Invocation PENDING for > 5 minutes (Timed Out) | Explain real-time monitoring for AI agents. | [`671f601eb777a5e46f0af18ecf3f639d`](https://console.cloud.google.com/traces/explorer;traceId=671f601eb777a5e46f0af18ecf3f639d?project=agent-operations-ek-01) | `e-23aeae45-d1e3-4a11-8bd0-6b9be7fcb7e7` |

### Agent Errors

| Rank | Timestamp | Agent Name | Error Message | Root Agent | Root Status | User Message | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24 18:30:44.609000+00:00 | ai_observability_agent | Agent span PENDING for > 5 minutes (Timed Out) | knowledge_qa_supervisor | UNKNOWN ❓ | None | [`6e722d2ee482472a74d9774b994a0453`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453?project=agent-operations-ek-01) | [`d94e8db1170b1c7e`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453;spanId=d94e8db1170b1c7e?project=agent-operations-ek-01) |
| 2 | 2026-02-24 18:30:40.381000+00:00 | knowledge_qa_supervisor | Agent span PENDING for > 5 minutes (Timed Out) | knowledge_qa_supervisor | UNKNOWN ❓ | None | [`6e722d2ee482472a74d9774b994a0453`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453?project=agent-operations-ek-01) | [`496c7a08fde1d7a2`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453;spanId=496c7a08fde1d7a2?project=agent-operations-ek-01) |
| 3 | 2026-02-24 18:30:29.973000+00:00 | ai_observability_agent | Agent span PENDING for > 5 minutes (Timed Out) | knowledge_qa_supervisor | ERROR 🔴 | What are the key metrics for AI agent health? | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`a0b3b3d8a14dd9dc`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=a0b3b3d8a14dd9dc?project=agent-operations-ek-01) |
| 4 | 2026-02-24 18:30:29.973000+00:00 | ai_observability_agent | Agent span PENDING for > 5 minutes (Timed Out) | knowledge_qa_supervisor | ERROR 🔴 | Explain real-time monitoring for AI agents. | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`a0b3b3d8a14dd9dc`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=a0b3b3d8a14dd9dc?project=agent-operations-ek-01) |
| 5 | 2026-02-24 18:23:34.807000+00:00 | config_test_agent_wrong_max_output_tokens_count_config | Agent span PENDING for > 5 minutes (Timed Out) | knowledge_qa_supervisor | ERROR 🔴 | Using config WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG, calculate for 'test A'. | [`738cf9dfc51da4180ec63fbea6c53a04`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04?project=agent-operations-ek-01) | [`caded97ae9ccd5a9`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04;spanId=caded97ae9ccd5a9?project=agent-operations-ek-01) |


### Tool Errors

| Rank | Timestamp | Tool Name | Tool Args | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24 18:17:57.819000+00:00 | flaky_tool_simulation | {"query":"Simulate a flaky action for 'test case 1'"} | unreliable_tool timed out for query: Simulate a flaky action for 'test case 1' | unreliable_tool_agent | ERROR 🔴 | knowledge_qa_supervisor | OK 🟢 | Describe event logging in AI agents. | [`c1a31dc41240d3f36d968c9a340b4e78`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78?project=agent-operations-ek-01) | [`df8428b97374a906`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78;spanId=df8428b97374a906?project=agent-operations-ek-01) |
| 2 | 2026-02-24 18:17:57.819000+00:00 | flaky_tool_simulation | {"query":"Simulate a flaky action for 'test case 1'"} | unreliable_tool timed out for query: Simulate a flaky action for 'test case 1' | unreliable_tool_agent | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | Simulate a flaky action for 'test case 1'. | [`c1a31dc41240d3f36d968c9a340b4e78`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78?project=agent-operations-ek-01) | [`df8428b97374a906`](https://console.cloud.google.com/traces/explorer;traceId=c1a31dc41240d3f36d968c9a340b4e78;spanId=df8428b97374a906?project=agent-operations-ek-01) |
| 3 | 2026-02-24 18:11:39.412000+00:00 | flaky_tool_simulation | {"query":"test case 1"} | Quota exceeded for unreliable_tool for query: test case 1 | unreliable_tool_agent | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | Simulate a flaky action for 'test case 1'. | [`244f62b8d272474da0d455e47757aa67`](https://console.cloud.google.com/traces/explorer;traceId=244f62b8d272474da0d455e47757aa67?project=agent-operations-ek-01) | [`5fc340627c95ab89`](https://console.cloud.google.com/traces/explorer;traceId=244f62b8d272474da0d455e47757aa67;spanId=5fc340627c95ab89?project=agent-operations-ek-01) |
| 4 | 2026-02-24 18:11:39.412000+00:00 | flaky_tool_simulation | {"query":"test case 1"} | Quota exceeded for unreliable_tool for query: test case 1 | unreliable_tool_agent | ERROR 🔴 | knowledge_qa_supervisor | OK 🟢 | Describe event logging in AI agents. | [`244f62b8d272474da0d455e47757aa67`](https://console.cloud.google.com/traces/explorer;traceId=244f62b8d272474da0d455e47757aa67?project=agent-operations-ek-01) | [`5fc340627c95ab89`](https://console.cloud.google.com/traces/explorer;traceId=244f62b8d272474da0d455e47757aa67;spanId=5fc340627c95ab89?project=agent-operations-ek-01) |
| 5 | 2026-02-24 18:09:24.281000+00:00 | flaky_tool_simulation | {"query":"very_slow_topic"} | unreliable_tool timed out for query: very_slow_topic | unreliable_tool_agent | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | Try the unreliable tool with very_slow_topic input. | [`bf46dbf39dc20547ec31b2e3ae73c6be`](https://console.cloud.google.com/traces/explorer;traceId=bf46dbf39dc20547ec31b2e3ae73c6be?project=agent-operations-ek-01) | [`8f579c4071f0b24a`](https://console.cloud.google.com/traces/explorer;traceId=bf46dbf39dc20547ec31b2e3ae73c6be;spanId=8f579c4071f0b24a?project=agent-operations-ek-01) |

### LLM Errors

| Rank | Timestamp | Model Name | LLM Config | Error Message | Parent Agent | Agent Status | Root Agent | Root Status | User Message | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24 18:30:44.609000+00:00 | gemini-3-pro-preview | None | [LARGE PAYLOAD: 14007 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | ai_observability_agent | ERROR 🔴 | None | UNKNOWN ❓ | None | [`6e722d2ee482472a74d9774b994a0453`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453?project=agent-operations-ek-01) | [`966edba3aa76d176`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453;spanId=966edba3aa76d176?project=agent-operations-ek-01) |
| 2 | 2026-02-24 18:30:29.973000+00:00 | gemini-3-pro-preview | None | [LARGE PAYLOAD: 14008 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | ai_observability_agent | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | What are the key metrics for AI agent health? | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`4d68bffbd200c7fe`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=4d68bffbd200c7fe?project=agent-operations-ek-01) |
| 3 | 2026-02-24 18:30:29.973000+00:00 | gemini-3-pro-preview | None | [LARGE PAYLOAD: 14008 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | ai_observability_agent | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | Explain real-time monitoring for AI agents. | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`4d68bffbd200c7fe`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=4d68bffbd200c7fe?project=agent-operations-ek-01) |
| 4 | 2026-02-24 18:23:34.808000+00:00 | gemini-2.5-flash | {"candidate_count":1,"max_output_tokens":100000,"presence_penalty":0.1,"top_k":5,"top_p":0.1} | [LARGE PAYLOAD: 1445 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | config_test_agent_wrong_max_output_tokens_count_config | ERROR 🔴 | knowledge_qa_supervisor | ERROR 🔴 | Using config WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG, calculate for 'test A'. | [`738cf9dfc51da4180ec63fbea6c53a04`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04?project=agent-operations-ek-01) | [`a7f0de2071d3dfdf`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04;spanId=a7f0de2071d3dfdf?project=agent-operations-ek-01) |
| 5 | 2026-02-24 18:20:17.404000+00:00 | gemini-3-pro-preview | None | [LARGE PAYLOAD: 13946 chars. Use batch_analyze_root_cause(span_ids='...') to analyze full content instead of fetching it here.] | ai_observability_agent | ERROR 🔴 | None | UNKNOWN ❓ | None | [`bd7592ed3b615164f96e5e4f5592d492`](https://console.cloud.google.com/traces/explorer;traceId=bd7592ed3b615164f96e5e4f5592d492?project=agent-operations-ek-01) | [`3c718e4a8a2b89ab`](https://console.cloud.google.com/traces/explorer;traceId=bd7592ed3b615164f96e5e4f5592d492;spanId=3c718e4a8a2b89ab?project=agent-operations-ek-01) |



---

## Empty LLM Responses
Zero output tokens generated.
### Summary

| Model Name | Agent Name | Empty Response Count |
| :--- | :--- | :--- |
| gemini-2.5-pro | ai_observability_agent | 22 |
| gemini-2.5-pro | adk_documentation_agent | 16 |
| gemini-3-pro-preview | ai_observability_agent | 14 |
| gemini-2.5-flash | config_test_agent_wrong_max_output_tokens_count_config | 9 |
| gemini-3.1-pro-preview | lookup_worker_2 | 4 |
| gemini-3.1-pro-preview | lookup_worker_3 | 3 |
| gemini-2.5-flash | adk_documentation_agent | 2 |
| gemini-3.1-pro-preview | config_test_agent_wrong_max_output_tokens_count_config | 1 |
| gemini-3-pro-preview | knowledge_qa_supervisor | 1 |
| gemini-3-pro-preview | lookup_worker_1 | 1 |
| gemini-3.1-pro-preview | lookup_worker_1 | 1 |

### Details

| Rank | Timestamp | Model Name | Agent Name | User Message | Prompt Tokens | Latency (s) | Trace ID | Span ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-02-24T18:31:48.896000+00:00 | gemini-3.1-pro-preview | lookup_worker_3 | Retrieve customer_ID_123, order_ID_456 simultaneously. | 147 | 5.499 | [`6ea801916e9f0384d32c8659fec5ff44`](https://console.cloud.google.com/traces/explorer;traceId=6ea801916e9f0384d32c8659fec5ff44?project=agent-operations-ek-01) | [`b6800ab6dc25c20b`](https://console.cloud.google.com/traces/explorer;traceId=6ea801916e9f0384d32c8659fec5ff44;spanId=b6800ab6dc25c20b?project=agent-operations-ek-01) |
| 2 | 2026-02-24T18:30:44.609000+00:00 | gemini-3-pro-preview | ai_observability_agent | None | 0 | 7.070 | [`6e722d2ee482472a74d9774b994a0453`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453?project=agent-operations-ek-01) | [`966edba3aa76d176`](https://console.cloud.google.com/traces/explorer;traceId=6e722d2ee482472a74d9774b994a0453;spanId=966edba3aa76d176?project=agent-operations-ek-01) |
| 3 | 2026-02-24T18:30:29.973000+00:00 | gemini-3-pro-preview | ai_observability_agent | Explain real-time monitoring for AI agents. | 0 | 9.892 | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`4d68bffbd200c7fe`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=4d68bffbd200c7fe?project=agent-operations-ek-01) |
| 4 | 2026-02-24T18:30:29.973000+00:00 | gemini-3-pro-preview | ai_observability_agent | What are the key metrics for AI agent health? | 0 | 9.892 | [`34092d5ff289565a8c24785995906ed6`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6?project=agent-operations-ek-01) | [`4d68bffbd200c7fe`](https://console.cloud.google.com/traces/explorer;traceId=34092d5ff289565a8c24785995906ed6;spanId=4d68bffbd200c7fe?project=agent-operations-ek-01) |
| 5 | 2026-02-24T18:29:21.665000+00:00 | gemini-2.5-pro | ai_observability_agent | Describe event logging in AI agents. | 397 | 46.516 | [`6b4a587717dbf843e57f310c546de93b`](https://console.cloud.google.com/traces/explorer;traceId=6b4a587717dbf843e57f310c546de93b?project=agent-operations-ek-01) | [`df4266e984fc040f`](https://console.cloud.google.com/traces/explorer;traceId=6b4a587717dbf843e57f310c546de93b;spanId=df4266e984fc040f?project=agent-operations-ek-01) |
| 6 | 2026-02-24T18:28:02.315000+00:00 | gemini-3.1-pro-preview | lookup_worker_2 | Execute concurrent lookups for 'inventory_A', 'inventory_B', 'inventory_C'. | 149 | 4.105 | [`10223a48c1c1f6edeac9d06e7d7cf0a1`](https://console.cloud.google.com/traces/explorer;traceId=10223a48c1c1f6edeac9d06e7d7cf0a1?project=agent-operations-ek-01) | [`b5738b26b884be4a`](https://console.cloud.google.com/traces/explorer;traceId=10223a48c1c1f6edeac9d06e7d7cf0a1;spanId=b5738b26b884be4a?project=agent-operations-ek-01) |
| 7 | 2026-02-24T18:27:33.476000+00:00 | gemini-2.5-pro | ai_observability_agent | What are the best open source observability solutions for agents? | 205 | 6.205 | [`dfa470d3e4ac6f6fd0da867738291c1b`](https://console.cloud.google.com/traces/explorer;traceId=dfa470d3e4ac6f6fd0da867738291c1b?project=agent-operations-ek-01) | [`016ef10af8ecba6f`](https://console.cloud.google.com/traces/explorer;traceId=dfa470d3e4ac6f6fd0da867738291c1b;spanId=016ef10af8ecba6f?project=agent-operations-ek-01) |
| 8 | 2026-02-24T18:24:24.790000+00:00 | gemini-2.5-pro | ai_observability_agent | Explain the benefits of AI agent tracing. | 720 | 4.528 | [`f8eda13d71fe90a2c5656de496ab543c`](https://console.cloud.google.com/traces/explorer;traceId=f8eda13d71fe90a2c5656de496ab543c?project=agent-operations-ek-01) | [`b09e52b5198c8a56`](https://console.cloud.google.com/traces/explorer;traceId=f8eda13d71fe90a2c5656de496ab543c;spanId=b09e52b5198c8a56?project=agent-operations-ek-01) |
| 9 | 2026-02-24T18:23:34.808000+00:00 | gemini-2.5-flash | config_test_agent_wrong_max_output_tokens_count_config | Using config WRONG_MAX_OUTPUT_TOKENS_COUNT_CONFIG, calculate for 'test A'. | 0 | 1.080 | [`738cf9dfc51da4180ec63fbea6c53a04`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04?project=agent-operations-ek-01) | [`a7f0de2071d3dfdf`](https://console.cloud.google.com/traces/explorer;traceId=738cf9dfc51da4180ec63fbea6c53a04;spanId=a7f0de2071d3dfdf?project=agent-operations-ek-01) |
| 10 | 2026-02-24T18:21:21.813000+00:00 | gemini-3.1-pro-preview | lookup_worker_3 | Retrieve customer_ID_123, order_ID_456 simultaneously. | 147 | 5.025 | [`b9d1f585047e79931110efd73754e0fb`](https://console.cloud.google.com/traces/explorer;traceId=b9d1f585047e79931110efd73754e0fb?project=agent-operations-ek-01) | [`ff686c8970d51c33`](https://console.cloud.google.com/traces/explorer;traceId=b9d1f585047e79931110efd73754e0fb;spanId=ff686c8970d51c33?project=agent-operations-ek-01) |
| 11 | 2026-02-24T18:20:17.404000+00:00 | gemini-3-pro-preview | ai_observability_agent | None | 0 | 5.751 | [`bd7592ed3b615164f96e5e4f5592d492`](https://console.cloud.google.com/traces/explorer;traceId=bd7592ed3b615164f96e5e4f5592d492?project=agent-operations-ek-01) | [`3c718e4a8a2b89ab`](https://console.cloud.google.com/traces/explorer;traceId=bd7592ed3b615164f96e5e4f5592d492;spanId=3c718e4a8a2b89ab?project=agent-operations-ek-01) |
| 12 | 2026-02-24T18:20:14.185000+00:00 | gemini-3-pro-preview | ai_observability_agent | None | 0 | 7.058 | [`e30fae36023e8458a06e4bb18cccba85`](https://console.cloud.google.com/traces/explorer;traceId=e30fae36023e8458a06e4bb18cccba85?project=agent-operations-ek-01) | [`89f9a6f0a1d8134f`](https://console.cloud.google.com/traces/explorer;traceId=e30fae36023e8458a06e4bb18cccba85;spanId=89f9a6f0a1d8134f?project=agent-operations-ek-01) |
| 13 | 2026-02-24T18:20:04.461000+00:00 | gemini-3-pro-preview | ai_observability_agent | What are the key metrics for AI agent health? | 0 | 5.180 | [`671f601eb777a5e46f0af18ecf3f639d`](https://console.cloud.google.com/traces/explorer;traceId=671f601eb777a5e46f0af18ecf3f639d?project=agent-operations-ek-01) | [`80e56d8113dbc8ef`](https://console.cloud.google.com/traces/explorer;traceId=671f601eb777a5e46f0af18ecf3f639d;spanId=80e56d8113dbc8ef?project=agent-operations-ek-01) |
| 14 | 2026-02-24T18:20:04.461000+00:00 | gemini-3-pro-preview | ai_observability_agent | Explain real-time monitoring for AI agents. | 0 | 5.180 | [`671f601eb777a5e46f0af18ecf3f639d`](https://console.cloud.google.com/traces/explorer;traceId=671f601eb777a5e46f0af18ecf3f639d?project=agent-operations-ek-01) | [`80e56d8113dbc8ef`](https://console.cloud.google.com/traces/explorer;traceId=671f601eb777a5e46f0af18ecf3f639d;spanId=80e56d8113dbc8ef?project=agent-operations-ek-01) |
| 15 | 2026-02-24T18:20:03.499000+00:00 | gemini-3-pro-preview | ai_observability_agent | What are the key metrics for AI agent health? | 0 | 6.199 | [`dbbf171351937900fcae0f2cd05d45ff`](https://console.cloud.google.com/traces/explorer;traceId=dbbf171351937900fcae0f2cd05d45ff?project=agent-operations-ek-01) | [`31dca9956b832daa`](https://console.cloud.google.com/traces/explorer;traceId=dbbf171351937900fcae0f2cd05d45ff;spanId=31dca9956b832daa?project=agent-operations-ek-01) |
| 16 | 2026-02-24T18:20:03.499000+00:00 | gemini-3-pro-preview | ai_observability_agent | Explain real-time monitoring for AI agents. | 0 | 6.199 | [`dbbf171351937900fcae0f2cd05d45ff`](https://console.cloud.google.com/traces/explorer;traceId=dbbf171351937900fcae0f2cd05d45ff?project=agent-operations-ek-01) | [`31dca9956b832daa`](https://console.cloud.google.com/traces/explorer;traceId=dbbf171351937900fcae0f2cd05d45ff;spanId=31dca9956b832daa?project=agent-operations-ek-01) |
| 17 | 2026-02-24T18:19:50.026000+00:00 | gemini-2.5-pro | adk_documentation_agent | None | 0 | 9.340 | [`3f67c18a2acfd4f88823468749d3464b`](https://console.cloud.google.com/traces/explorer;traceId=3f67c18a2acfd4f88823468749d3464b?project=agent-operations-ek-01) | [`eca84384d617f103`](https://console.cloud.google.com/traces/explorer;traceId=3f67c18a2acfd4f88823468749d3464b;spanId=eca84384d617f103?project=agent-operations-ek-01) |
| 18 | 2026-02-24T18:19:39.297000+00:00 | gemini-2.5-pro | adk_documentation_agent | Describe ADK's configuration options. | 0 | 7.504 | [`bfa983265ad7a06de323947541c33f50`](https://console.cloud.google.com/traces/explorer;traceId=bfa983265ad7a06de323947541c33f50?project=agent-operations-ek-01) | [`8ee7050b3eeea086`](https://console.cloud.google.com/traces/explorer;traceId=bfa983265ad7a06de323947541c33f50;spanId=8ee7050b3eeea086?project=agent-operations-ek-01) |
| 19 | 2026-02-24T18:19:39.297000+00:00 | gemini-2.5-pro | adk_documentation_agent | What are common ADK deployment issues? | 0 | 7.504 | [`bfa983265ad7a06de323947541c33f50`](https://console.cloud.google.com/traces/explorer;traceId=bfa983265ad7a06de323947541c33f50?project=agent-operations-ek-01) | [`8ee7050b3eeea086`](https://console.cloud.google.com/traces/explorer;traceId=bfa983265ad7a06de323947541c33f50;spanId=8ee7050b3eeea086?project=agent-operations-ek-01) |
| 20 | 2026-02-24T18:19:33.489000+00:00 | gemini-2.5-pro | ai_observability_agent | Describe event logging in AI agents. | 417 | 7.209 | [`a9e5283f2e1c60bb5b4b40ddc088bbf7`](https://console.cloud.google.com/traces/explorer;traceId=a9e5283f2e1c60bb5b4b40ddc088bbf7?project=agent-operations-ek-01) | [`54a0a0dff97d4359`](https://console.cloud.google.com/traces/explorer;traceId=a9e5283f2e1c60bb5b4b40ddc088bbf7;spanId=54a0a0dff97d4359?project=agent-operations-ek-01) |

---

## Recommendations

1.  **Address Timeout Issues:** The prevalent "Agent span PENDING for > 5 minutes (Timed Out)" error message indicates a systemic issue.
    *   **Increase Timeout Limits:** Temporarily increase timeout thresholds for critical agents like `knowledge_qa_supervisor`, `ai_observability_agent`, and `config_test_agent_wrong_max_output_tokens_count_config` to allow for successful completion and gather more data on actual completion times.
    *   **Optimize Long-Running Operations:** Investigate the underlying causes of long durations in `bigquery_data_agent`, `parallel_db_lookup`, and `google_search_agent`. This could involve optimizing external tool calls, database queries, or data processing.
    *   **Asynchronous Processing:** For operations identified as inherently slow (e.g., complex data lookups, large search queries), consider implementing asynchronous processing patterns to prevent blocking the agent's execution thread and avoid timeouts.
2.  **Mitigate High Error Rates:**
    *   **Investigate `config_test_agent_wrong_max_output_tokens_count_config` (100% Error Rate):** This agent consistently fails. Review its configuration (`max_output_tokens` setting) and its interactions with models (`gemini-2.5-flash`, `gemini-3.1-pro-preview`) to resolve the configuration conflict or model incompatibility.
    *   **Review `adk_documentation_agent`, `ai_observability_agent`, `unreliable_tool_agent` Errors:** Analyze detailed logs for these agents to understand the specific failures beyond timeouts. For `unreliable_tool_agent`, acknowledge that some errors are by design ("flaky action"), but verify if actual errors exceed expected "flakiness" and if recovery mechanisms are in place.
    *   **Address Model-Specific Errors:** The 100% error rate for `gemini-2.5-pro` in `adk_documentation_agent` and `gemini-3-pro-preview` in `lookup_worker_1`, `lookup_worker_2`, `lookup_worker_3` suggests a misconfiguration or incompatibility. These specific agent-model combinations need immediate attention.
3.  **Optimize Token Usage & Latency Correlation:**
    *   **Large Output/Thought Tokens:** The strong correlation between latency and `output_tokens` or `thoughts_token_count` for several models (e.g., `gemini-3-pro-preview`, `gemini-3.1-pro-preview`) and agents (`lookup_worker_3`, `ai_observability_agent`) indicates that generating extensive responses or internal thoughts significantly increases latency.
    *   **Prompt Engineering:** Refine prompts to encourage more concise and direct responses from LLMs, reducing unnecessary token generation.
    *   **Response Summarization:** Implement post-processing steps to summarize large LLM outputs if the full detail is not always required by downstream tasks.
4.  **Model Selection Review:**
    *   For agents currently underperforming on specific models (e.g., `ai_observability_agent` with `gemini-2.5-pro` and `gemini-3-pro-preview` showing high errors, or `lookup_worker_3` with `gemini-2.5-pro` showing very high P95.5 latency), consider re-evaluating the model choice or prompt strategy for those combinations. `gemini-2.5-flash` generally shows lower latencies and error rates across agents when it is used successfully.
5.  **Monitor Empty LLM Responses:** The significant number of empty LLM responses for `ai_observability_agent` and `adk_documentation_agent` needs investigation. This could indicate prompt issues, model failures, or incorrect handling of edge cases.

---

## Configuration

```json
{
  "time_period": "7d",
  "playbook": "overview",
  "kpis": {
    "end_to_end": {
      "latency_target": 10.0,
      "percentile_target": 95.5,
      "error_target": 5.0
    },
    "agent": {
      "latency_target": 8.0,
      "percentile_target": 95.5,
      "error_target": 5.0
    },
    "llm": {
      "latency_target": 5.0,
      "percentile_target": 95.5,
      "error_target": 5.0
    },
    "tool": {
      "latency_target": 3.0,
      "percentile_target": 95.5,
      "error_target": 5.0
    }
  },
  "num_slowest_queries": 5,
  "num_error_queries": 5
}
```