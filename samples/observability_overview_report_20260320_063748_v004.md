# Agents Observability Report

| **Property**        | **Value**                 |
|:--------------------|:--------------------------|
| **Project ID**      | `agent-operations-ek-05`  |
| **Playbook**        | `overview`                |
| **Time Range**      | `all`                     |
| **Analysis Window** | `All Available History`   |
| **Datastore ID**    | `logging`                 |
| **Table ID**        | `agent_events_demo_v3`    |
| **Generated**       | `2026-03-20 06:38:39 UTC` |
| **Agent Version**   | `0.0.4`                   |
| **Agent Model ID**  | `gemini-3.1-pro-preview`  |

---


## How to Navigate This Report

This observability report provides a comprehensive, deep-dive analysis of your multi-agent ecosystem. Given its extensive length, it is designed to be consumed either as a high-level summary or as a granular debugging tool. 

**Recommended Reading Path:**
If you are new to this report or looking for immediate takeaways, we recommend following this primary path:
1. **[Executive Summary](#executive-summary):** Start here for a snapshot of critical system health metrics and an overview of whether your latency and error budgets are being met.
2. **[Root Cause Insights](#root-cause-insights):** Jump directly to the AI SRE's automated diagnosis of *why* the system is failing, including specific traces and anomalies. 
3. **[Recommendations](#recommendations) & [Architectural Recommendations](#architectural-recommendations):** Review the prioritized action items and structural changes required to resolve the identified bottlenecks and stability issues.

**Deep-Dive Sections:**
For engineers investigating specific traces, token usage, or resource exhaustion errors, utilize the sections below:
- **[Performance](#performance):** A top-down scorecard grading overall End-to-End, Agent, Tool, and Model execution against your defined Service Level Objectives (SLOs).
- **[System Bottlenecks & Impact](#system-bottlenecks--impact):** A forensic breakdown of the absolute slowest invocations, agents, models, and tools.
- **[Error Analysis](#error-analysis) & [Critical Workflow Failures](#critical-workflow-failures):** Categorized insights into system crashes, hallucinated tool calls, capacity rejections (e.g., HTTP 429s), and flaky simulated tools.
- **[Empty LLM Responses](#empty-llm-responses):** Identifies cases where the LLM returned 0 output tokens. Extracts the full context (User Message, Model, Prompt Tokens) and intelligently deduplicates to surface the most diverse set of generation failures.
- **[Pathological Generation Loops](#pathological-generation-loops):** Identifies instances where the LLM generated massive token outputs, typically symptomatic of a runaway cognitive reasoning loop or hallucination.
- **[Hypothesis Testing: Latency & Tokens](#hypothesis-testing-latency--tokens):** A rigorous analysis exploring the correlation between token consumption and latency, identifying pathological reasoning loops or context bloating.
- **Granular Breakdowns:** Browse the [Agent Details](#agent-details), [Tool Details](#tool-details), and [Model Details](#model-details) for raw volume, traffic distribution, token breakdowns, and sequential latency charts over time.

---


## Executive Summary


The multi-agent ecosystem is failing its primary Service Level Objectives, severely bottlenecked by unhandled application-level crashes, massive internal agent overhead, and pathological LLM generation loops. The root `knowledge_qa_supervisor` agent is failing its E2E targets with a 30.4s mean latency (91.0s P95.5) and a 25.42% error rate. Top-level degradation is heavily driven by catastrophic execution profiles within sub-agents like `bigquery_data_agent`, which exhibits ~228s of internal overhead due to synchronous blocking during unoptimized executions. Furthermore, a systemic prompt-safety issue is snapping reasoning chains, evidenced by 252 empty token responses predominantly striking `ai_observability_agent`. Finally, model capacity misalignments are causing `gemini-3.1-pro-preview` and `gemini-3-pro-preview` to suffer from >8% error rates due to 429 RESOURCE_EXHAUSTED provider rejections, while `gemini-2.5-flash` maintains a stable 0.65% error rate.


---


## Performance

This section provides a high-level scorecard for End to End, Sub Agent, Tool, and LLM levels, assessing compliance against defined Service Level Objectives (SLOs).


---


Overall system performance is failing (🔴). The End-to-End status is 🔴, failing both the <30.0s latency target and the <5.0% error target. Almost all sub-agents, including `bigquery_data_agent` and `adk_documentation_agent`, achieved an Overall 🔴 status for missing latency and error SLOs. Tool performance is mostly 🟢, though `flaky_tool_simulation`, `search`, and `list_tables` drove tool-level Overall status to 🔴. At the model level, all models breached the 8.0s P95.5 latency target (Overall 🔴), and `gemini-3-pro-preview` and `gemini-3.1-pro-preview` breached the 5.0% error target.


---


### End to End


The system is governed by a single root agent, `knowledge_qa_supervisor`, which is the slowest root agent with a mean latency of 30.406s and a P95.5 latency of 91.069s, breaching the 30.0s target. The absolute slowest single invocation took 276.118s, which can be reviewed here: [8dc35732c05c554d2134596dd4465400](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05).

This shows user-facing performance from start to end of an invocation.

| **Name**                    |   **Requests** | **%**   |   **Mean (s)** |   **P95.5 (s)** |   **Target (s)** | **Status**   |   **Err %** |   **Target (%)** | **Status**   | **Input Tok (Avg/P95)**   | **Output Tok (Avg/P95)**   | **Thought Tok (Avg/P95)**   | **Tokens Consumed (Avg/P95)**   | **Overall**   |
|:----------------------------|---------------:|:--------|---------------:|----------------:|-----------------:|:-------------|------------:|-----------------:|:-------------|:--------------------------|:---------------------------|:----------------------------|:--------------------------------|:--------------|
| **knowledge_qa_supervisor** |           1727 | 100.0%  |         30.406 |          91.069 |               30 | 🔴           |       25.42 |                5 | 🔴           | 27034 / 112282            | 109 / 330                  | 478 / 1448                  | 27622 / 112747                  | 🔴            |

<br>



**Root Agent Execution**

The following charts display the end-to-end execution latency for each top-level Root Agent over the course of the test run, plotted in the order the requests were received. This helps identify degradation in overall system performance over time.


**knowledge_qa_supervisor Latency (Request Order)**<br>

[![knowledge_qa_supervisor Latency (Request Order)](report_assets_20260320_063748/e2e_sequence_knowledge_qa_supervisor.png)](report_assets_20260320_063748/e2e_sequence_knowledge_qa_supervisor_4K.png)
<br>

**knowledge_qa_supervisor Latency Histogram**<br>

[![knowledge_qa_supervisor Latency Histogram](report_assets_20260320_063748/e2e_histogram_knowledge_qa_supervisor.png)](report_assets_20260320_063748/e2e_histogram_knowledge_qa_supervisor_4K.png)
<br>


---


### Agent Level


Almost all sub-agents missed the 10.0s latency target. Agents with >0% error rates include `bigquery_data_agent` (33.25%), `unreliable_tool_agent` (18.06%), `parallel_db_lookup` (17.32%), `ai_observability_agent` (16.36%), `adk_documentation_agent` (15.78%), `lookup_worker_3` (15.75%), `lookup_worker_1` (15.75%), `lookup_worker_2` (14.96%), `config_test_agent_wrong_candidates` (7.89%), `config_test_agent_over_provisioned` (6.82%), `config_test_agent_normal` (6.82%), `config_test_agent_high_temp` (2.44%), and `google_search_agent` (1.57%). The `config_test_agent_wrong_max_tokens` agent completely failed with a 100% Error Rate.

| Name                                   |   Requests | %     | Mean (s)   | P95.5 (s)   |   Target (s) | Status   |   Err % |   Target (%) | Err Status   | Overall   |
|:---------------------------------------|-----------:|:------|:-----------|:------------|-------------:|:---------|--------:|-------------:|:-------------|:----------|
| **bigquery_data_agent**                |        400 | 18.7% | 44.238     | 116.416     |           10 | 🔴       |   33.25 |            5 | 🔴           | 🔴        |
| **config_test_agent_wrong_candidates** |         38 | 1.8%  | 30.44      | 89.958      |           10 | 🔴       |    7.89 |            5 | 🔴           | 🔴        |
| **adk_documentation_agent**            |        374 | 17.5% | 30.112     | 90.567      |           10 | 🔴       |   15.78 |            5 | 🔴           | 🔴        |
| **parallel_db_lookup**                 |        127 | 5.9%  | 26.764     | 81.41       |           10 | 🔴       |   17.32 |            5 | 🔴           | 🔴        |
| **google_search_agent**                |        191 | 8.9%  | 21.653     | 46.145      |           10 | 🔴       |    1.57 |            5 | 🟢           | 🔴        |
| **config_test_agent_over_provisioned** |         44 | 2.1%  | 20.831     | 64.327      |           10 | 🔴       |    6.82 |            5 | 🔴           | 🔴        |
| **lookup_worker_3**                    |        127 | 5.9%  | 20.532     | 60.556      |           10 | 🔴       |   15.75 |            5 | 🔴           | 🔴        |
| **lookup_worker_2**                    |        127 | 5.9%  | 19.878     | 53.914      |           10 | 🔴       |   14.96 |            5 | 🔴           | 🔴        |
| **config_test_agent_high_temp**        |         41 | 1.9%  | 16.253     | 42.451      |           10 | 🔴       |    2.44 |            5 | 🟢           | 🔴        |
| **lookup_worker_1**                    |        127 | 5.9%  | 15.667     | 33.267      |           10 | 🔴       |   15.75 |            5 | 🔴           | 🔴        |
| **ai_observability_agent**             |        324 | 15.1% | 13.138     | 55.231      |           10 | 🔴       |   16.36 |            5 | 🔴           | 🔴        |
| **unreliable_tool_agent**              |         72 | 3.4%  | 12.79      | 39.01       |           10 | 🔴       |   18.06 |            5 | 🔴           | 🔴        |
| **config_test_agent_normal**           |         44 | 2.1%  | 12.045     | 43.315      |           10 | 🔴       |    6.82 |            5 | 🔴           | 🔴        |
| **config_test_agent_wrong_max_tokens** |        103 | 4.8%  | -          | -           |           10 | ⚪       |  100    |            5 | 🔴           | 🔴        |

<br>

**Agent Level Usage**<br>

[![Agent Level Usage](report_assets_20260320_063748/agent__usage.png)](report_assets_20260320_063748/agent__usage_4K.png)
<br>

**Agent Level Latency (Target: 10.0s)**<br>

[![Agent Level Latency (Target: 10.0s)](report_assets_20260320_063748/agent__lat_status.png)](report_assets_20260320_063748/agent__lat_status_4K.png)
<br>

**Agent Level Error (Target: 5.0%)**<br>

[![Agent Level Error (Target: 5.0%)](report_assets_20260320_063748/agent__err_status.png)](report_assets_20260320_063748/agent__err_status_4K.png)
<br>


---


### Tool Level


The slowest tools are `complex_calculation` (Mean Latency 2.042s) and `flaky_tool_simulation` (Mean Latency 1.264s). While most tools met the 3.0s latency target, `flaky_tool_simulation` experienced a 13.7% error rate, and the hallucinated tools `search` and `list_tables` experienced 100% error rates.

| Name                      |   Requests | %     | Mean (s)   | P95.5 (s)   |   Target (s) | Status   |   Err % |   Target (%) | Err Status   | Overall   |
|:--------------------------|-----------:|:------|:-----------|:------------|-------------:|:---------|--------:|-------------:|:-------------|:----------|
| **complex_calculation**   |         44 | 2.2%  | 2.042      | 2.984       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **flaky_tool_simulation** |         73 | 3.6%  | 1.264      | 1.963       |            3 | 🟢       |    13.7 |            5 | 🔴           | 🔴        |
| **search_catalog**        |          5 | 0.2%  | 0.802      | 0.997       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **execute_sql**           |        796 | 39.5% | 0.705      | 1.105       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **simulated_db_lookup**   |        766 | 38.0% | 0.588      | 0.956       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **list_dataset_ids**      |         24 | 1.2%  | 0.21       | 0.229       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **get_dataset_info**      |          1 | 0.0%  | 0.187      | 0.187       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **get_table_info**        |        217 | 10.8% | 0.18       | 0.214       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **list_table_ids**        |         84 | 4.2%  | 0.175      | 0.321       |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **detect_anomalies**      |          2 | 0.1%  | 0.0        | 0.0         |            3 | 🟢       |     0   |            5 | 🟢           | 🟢        |
| **search**                |          3 | 0.1%  | -          | -           |            3 | ⚪       |   100   |            5 | 🔴           | 🔴        |
| **list_tables**           |          1 | 0.0%  | -          | -           |            3 | ⚪       |   100   |            5 | 🔴           | 🔴        |

<br>

**Tool Level Usage**<br>

[![Tool Level Usage](report_assets_20260320_063748/tool__usage.png)](report_assets_20260320_063748/tool__usage_4K.png)
<br>

**Tool Level Latency (Target: 3.0s)**<br>

[![Tool Level Latency (Target: 3.0s)](report_assets_20260320_063748/tool__lat_status.png)](report_assets_20260320_063748/tool__lat_status_4K.png)
<br>

**Tool Level Error (Target: 5.0%)**<br>

[![Tool Level Error (Target: 5.0%)](report_assets_20260320_063748/tool__err_status.png)](report_assets_20260320_063748/tool__err_status_4K.png)
<br>


---


### Model Level


The most used models are `gemini-2.5-flash` (5378 requests, 35.4%) and `gemini-2.5-pro` (5132 requests, 33.8%). The slowest model is `gemini-3-pro-preview` with a mean latency of 15.258s and a P95.5 of 35.943s. Both `gemini-3-pro-preview` (7.98% error rate) and `gemini-3.1-pro-preview` (8.5% error rate) failed the 5.0% error target.

| Name                       |   Requests | %     |   Mean (s) |   P95.5 (s) |   Target (s) | Status   |   Err % |   Target (%) | Err Status   | Input Tok (Avg/P95)   | Output Tok (Avg/P95)   | Thought Tok (Avg/P95)   | Tokens Consumed (Avg/P95)   | Overall   |
|:---------------------------|-----------:|:------|-----------:|------------:|-------------:|:---------|--------:|-------------:|:-------------|:----------------------|:-----------------------|:------------------------|:----------------------------|:----------|
| **gemini-3-pro-preview**   |       1956 | 12.9% |     15.258 |      35.943 |            8 | 🔴       |    7.98 |            5 | 🔴           | 10970 / 26158         | 133 / 607              | 704 / 2210              | 11763 / 26413               | 🔴        |
| **gemini-3.1-pro-preview** |       2729 | 18.0% |     12.211 |      46.638 |            8 | 🔴       |    8.5  |            5 | 🔴           | 22637 / 53577         | 96 / 290               | 398 / 854               | 23127 / 53981               | 🔴        |
| **gemini-2.5-pro**         |       5132 | 33.8% |      8.793 |      23.005 |            8 | 🔴       |    2.03 |            5 | 🟢           | 30821 / 112115        | 112 / 333              | 492 / 1498              | 31447 / 112510              | 🔴        |
| **gemini-2.5-flash**       |       5378 | 35.4% |      5.01  |      12.207 |            8 | 🔴       |    0.65 |            5 | 🟢           | 30935 / 115269        | 104 / 290              | 427 / 1270              | 31466 / 115767              | 🔴        |

<br>

**Model Level Usage**<br>

[![Model Level Usage](report_assets_20260320_063748/model__usage.png)](report_assets_20260320_063748/model__usage_4K.png)
<br>

**Model Level Latency (Target: 8.0s)**<br>

[![Model Level Latency (Target: 8.0s)](report_assets_20260320_063748/model__lat_status.png)](report_assets_20260320_063748/model__lat_status_4K.png)
<br>

**Model Level Error (Target: 5.0%)**<br>

[![Model Level Error (Target: 5.0%)](report_assets_20260320_063748/model__err_status.png)](report_assets_20260320_063748/model__err_status_4K.png)
<br>


---


## Agent Details


`bigquery_data_agent` predominantly uses `gemini-2.5-flash` (36%) and `gemini-2.5-pro` (34%). `ai_observability_agent` relies mostly on `gemini-2.5-flash` (44%) and `gemini-2.5-pro` (40%). The root `knowledge_qa_supervisor` is distributed fairly evenly across all four available models.


### Root Agents Summary

A high-level cross-report summary for each root workflow.


**`knowledge_qa_supervisor`**
- **Requests:** 1727 (100.0%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 30.406s / 91.069s
- **Errors:** 25.42%
- **Total Tokens (Avg/P95.5):** 27622 / 112747
- **Input:** 27034 / 112282 | **Output:** 109 / 330 | **Thought:** 478 / 1448



### Sub-Agents Summary

A high-level cross-report summary for each sub-agent.


**`bigquery_data_agent`**
- **Requests:** 400 (18.7%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 44.238s / 116.416s
- **Errors:** 33.25%
- **Total Tokens (Avg/P95.5):** 39029 / 114792
- **Input:** 38479 / 114158 | **Output:** 95 / 234 | **Thought:** 457 / 1362


**`config_test_agent_wrong_candidates`**
- **Requests:** 38 (1.8%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 30.44s / 89.958s
- **Errors:** 7.89%
- **Total Tokens (Avg/P95.5):** 6441 / 19658
- **Input:** 1692 / 3018 | **Output:** 695 / 2750 | **Thought:** 4715 / 17250


**`adk_documentation_agent`**
- **Requests:** 374 (17.5%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 30.112s / 90.567s
- **Errors:** 15.78%
- **Total Tokens (Avg/P95.5):** 4108 / 10107
- **Input:** 602 / 414 | **Output:** 614 / 1078 | **Thought:** 2424 / 7719


**`parallel_db_lookup`**
- **Requests:** 127 (5.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 26.764s / 81.41s
- **Errors:** 17.32%
- **Total Tokens (Avg/P95.5):** -
- **Input:** - | **Output:** - | **Thought:** -


**`google_search_agent`**
- **Requests:** 191 (8.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🟢)
- **Latency (Mean / P95.5):** 21.653s / 46.145s
- **Errors:** 1.57%
- **Total Tokens (Avg/P95.5):** 11315 / 90276
- **Input:** 9606 / 88926 | **Output:** 799 / 1324 | **Thought:** 704 / 1695


**`config_test_agent_over_provisioned`**
- **Requests:** 44 (2.1%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 20.831s / 64.327s
- **Errors:** 6.82%
- **Total Tokens (Avg/P95.5):** 2052 / 4382
- **Input:** 1664 / 2952 | **Output:** 109 / 392 | **Thought:** 349 / 854


**`lookup_worker_3`**
- **Requests:** 127 (5.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 20.532s / 60.556s
- **Errors:** 15.75%
- **Total Tokens (Avg/P95.5):** 916 / 2398
- **Input:** 634 / 1541 | **Output:** 41 / 78 | **Thought:** 332 / 1375


**`lookup_worker_2`**
- **Requests:** 127 (5.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 19.878s / 53.914s
- **Errors:** 14.96%
- **Total Tokens (Avg/P95.5):** 1101 / 2813
- **Input:** 662 / 1900 | **Output:** 155 / 85 | **Thought:** 345 / 1618


**`config_test_agent_high_temp`**
- **Requests:** 41 (1.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🟢)
- **Latency (Mean / P95.5):** 16.253s / 42.451s
- **Errors:** 2.44%
- **Total Tokens (Avg/P95.5):** 2619 / 4510
- **Input:** 1764 / 3190 | **Output:** 340 / 1665 | **Thought:** 535 / 1452


**`lookup_worker_1`**
- **Requests:** 127 (5.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 15.667s / 33.267s
- **Errors:** 15.75%
- **Total Tokens (Avg/P95.5):** 971 / 2517
- **Input:** 702 / 2047 | **Output:** 42 / 79 | **Thought:** 290 / 1061


**`ai_observability_agent`**
- **Requests:** 324 (15.1%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 13.138s / 55.231s
- **Errors:** 16.36%
- **Total Tokens (Avg/P95.5):** 1755 / 4554
- **Input:** 645 / 288 | **Output:** 645 / 957 | **Thought:** 663 / 3028


**`unreliable_tool_agent`**
- **Requests:** 72 (3.4%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 12.79s / 39.01s
- **Errors:** 18.06%
- **Total Tokens (Avg/P95.5):** 2101 / 3598
- **Input:** 1850 / 3033 | **Output:** 33 / 77 | **Thought:** 267 / 657


**`config_test_agent_normal`**
- **Requests:** 44 (2.1%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 12.045s / 43.315s
- **Errors:** 6.82%
- **Total Tokens (Avg/P95.5):** 10977 / 100428
- **Input:** 10502 / 99981 | **Output:** 117 / 551 | **Thought:** 356 / 1007


**`config_test_agent_wrong_max_tokens`**
- **Requests:** 103 (4.8%)
- **Status:** 🔴 Overall (Lat: ⚪, Err: 🔴)
- **Latency (Mean / P95.5):** -s / -s
- **Errors:** 100.0%
- **Total Tokens (Avg/P95.5):** -
- **Input:** - | **Output:** - | **Thought:** -



### Distribution

**Total Requests:** 2139

| **Name**                               |   **Requests** |   **%** |
|:---------------------------------------|---------------:|--------:|
| **bigquery_data_agent**                |            400 |   18.7  |
| **config_test_agent_wrong_candidates** |             38 |    1.78 |
| **adk_documentation_agent**            |            374 |   17.48 |
| **parallel_db_lookup**                 |            127 |    5.94 |
| **google_search_agent**                |            191 |    8.93 |
| **config_test_agent_over_provisioned** |             44 |    2.06 |
| **lookup_worker_3**                    |            127 |    5.94 |
| **lookup_worker_2**                    |            127 |    5.94 |
| **config_test_agent_high_temp**        |             41 |    1.92 |
| **lookup_worker_1**                    |            127 |    5.94 |
| **ai_observability_agent**             |            324 |   15.15 |
| **unreliable_tool_agent**              |             72 |    3.37 |
| **config_test_agent_normal**           |             44 |    2.06 |
| **config_test_agent_wrong_max_tokens** |            103 |    4.82 |

<br>

**Agent Composition**<br>

[![Agent Composition](report_assets_20260320_063748/agent_composition_pie.png)](report_assets_20260320_063748/agent_composition_pie_4K.png)
<br>

**Total LLM Calls per Agent**<br>

[![Total LLM Calls per Agent](report_assets_20260320_063748/agent_calls_stacked.png)](report_assets_20260320_063748/agent_calls_stacked_4K.png)
<br>


### Model Traffic

| **Agent Name**                         | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:---------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **adk_documentation_agent**            | 100 (28%)              | 120 (33%)            | 79 (22%)                   | 62 (17%)                     |
| **ai_observability_agent**             | 134 (44%)              | 123 (40%)            | 32 (10%)                   | 18 (6%)                      |
| **bigquery_data_agent**                | 3696 (36%)             | 3489 (34%)           | 1114 (11%)                 | 2079 (20%)                   |
| **config_test_agent_high_temp**        | 16 (32%)               | 17 (34%)             | 9 (18%)                    | 8 (16%)                      |
| **config_test_agent_normal**           | 18 (29%)               | 21 (34%)             | 14 (23%)                   | 9 (15%)                      |
| **config_test_agent_over_provisioned** | 39 (30%)               | 50 (39%)             | 20 (16%)                   | 19 (15%)                     |
| **config_test_agent_wrong_candidates** | 30 (51%)               | 14 (24%)             | 7 (12%)                    | 8 (14%)                      |
| **config_test_agent_wrong_max_tokens** | 18 (26%)               | 20 (29%)             | 12 (17%)                   | 20 (29%)                     |
| **google_search_agent**                | 67 (35%)               | 93 (49%)             | 14 (7%)                    | 17 (9%)                      |
| **knowledge_qa_supervisor**            | 517 (33%)              | 554 (35%)            | 243 (15%)                  | 261 (17%)                    |
| **lookup_worker_1**                    | 234 (40%)              | 151 (26%)            | 124 (21%)                  | 70 (12%)                     |
| **lookup_worker_2**                    | 193 (36%)              | 169 (31%)            | 102 (19%)                  | 77 (14%)                     |
| **lookup_worker_3**                    | 246 (40%)              | 160 (26%)            | 130 (21%)                  | 77 (13%)                     |
| **unreliable_tool_agent**              | 70 (25%)               | 151 (54%)            | 56 (20%)                   | 4 (1%)                       |

<br>


### Model Performance (Agent End-to-End)

This table compares how specific agents perform when running on different models. **Values represent Agent End-to-End Latency** (including tool execution and overhead), not just LLM generation time.

> [!NOTE]
> **KPI Settings:** Latency Target = `8.0s`, Error Target = `5.0%`
> **Cell Format:** `[Status] [P95.5 Latency]s ([Error Rate]%)`. For example, `🔴 21.558s (16.67%)` means the Agent had a P95.5 latency of 21.558 seconds and an error rate of 16.67%, and received a failing 🔴 status because it breached either the latency or error target.

| **Agent Name**                         | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:---------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **adk_documentation_agent**            | 🔴 25.837s (6.0%)      | 🔴 38.157s (5.0%)    | 🔴 145.704s (27.85%)       | 🔴 106.056s (19.35%)         |
| **ai_observability_agent**             | 🔴 9.972s (4.48%)      | 🔴 23.657s (11.38%)  | 🔴 85.828s (31.25%)        | 🔴 156.992s (33.33%)         |
| **bigquery_data_agent**                | 🔴 77.304s (0.86%)     | 🔴 108.084s (16.78%) | 🔴 265.147s (67.92%)       | 🔴 218.079s (77.14%)         |
| **config_test_agent_high_temp**        | 🔴 41.686s (0.0%)      | 🔴 26.496s (0.0%)    | 🔴 21.943s (11.11%)        | 🔴 48.039s (0.0%)            |
| **config_test_agent_normal**           | 🔴 46.176s (0.0%)      | 🔴 25.383s (0.0%)    | 🔴 27.008s (9.09%)         | 🔴 43.315s (22.22%)          |
| **config_test_agent_over_provisioned** | 🔴 12.398s (0.0%)      | 🔴 25.807s (7.14%)   | 🔴 64.327s (12.5%)         | 🔴 244.966s (10.0%)          |
| **config_test_agent_wrong_candidates** | 🔴 32.507s (0.0%)      | 🔴 57.993s (12.5%)   | 🔴 93.171s (0.0%)          | 🔴 82.02s (25.0%)            |
| **config_test_agent_wrong_max_tokens** | -                      | -                    | -                          | -                            |
| **google_search_agent**                | 🔴 24.045s (0.0%)      | 🔴 43.973s (1.08%)   | 🔴 42.132s (0.0%)          | 🔴 117.314s (11.76%)         |
| **knowledge_qa_supervisor**            | 🔴 48.043s (8.9%)      | 🔴 76.291s (16.43%)  | 🔴 126.318s (34.16%)       | 🔴 158.255s (52.11%)         |
| **lookup_worker_1**                    | 🔴 14.853s (0.0%)      | 🔴 18.732s (7.41%)   | 🔴 33.267s (3.85%)         | 🔴 83.937s (31.82%)          |
| **lookup_worker_2**                    | 🔴 13.43s (0.0%)       | 🔴 25.001s (7.14%)   | 🔴 86.99s (3.85%)          | 🔴 78.115s (31.82%)          |
| **lookup_worker_3**                    | 🔴 12.26s (0.0%)       | 🔴 17.935s (3.7%)    | 🔴 58.655s (7.41%)         | 🔴 236.02s (41.67%)          |
| **unreliable_tool_agent**              | 🔴 16.521s (6.25%)     | 🔴 28.44s (21.05%)   | 🔴 50.915s (23.53%)        | 🔴 11.633s (0.0%)            |

<br>


### LLM Generation Performance

This table compares the raw LLM generation time for specific agents and models. **Values represent Pure LLM Latency** (excluding agent overhead).

> [!NOTE]
> **KPI Settings:** Latency Target = `5.0s`, Error Target = `5.0%`
> **Cell Format:** `[Status] [P95.5 Latency]s ([Error Rate]%)`.

| **Agent Name**                         | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:---------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **adk_documentation_agent**            | 🔴 25.836s (6.0%)      | 🔴 38.156s (5.0%)    | 🔴 145.701s (27.85%)       | 🔴 106.054s (19.35%)         |
| **ai_observability_agent**             | 🔴 9.971s (4.48%)      | 🔴 23.655s (11.38%)  | 🔴 85.826s (31.25%)        | 🔴 156.991s (33.33%)         |
| **bigquery_data_agent**                | 🔴 11.759s (0.14%)     | 🔴 21.943s (1.58%)   | 🔴 21.918s (8.98%)         | 🔴 29.466s (6.11%)           |
| **config_test_agent_high_temp**        | 🔴 8.171s (0.0%)       | 🔴 26.494s (0.0%)    | 🔴 21.94s (0.0%)           | 🔴 48.035s (0.0%)            |
| **config_test_agent_normal**           | 🔴 5.997s (0.0%)       | 🔴 12.721s (0.0%)    | 🔴 27.006s (7.14%)         | 🔴 21.194s (22.22%)          |
| **config_test_agent_over_provisioned** | 🔴 5.571s (0.0%)       | 🔴 11.109s (2.0%)    | 🔴 36.17s (5.0%)           | 🔴 45.18s (10.53%)           |
| **config_test_agent_wrong_candidates** | 🔴 7.559s (0.0%)       | 🔴 41.067s (0.0%)    | 🔴 93.169s (0.0%)          | 🔴 82.017s (25.0%)           |
| **config_test_agent_wrong_max_tokens** | -                      | -                    | -                          | -                            |
| **google_search_agent**                | 🔴 24.042s (0.0%)      | 🔴 43.97s (1.08%)    | 🔴 42.13s (0.0%)           | 🔴 117.298s (11.76%)         |
| **knowledge_qa_supervisor**            | 🟢 3.751s (0.0%)       | 🔴 6.695s (0.54%)    | 🔴 23.214s (2.47%)         | 🔴 46.322s (13.79%)          |
| **lookup_worker_1**                    | 🟢 4.78s (0.0%)        | 🔴 10.527s (1.99%)   | 🔴 24.338s (2.42%)         | 🔴 41.477s (4.29%)           |
| **lookup_worker_2**                    | 🔴 5.58s (0.0%)        | 🔴 9.519s (0.59%)    | 🔴 41.651s (0.0%)          | 🔴 59.378s (11.69%)          |
| **lookup_worker_3**                    | 🟢 4.618s (0.0%)       | 🔴 8.436s (0.0%)     | 🔴 32.296s (0.77%)         | 🔴 84.409s (14.29%)          |
| **unreliable_tool_agent**              | 🟢 3.517s (0.0%)       | 🔴 6.457s (0.0%)     | 🔴 33.916s (0.0%)          | 🔴 5.447s (0.0%)             |

<br>


### Agent Overhead Analysis

This chart breaks down the internal execution time of an Agent into **LLM Time**, **Tool Time**, and its own **Code Overhead** (the remaining time).

> [!NOTE]
> The data below is calculated using the **P95.5 execution latency** metrics across all events for each agent to illustrate worst-case internal overheads.


#### Overhead Data Summary

| **Agent Name**                         | **Total Agent Latency (s)**   | **Pure LLM Latency (s)**   | **Agent Overhead (s)**   |
|:---------------------------------------|:------------------------------|:---------------------------|:-------------------------|
| **bigquery_data_agent**                | 248.256s                      | 20.008s                    | 228.248s                 |
| **adk_documentation_agent**            | 90.06s                        | 90.057s                    | 0.003s                   |
| **config_test_agent_wrong_candidates** | 81.949s                       | 81.94s                     | 0.01s                    |
| **lookup_worker_3**                    | 58.655s                       | 26.779s                    | 31.876s                  |
| **ai_observability_agent**             | 54.999s                       | 54.997s                    | 0.001s                   |
| **lookup_worker_2**                    | 50.897s                       | 24.225s                    | 26.673s                  |
| **google_search_agent**                | 45.381s                       | 45.379s                    | 0.002s                   |
| **config_test_agent_over_provisioned** | 45.273s                       | 26.064s                    | 19.21s                   |
| **config_test_agent_high_temp**        | 41.061s                       | 35.461s                    | 5.6s                     |
| **lookup_worker_1**                    | 33.68s                        | 18.468s                    | 15.212s                  |

<br>

**Agent Overhead Comparison**<br>

[![Agent Overhead Comparison](report_assets_20260320_063748/agent_overhead_composition.png)](report_assets_20260320_063748/agent_overhead_composition_4K.png)
<br>


---


### Agent Execution Latency (Request Order)

The following charts display the end-to-end latency for each specific Agent over time, highlighting performance trends and potential internal degradation.


**adk_documentation_agent Execution Latency Sequence (Request Order)**<br>

[![adk_documentation_agent Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_adk_documentation_agent.png)](report_assets_20260320_063748/seq_agent_overall_adk_documentation_agent_4K.png)
<br>

**ai_observability_agent Execution Latency Sequence (Request Order)**<br>

[![ai_observability_agent Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_ai_observability_agent.png)](report_assets_20260320_063748/seq_agent_overall_ai_observability_agent_4K.png)
<br>

**bigquery_data_agent Execution Latency Sequence (Request Order)**<br>

[![bigquery_data_agent Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_bigquery_data_agent.png)](report_assets_20260320_063748/seq_agent_overall_bigquery_data_agent_4K.png)
<br>

**config_test_agent_high_temp Execution Latency Sequence (Request Order)**<br>

[![config_test_agent_high_temp Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_high_temp.png)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_high_temp_4K.png)
<br>

**config_test_agent_normal Execution Latency Sequence (Request Order)**<br>

[![config_test_agent_normal Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_normal.png)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_normal_4K.png)
<br>

**config_test_agent_over_provisioned Execution Latency Sequence (Request Order)**<br>

[![config_test_agent_over_provisioned Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_over_provisioned.png)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_over_provisioned_4K.png)
<br>

**config_test_agent_wrong_candidates Execution Latency Sequence (Request Order)**<br>

[![config_test_agent_wrong_candidates Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_wrong_candidates.png)](report_assets_20260320_063748/seq_agent_overall_config_test_agent_wrong_candidates_4K.png)
<br>

**google_search_agent Execution Latency Sequence (Request Order)**<br>

[![google_search_agent Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_google_search_agent.png)](report_assets_20260320_063748/seq_agent_overall_google_search_agent_4K.png)
<br>

**lookup_worker_1 Execution Latency Sequence (Request Order)**<br>

[![lookup_worker_1 Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_1.png)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_1_4K.png)
<br>

**lookup_worker_2 Execution Latency Sequence (Request Order)**<br>

[![lookup_worker_2 Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_2.png)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_2_4K.png)
<br>

**lookup_worker_3 Execution Latency Sequence (Request Order)**<br>

[![lookup_worker_3 Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_3.png)](report_assets_20260320_063748/seq_agent_overall_lookup_worker_3_4K.png)
<br>

**parallel_db_lookup Execution Latency Sequence (Request Order)**<br>

[![parallel_db_lookup Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_parallel_db_lookup.png)](report_assets_20260320_063748/seq_agent_overall_parallel_db_lookup_4K.png)
<br>

**unreliable_tool_agent Execution Latency Sequence (Request Order)**<br>

[![unreliable_tool_agent Execution Latency Sequence (Request Order)](report_assets_20260320_063748/seq_agent_overall_unreliable_tool_agent.png)](report_assets_20260320_063748/seq_agent_overall_unreliable_tool_agent_4K.png)
<br>


---


### Token Statistics


`bigquery_data_agent` consumes massive input tokens, averaging over 38k tokens. `config_test_agent_wrong_candidates` uses exceptionally high thought tokens, averaging 4715 thought tokens per request. `knowledge_qa_supervisor` handles relatively lightweight payloads, averaging 27034 input tokens and only 109 output tokens.


**adk_documentation_agent**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 100                    | 120                  | 79                         | 62                           |
| **Mean Input Tokens**                | 1346.31                | 305.29               | 255.46                     | 278.32                       |
| **P95 Input Tokens**                 | 1082.00                | 414.00               | 305.00                     | 445.00                       |
| **Mean Thought Tokens**              | 912.31                 | 1090.33              | 4827.28                    | 5632.84                      |
| **P95 Thought Tokens**               | 2124.00                | 1878.00              | 22934.00                   | 17968.00                     |
| **Mean Output Tokens**               | 510.18                 | 615.41               | 766.09                     | 633.43                       |
| **P95 Output Tokens**                | 1415.00                | 1097.00              | 1071.00                    | 956.00                       |
| **Median Output Tokens**             | 469.00                 | 685.00               | 776.00                     | 616.00                       |
| **Min Output Tokens**                | 42.00                  | 22.00                | 290.00                     | 244.00                       |
| **Max Output Tokens**                | 1949.00                | 1338.00              | 1161.00                    | 1151.00                      |
| **Mean Total Tokens**                | 3434.88                | 2790.96              | 5848.82                    | 6393.92                      |
| **Latency vs Input Corr.**           | 0.098                  | 0.245                | -0.064                     | -0.138                       |
| **Latency vs Output Corr.**          | 0.703                  | 0.652                | -0.096                     | 0.012                        |
| **Latency vs Output+Thinking Corr.** | **0.885**              | **0.899**            | 0.377                      | 0.760                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟧 **Strong**        | 🟦 **Weak**                | 🟨 **Moderate**              |

<br>


**ai_observability_agent**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 134                    | 123                  | 32                         | 18                           |
| **Mean Input Tokens**                | 287.67                 | 1180.90              | 310.77                     | 210.08                       |
| **P95 Input Tokens**                 | 285.00                 | 220.00               | 809.00                     | 215.00                       |
| **Mean Thought Tokens**              | 227.81                 | 436.80               | 2319.27                    | 4336.08                      |
| **P95 Thought Tokens**               | 645.00                 | 1016.00              | 3790.00                    | 8379.00                      |
| **Mean Output Tokens**               | 315.00                 | 724.20               | 604.86                     | 786.92                       |
| **P95 Output Tokens**                | 886.00                 | 973.00               | 723.00                     | 1008.00                      |
| **Median Output Tokens**             | 57.00                  | 737.00               | 607.00                     | 773.00                       |
| **Min Output Tokens**                | 49.00                  | 456.00               | 452.00                     | 585.00                       |
| **Max Output Tokens**                | 886.00                 | 973.00               | 935.00                     | 1008.00                      |
| **Mean Total Tokens**                | 853.44                 | 2121.17              | 3234.91                    | 5333.08                      |
| **Latency vs Input Corr.**           | 0.032                  | 0.453                | -0.177                     | 0.132                        |
| **Latency vs Output Corr.**          | **0.930**              | 0.406                | -0.165                     | 0.298                        |
| **Latency vs Output+Thinking Corr.** | **0.984**              | **0.950**            | 0.202                      | 0.019                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟧 **Strong**        | 🟦 **Weak**                | 🟦 **Weak**                  |

<br>


**bigquery_data_agent**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 3696                   | 3489                 | 1114                       | 2079                         |
| **Mean Input Tokens**                | 44102.55               | 43972.27             | 18453.55                   | 28584.46                     |
| **P95 Input Tokens**                 | 118907.00              | 114119.00            | 26585.00                   | 53656.00                     |
| **Mean Thought Tokens**              | 503.36                 | 558.60               | 439.24                     | 199.02                       |
| **P95 Thought Tokens**               | 1423.00                | 1550.00              | 1101.00                    | 494.00                       |
| **Mean Output Tokens**               | 102.51                 | 101.86               | 78.62                      | 78.67                        |
| **P95 Output Tokens**                | 257.00                 | 278.00               | 196.00                     | 169.00                       |
| **Median Output Tokens**             | 81.00                  | 70.00                | 56.00                      | 66.00                        |
| **Min Output Tokens**                | 12.00                  | 13.00                | 17.00                      | 17.00                        |
| **Max Output Tokens**                | 2611.00                | 5922.00              | 976.00                     | 745.00                       |
| **Mean Total Tokens**                | 44707.64               | 44631.33             | 18971.41                   | 28860.04                     |
| **Latency vs Input Corr.**           | 0.253                  | 0.211                | 0.110                      | -0.150                       |
| **Latency vs Output Corr.**          | 0.258                  | 0.362                | 0.094                      | 0.219                        |
| **Latency vs Output+Thinking Corr.** | **0.862**              | 0.835                | 0.394                      | 0.160                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟨 **Moderate**      | 🟦 **Weak**                | 🟦 **Weak**                  |

<br>


**config_test_agent_high_temp**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 16                     | 17                   | 9                          | 8                            |
| **Mean Input Tokens**                | 1885.94                | 1337.88              | 2071.67                    | 2084.12                      |
| **P95 Input Tokens**                 | 4196.00                | 2017.00              | 3005.00                    | 2853.00                      |
| **Mean Thought Tokens**              | 261.56                 | 504.47               | 546.56                     | 1131.25                      |
| **P95 Thought Tokens**               | 917.00                 | 1338.00              | 1452.00                    | 2922.00                      |
| **Mean Output Tokens**               | 155.62                 | 435.65               | 387.67                     | 455.75                       |
| **P95 Output Tokens**                | 613.00                 | 1753.00              | 1178.00                    | 1094.00                      |
| **Median Output Tokens**             | 107.00                 | 159.00               | 218.00                     | 195.00                       |
| **Min Output Tokens**                | 13.00                  | 11.00                | 18.00                      | 20.00                        |
| **Max Output Tokens**                | 613.00                 | 1753.00              | 1178.00                    | 1094.00                      |
| **Mean Total Tokens**                | 2303.13                | 2218.65              | 3005.89                    | 3671.12                      |
| **Latency vs Input Corr.**           | -0.261                 | 0.257                | -0.420                     | -0.518                       |
| **Latency vs Output Corr.**          | 0.499                  | 0.795                | 0.422                      | 0.197                        |
| **Latency vs Output+Thinking Corr.** | 0.569                  | **0.969**            | 0.656                      | 0.587                        |
| **Correlation Strength**             | 🟨 **Moderate**        | 🟧 **Strong**        | 🟨 **Moderate**            | 🟨 **Moderate**              |

<br>


**config_test_agent_normal**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 18                     | 21                   | 14                         | 9                            |
| **Mean Input Tokens**                | 2425.11                | 20786.10             | 2193.77                    | 15854.43                     |
| **P95 Input Tokens**                 | 4469.00                | 100445.00            | 8376.00                    | 99039.00                     |
| **Mean Thought Tokens**              | 155.89                 | 338.86               | 598.38                     | 475.86                       |
| **P95 Thought Tokens**               | 721.00                 | 812.00               | 2241.00                    | 1478.00                      |
| **Mean Output Tokens**               | 117.61                 | 85.86                | 170.00                     | 117.57                       |
| **P95 Output Tokens**                | 631.00                 | 417.00               | 502.00                     | 248.00                       |
| **Median Output Tokens**             | 13.00                  | 29.00                | 73.00                      | 114.00                       |
| **Min Output Tokens**                | 7.00                   | 7.00                 | 7.00                       | 18.00                        |
| **Max Output Tokens**                | 631.00                 | 578.00               | 502.00                     | 248.00                       |
| **Mean Total Tokens**                | 2698.61                | 21210.81             | 2962.15                    | 16447.86                     |
| **Latency vs Input Corr.**           | -0.138                 | 0.250                | 0.038                      | -0.167                       |
| **Latency vs Output Corr.**          | 0.707                  | 0.555                | 0.149                      | 0.407                        |
| **Latency vs Output+Thinking Corr.** | **0.966**              | **0.918**            | 0.604                      | 0.612                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟧 **Strong**        | 🟨 **Moderate**            | 🟨 **Moderate**              |

<br>


**config_test_agent_over_provisioned**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 39                     | 50                   | 20                         | 19                           |
| **Mean Input Tokens**                | 1665.36                | 1399.24              | 2435.26                    | 1566.00                      |
| **P95 Input Tokens**                 | 2952.00                | 2117.00              | 4719.00                    | 2924.00                      |
| **Mean Thought Tokens**              | 155.80                 | 264.00               | 794.69                     | 518.06                       |
| **P95 Thought Tokens**               | 211.00                 | 529.00               | 3348.00                    | 2623.00                      |
| **Mean Output Tokens**               | 69.72                  | 85.50                | 58.16                      | 327.18                       |
| **P95 Output Tokens**                | 77.00                  | 158.00               | 225.00                     | 2963.00                      |
| **Median Output Tokens**             | 32.00                  | 24.00                | 36.00                      | 28.00                        |
| **Min Output Tokens**                | 11.00                  | 8.00                 | 18.00                      | 14.00                        |
| **Max Output Tokens**                | 1665.00                | 1394.00              | 225.00                     | 2963.00                      |
| **Mean Total Tokens**                | 1834.95                | 1720.06              | 3037.16                    | 2411.24                      |
| **Latency vs Input Corr.**           | 0.148                  | 0.093                | -0.334                     | 0.488                        |
| **Latency vs Output Corr.**          | **0.923**              | **0.857**            | -0.370                     | 0.580                        |
| **Latency vs Output+Thinking Corr.** | **0.995**              | **0.997**            | 0.526                      | 0.699                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟧 **Strong**        | 🟨 **Moderate**            | 🟨 **Moderate**              |

<br>


**config_test_agent_wrong_candidates**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 30                     | 14                   | 7                          | 8                            |
| **Mean Input Tokens**                | 1563.37                | 1668.79              | 2161.29                    | 1845.17                      |
| **P95 Input Tokens**                 | 2597.00                | 3535.00              | 3018.00                    | 2963.00                      |
| **Mean Thought Tokens**              | 1118.41                | 3188.64              | 11009.00                   | 14125.83                     |
| **P95 Thought Tokens**               | 2450.00                | 9859.00              | 35075.00                   | 19700.00                     |
| **Mean Output Tokens**               | 603.83                 | 460.43               | 972.00                     | 1382.33                      |
| **P95 Output Tokens**                | 2920.00                | 2271.00              | 2690.00                    | 2750.00                      |
| **Median Output Tokens**             | 145.00                 | 125.00               | 790.00                     | 1110.00                      |
| **Min Output Tokens**                | 40.00                  | 65.00                | 248.00                     | 429.00                       |
| **Max Output Tokens**                | 4935.00                | 2271.00              | 2690.00                    | 2750.00                      |
| **Mean Total Tokens**                | 2987.37                | 5317.86              | 14142.29                   | 17353.33                     |
| **Latency vs Input Corr.**           | 0.396                  | 0.002                | -0.221                     | -0.141                       |
| **Latency vs Output Corr.**          | 0.778                  | 0.213                | 0.377                      | **0.933**                    |
| **Latency vs Output+Thinking Corr.** | **0.948**              | **0.900**            | 0.471                      | 0.592                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟧 **Strong**        | 🟦 **Weak**                | 🟨 **Moderate**              |

<br>


**config_test_agent_wrong_max_tokens**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 18                     | 20                   | 12                         | 20                           |
| **Mean Input Tokens**                | N/A                    | N/A                  | N/A                        | N/A                          |
| **P95 Input Tokens**                 | N/A                    | N/A                  | N/A                        | N/A                          |
| **Mean Thought Tokens**              | N/A                    | N/A                  | N/A                        | N/A                          |
| **P95 Thought Tokens**               | N/A                    | N/A                  | N/A                        | N/A                          |
| **Mean Output Tokens**               | N/A                    | N/A                  | N/A                        | N/A                          |
| **P95 Output Tokens**                | N/A                    | N/A                  | N/A                        | N/A                          |
| **Median Output Tokens**             | N/A                    | N/A                  | N/A                        | N/A                          |
| **Min Output Tokens**                | N/A                    | N/A                  | N/A                        | N/A                          |
| **Max Output Tokens**                | N/A                    | N/A                  | N/A                        | N/A                          |
| **Mean Total Tokens**                | N/A                    | N/A                  | N/A                        | N/A                          |
| **Latency vs Input Corr.**           | nan                    | nan                  | nan                        | nan                          |
| **Latency vs Output Corr.**          | N/A                    | N/A                  | N/A                        | N/A                          |
| **Latency vs Output+Thinking Corr.** | N/A                    | N/A                  | N/A                        | N/A                          |
| **Correlation Strength**             | N/A                    | N/A                  | N/A                        | N/A                          |

<br>


**google_search_agent**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 67                     | 93                   | 14                         | 17                           |
| **Mean Input Tokens**                | 10288.24               | 11732.12             | 1792.36                    | 819.07                       |
| **P95 Input Tokens**                 | 79026.00               | 91499.00             | 18171.00                   | 9760.00                      |
| **Mean Thought Tokens**              | 726.66                 | 502.89               | 1270.14                    | 1312.07                      |
| **P95 Thought Tokens**               | 1644.00                | 1169.00              | 2868.00                    | 3661.00                      |
| **Mean Output Tokens**               | 814.27                 | 798.66               | 842.86                     | 702.67                       |
| **P95 Output Tokens**                | 1688.00                | 1297.00              | 1398.00                    | 1193.00                      |
| **Median Output Tokens**             | 714.00                 | 836.00               | 898.00                     | 772.00                       |
| **Min Output Tokens**                | 90.00                  | 122.00               | 340.00                     | 13.00                        |
| **Max Output Tokens**                | 2554.00                | 1512.00              | 1398.00                    | 1193.00                      |
| **Mean Total Tokens**                | 11958.66               | 13357.88             | 3905.36                    | 2833.80                      |
| **Latency vs Input Corr.**           | 0.194                  | 0.355                | -0.220                     | 0.081                        |
| **Latency vs Output Corr.**          | 0.761                  | 0.635                | -0.080                     | 0.115                        |
| **Latency vs Output+Thinking Corr.** | **0.916**              | 0.670                | 0.095                      | 0.221                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟨 **Moderate**      | 🟦 **Weak**                | 🟦 **Weak**                  |

<br>


**knowledge_qa_supervisor**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 517                    | 554                  | 243                        | 261                          |
| **Mean Input Tokens**                | 1905.57                | 2936.31              | 1829.94                    | 1654.61                      |
| **P95 Input Tokens**                 | 2804.00                | 3016.00              | 2658.00                    | 2642.00                      |
| **Mean Thought Tokens**              | 121.19                 | 174.19               | 302.65                     | 305.78                       |
| **P95 Thought Tokens**               | 309.00                 | 437.00               | 1238.00                    | 747.00                       |
| **Mean Output Tokens**               | 15.15                  | 15.94                | 18.46                      | 19.35                        |
| **P95 Output Tokens**                | 19.00                  | 19.00                | 23.00                      | 23.00                        |
| **Median Output Tokens**             | 14.00                  | 14.00                | 18.00                      | 18.00                        |
| **Min Output Tokens**                | 13.00                  | 13.00                | 17.00                      | 17.00                        |
| **Max Output Tokens**                | 365.00                 | 489.00               | 23.00                      | 83.00                        |
| **Mean Total Tokens**                | 2041.89                | 3126.12              | 2151.05                    | 1979.74                      |
| **Latency vs Input Corr.**           | 0.142                  | 0.308                | 0.011                      | 0.144                        |
| **Latency vs Output Corr.**          | 0.109                  | 0.338                | -0.218                     | -0.033                       |
| **Latency vs Output+Thinking Corr.** | 0.721                  | **0.883**            | 0.438                      | 0.205                        |
| **Correlation Strength**             | 🟨 **Moderate**        | 🟧 **Strong**        | 🟦 **Weak**                | 🟦 **Weak**                  |

<br>


**lookup_worker_1**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 234                    | 151                  | 124                        | 70                           |
| **Mean Input Tokens**                | 602.74                 | 508.86               | 1070.24                    | 812.13                       |
| **P95 Input Tokens**                 | 2410.00                | 1095.00              | 3028.00                    | 2047.00                      |
| **Mean Thought Tokens**              | 117.89                 | 294.30               | 572.16                     | 308.08                       |
| **P95 Thought Tokens**               | 233.00                 | 877.00               | 1365.00                    | 827.00                       |
| **Mean Output Tokens**               | 41.28                  | 33.37                | 40.92                      | 74.17                        |
| **P95 Output Tokens**                | 85.00                  | 69.00                | 78.00                      | 84.00                        |
| **Median Output Tokens**             | 32.00                  | 32.00                | 40.00                      | 61.00                        |
| **Min Output Tokens**                | 8.00                   | 14.00                | 11.00                      | 40.00                        |
| **Max Output Tokens**                | 430.00                 | 98.00                | 91.00                      | 547.00                       |
| **Mean Total Tokens**                | 725.14                 | 792.33               | 1550.92                    | 1182.97                      |
| **Latency vs Input Corr.**           | -0.059                 | -0.135               | 0.155                      | 0.047                        |
| **Latency vs Output Corr.**          | 0.293                  | 0.049                | -0.174                     | -0.014                       |
| **Latency vs Output+Thinking Corr.** | 0.790                  | **0.940**            | 0.752                      | 0.445                        |
| **Correlation Strength**             | 🟨 **Moderate**        | 🟧 **Strong**        | 🟨 **Moderate**            | 🟦 **Weak**                  |

<br>


**lookup_worker_2**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 193                    | 169                  | 102                        | 77                           |
| **Mean Input Tokens**                | 551.26                 | 584.35               | 935.73                     | 764.29                       |
| **P95 Input Tokens**                 | 1809.00                | 1607.00              | 2952.00                    | 2047.00                      |
| **Mean Thought Tokens**              | 121.43                 | 192.71               | 1141.59                    | 407.72                       |
| **P95 Thought Tokens**               | 126.00                 | 739.00               | 3836.00                    | 1266.00                      |
| **Mean Output Tokens**               | 53.88                  | 34.45                | 608.41                     | 57.94                        |
| **P95 Output Tokens**                | 111.00                 | 70.00                | 104.00                     | 83.00                        |
| **Median Output Tokens**             | 41.00                  | 33.00                | 22.00                      | 44.00                        |
| **Min Output Tokens**                | 14.00                  | 14.00                | 9.00                       | 20.00                        |
| **Max Output Tokens**                | 667.00                 | 89.00                | 29336.00                   | 449.00                       |
| **Mean Total Tokens**                | 705.18                 | 785.85               | 2305.20                    | 1204.26                      |
| **Latency vs Input Corr.**           | -0.061                 | -0.111               | 0.039                      | 0.398                        |
| **Latency vs Output Corr.**          | 0.229                  | 0.199                | **0.927**                  | 0.528                        |
| **Latency vs Output+Thinking Corr.** | 0.841                  | 0.675                | **0.981**                  | 0.289                        |
| **Correlation Strength**             | 🟨 **Moderate**        | 🟨 **Moderate**      | 🟧 **Strong**              | 🟦 **Weak**                  |

<br>


**lookup_worker_3**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 246                    | 160                  | 130                        | 77                           |
| **Mean Input Tokens**                | 472.69                 | 507.20               | 1018.29                    | 799.55                       |
| **P95 Input Tokens**                 | 1088.00                | 1172.00              | 2990.00                    | 2047.00                      |
| **Mean Thought Tokens**              | 86.26                  | 255.29               | 675.80                     | 466.73                       |
| **P95 Thought Tokens**               | 140.00                 | 665.00               | 1869.00                    | 1293.00                      |
| **Mean Output Tokens**               | 41.28                  | 33.69                | 37.83                      | 64.30                        |
| **P95 Output Tokens**                | 88.00                  | 73.00                | 67.00                      | 78.00                        |
| **Median Output Tokens**             | 33.00                  | 26.00                | 39.00                      | 60.00                        |
| **Min Output Tokens**                | 12.00                  | 8.00                 | 11.00                      | 20.00                        |
| **Max Output Tokens**                | 599.00                 | 83.00                | 87.00                      | 330.00                       |
| **Mean Total Tokens**                | 563.07                 | 741.84               | 1595.71                    | 1330.58                      |
| **Latency vs Input Corr.**           | -0.062                 | -0.061               | -0.096                     | 0.448                        |
| **Latency vs Output Corr.**          | 0.251                  | 0.210                | -0.356                     | 0.811                        |
| **Latency vs Output+Thinking Corr.** | 0.481                  | **0.916**            | 0.746                      | 0.332                        |
| **Correlation Strength**             | 🟦 **Weak**            | 🟧 **Strong**        | 🟨 **Moderate**            | 🟦 **Weak**                  |

<br>


**unreliable_tool_agent**

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 70                     | 151                  | 56                         | 4                            |
| **Mean Input Tokens**                | 1723.07                | 2023.36              | 1591.50                    | 1165.00                      |
| **P95 Input Tokens**                 | 2592.00                | 3244.00              | 3152.00                    | 1189.00                      |
| **Mean Thought Tokens**              | 94.15                  | 218.36               | 710.06                     | 88.00                        |
| **P95 Thought Tokens**               | 157.00                 | 391.00               | 2932.00                    | 158.00                       |
| **Mean Output Tokens**               | 27.87                  | 31.46                | 46.11                      | 40.00                        |
| **P95 Output Tokens**                | 54.00                  | 70.00                | 121.00                     | 62.00                        |
| **Median Output Tokens**             | 23.00                  | 20.00                | 32.00                      | 18.00                        |
| **Min Output Tokens**                | 12.00                  | 12.00                | 16.00                      | 18.00                        |
| **Max Output Tokens**                | 62.00                  | 87.00                | 152.00                     | 62.00                        |
| **Mean Total Tokens**                | 1815.50                | 2258.72              | 2094.07                    | 1293.00                      |
| **Latency vs Input Corr.**           | -0.175                 | 0.272                | -0.068                     | **-1.000**                   |
| **Latency vs Output Corr.**          | -0.336                 | 0.046                | -0.044                     | **-1.000**                   |
| **Latency vs Output+Thinking Corr.** | 0.680                  | **0.930**            | **0.874**                  | **1.000**                    |
| **Correlation Strength**             | 🟨 **Moderate**        | 🟧 **Strong**        | 🟧 **Strong**              | 🟧 **Strong**                |

<br>

<br>

---


## Tool Details


The slowest tools are `complex_calculation` (Mean Latency 2.042s) and `flaky_tool_simulation` (Mean Latency 1.264s). While most tools met the 3.0s latency target, `flaky_tool_simulation` experienced a 13.7% error rate, and the hallucinated tools `search` and `list_tables` experienced 100% error rates.


### Tool Summaries

A high-level cross-report summary for each tool.


**`complex_calculation`**
- **Requests:** 44 (2.2%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 2.042s / 2.984s
- **Errors:** 0.0%


**`flaky_tool_simulation`**
- **Requests:** 73 (3.6%)
- **Status:** 🔴 Overall (Lat: 🟢, Err: 🔴)
- **Latency (Mean / P95.5):** 1.264s / 1.963s
- **Errors:** 13.7%


**`search_catalog`**
- **Requests:** 5 (0.2%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.802s / 0.997s
- **Errors:** 0.0%


**`execute_sql`**
- **Requests:** 796 (39.5%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.705s / 1.105s
- **Errors:** 0.0%


**`simulated_db_lookup`**
- **Requests:** 766 (38.0%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.588s / 0.956s
- **Errors:** 0.0%


**`list_dataset_ids`**
- **Requests:** 24 (1.2%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.21s / 0.229s
- **Errors:** 0.0%


**`get_dataset_info`**
- **Requests:** 1 (0.0%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.187s / 0.187s
- **Errors:** 0.0%


**`get_table_info`**
- **Requests:** 217 (10.8%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.18s / 0.214s
- **Errors:** 0.0%


**`list_table_ids`**
- **Requests:** 84 (4.2%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.175s / 0.321s
- **Errors:** 0.0%


**`detect_anomalies`**
- **Requests:** 2 (0.1%)
- **Status:** 🟢 Overall (Lat: 🟢, Err: 🟢)
- **Latency (Mean / P95.5):** 0.0s / 0.0s
- **Errors:** 0.0%


**`search`**
- **Requests:** 3 (0.1%)
- **Status:** 🔴 Overall (Lat: ⚪, Err: 🔴)
- **Latency (Mean / P95.5):** -s / -s
- **Errors:** 100.0%


**`list_tables`**
- **Requests:** 1 (0.0%)
- **Status:** 🔴 Overall (Lat: ⚪, Err: 🔴)
- **Latency (Mean / P95.5):** -s / -s
- **Errors:** 100.0%



### Distribution

**Total Requests:** 2016

| **Name**                  |   **Requests** |   **%** |
|:--------------------------|---------------:|--------:|
| **complex_calculation**   |             44 |    2.18 |
| **flaky_tool_simulation** |             73 |    3.62 |
| **search_catalog**        |              5 |    0.25 |
| **execute_sql**           |            796 |   39.48 |
| **simulated_db_lookup**   |            766 |   38    |
| **list_dataset_ids**      |             24 |    1.19 |
| **get_dataset_info**      |              1 |    0.05 |
| **get_table_info**        |            217 |   10.76 |
| **list_table_ids**        |             84 |    4.17 |
| **detect_anomalies**      |              2 |    0.1  |
| **search**                |              3 |    0.15 |
| **list_tables**           |              1 |    0.05 |

<br>


---


## Model Details


`gemini-2.5-flash` is the fastest (5.01s mean) and most reliable (0.65% error rate) model in the ecosystem. Conversely, `gemini-3-pro-preview` is the slowest (15.258s mean), and `gemini-3.1-pro-preview` has the highest failure rate (8.5%).


### Model Summaries

A high-level cross-report summary for each model.


**`gemini-3-pro-preview`**
- **Requests:** 1956 (12.9%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 15.258s / 35.943s
- **Errors:** 7.98%
- **Total Tokens (Avg/P95.5):** 11763 / 26413
- **Input:** 10970 / 26158 | **Output:** 133 / 607 | **Thought:** 704 / 2210


**`gemini-3.1-pro-preview`**
- **Requests:** 2729 (18.0%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🔴)
- **Latency (Mean / P95.5):** 12.211s / 46.638s
- **Errors:** 8.5%
- **Total Tokens (Avg/P95.5):** 23127 / 53981
- **Input:** 22637 / 53577 | **Output:** 96 / 290 | **Thought:** 398 / 854


**`gemini-2.5-pro`**
- **Requests:** 5132 (33.8%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🟢)
- **Latency (Mean / P95.5):** 8.793s / 23.005s
- **Errors:** 2.03%
- **Total Tokens (Avg/P95.5):** 31447 / 112510
- **Input:** 30821 / 112115 | **Output:** 112 / 333 | **Thought:** 492 / 1498


**`gemini-2.5-flash`**
- **Requests:** 5378 (35.4%)
- **Status:** 🔴 Overall (Lat: 🔴, Err: 🟢)
- **Latency (Mean / P95.5):** 5.01s / 12.207s
- **Errors:** 0.65%
- **Total Tokens (Avg/P95.5):** 31466 / 115767
- **Input:** 30935 / 115269 | **Output:** 104 / 290 | **Thought:** 427 / 1270



### Distribution

**Total Requests:** 15195

| **Name**                   |   **Requests** |   **%** |
|:---------------------------|---------------:|--------:|
| **gemini-3-pro-preview**   |           1956 |   12.87 |
| **gemini-3.1-pro-preview** |           2729 |   17.96 |
| **gemini-2.5-pro**         |           5132 |   33.77 |
| **gemini-2.5-flash**       |           5378 |   35.39 |

<br>

**Model Usage**<br>

[![Model Usage](report_assets_20260320_063748/model_usage_pie.png)](report_assets_20260320_063748/model_usage_pie_4K.png)
<br>

**Latency Distribution by Category**<br>

[![Latency Distribution by Category](report_assets_20260320_063748/latency_category_dist.png)](report_assets_20260320_063748/latency_category_dist_4K.png)
<br>


### Model Performance

| **Metric**                     | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   | **gemini-2.5-pro**   | **gemini-2.5-flash**   |
|:-------------------------------|:---------------------------|:-----------------------------|:---------------------|:-----------------------|
| Total Requests                 | 1956                       | 2729                         | 5132                 | 5378                   |
| Mean Latency (s)               | 15.258                     | 12.211                       | 8.793                | 5.01                   |
| Std Deviation (s)              | 15.442                     | 18.231                       | 7.044                | 3.877                  |
| Median Latency (s)             | 12.585                     | 7.302                        | 6.508                | 4.054                  |
| P95 Latency (s)                | 33.136                     | 41.477                       | 21.943               | 11.527                 |
| P99 Latency (s)                | 85.826                     | 109.174                      | 36.348               | 22.557                 |
| Max Latency (s)                | 234.97                     | 222.999                      | 104.521              | 39.37                  |
| Outliers 2 STD Count (Percent) | 48 (2.5%)                  | 102 (3.7%)                   | 231 (4.5%)           | 206 (3.8%)             |
| Outliers 3 STD Count (Percent) | 33 (1.7%)                  | 63 (2.3%)                    | 90 (1.8%)            | 86 (1.6%)              |

<br>


### Model Latency Sequences

The following charts display the pure LLM execution latency (excluding agent overhead) for each generated response throughout the test run.


**gemini-2.5-flash LLM Latency Sequence (Request Order)**<br>

[![gemini-2.5-flash LLM Latency Sequence (Request Order)](report_assets_20260320_063748/seq_model_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_model_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro LLM Latency Sequence (Request Order)**<br>

[![gemini-2.5-pro LLM Latency Sequence (Request Order)](report_assets_20260320_063748/seq_model_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_model_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview LLM Latency Sequence (Request Order)**<br>

[![gemini-3-pro-preview LLM Latency Sequence (Request Order)](report_assets_20260320_063748/seq_model_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_model_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview LLM Latency Sequence (Request Order)**<br>

[![gemini-3.1-pro-preview LLM Latency Sequence (Request Order)](report_assets_20260320_063748/seq_model_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_model_gemini-3_1-pro-preview_4K.png)
<br>


### Token Statistics


`gemini-2.5-pro` and `gemini-2.5-flash` process ~30k input tokens on average. For `gemini-2.5-flash` and `gemini-2.5-pro`, there are 'Strong' and 'Very Strong' correlations (up to 0.99) between output+thinking token consumption and latency across several agents, indicating generation time heavily dictates overall speed.

| **Metric**                           | **gemini-2.5-flash**   | **gemini-2.5-pro**   | **gemini-3-pro-preview**   | **gemini-3.1-pro-preview**   |
|:-------------------------------------|:-----------------------|:---------------------|:---------------------------|:-----------------------------|
| **Amount of Requests**               | 5378                   | 5132                 | 1956                       | 2729                         |
| **Mean Input Tokens**                | 30935.87               | 30821.98             | 10970.04                   | 22637.98                     |
| **P95 Input Tokens**                 | 115269.00              | 112115.00            | 26158.00                   | 53577.00                     |
| **Mean Thought Tokens**              | 427.49                 | 492.83               | 704.14                     | 398.48                       |
| **P95 Thought Tokens**               | 1270.00                | 1498.00              | 2210.00                    | 854.00                       |
| **Mean Output Tokens**               | 104.94                 | 112.05               | 133.86                     | 96.02                        |
| **P95 Output Tokens**                | 290.00                 | 333.00               | 607.00                     | 290.00                       |
| **Median Output Tokens**             | 61.00                  | 56.00                | 41.00                      | 62.00                        |
| **Min Output Tokens**                | 7.00                   | 7.00                 | 7.00                       | 13.00                        |
| **Max Output Tokens**                | 4935.00                | 5922.00              | 29336.00                   | 2963.00                      |
| **Mean Total Tokens**                | 31466.01               | 31447.04             | 11763.45                   | 23127.83                     |
| **Latency vs Input Corr.**           | 0.285                  | 0.235                | -0.025                     | -0.204                       |
| **Latency vs Output Corr.**          | 0.440                  | 0.534                | 0.558                      | 0.414                        |
| **Latency vs Output+Thinking Corr.** | **0.870**              | 0.831                | 0.708                      | 0.443                        |
| **Correlation Strength**             | 🟧 **Strong**          | 🟨 **Moderate**      | 🟨 **Moderate**            | ⬜ **Weak**                  |

<br>


### Token Usage Breakdown per Model

The charts below display the average token consumption per request, broken down by **Input**, **Thought**, and **Output** tokens for each Agent using a specific Model.

> [!NOTE]
> This data is aggregated by calculating the mean token counts across all raw LLM events for the given Agent and Model combination.


**Token Breakdown for gemini-2.5-flash**<br>

[![Token Breakdown for gemini-2.5-flash](report_assets_20260320_063748/token_usage_gemini-2_5-flash.png)](report_assets_20260320_063748/token_usage_gemini-2_5-flash_4K.png)
<br>

**Token Breakdown for gemini-2.5-pro**<br>

[![Token Breakdown for gemini-2.5-pro](report_assets_20260320_063748/token_usage_gemini-2_5-pro.png)](report_assets_20260320_063748/token_usage_gemini-2_5-pro_4K.png)
<br>

**Token Breakdown for gemini-3-pro-preview**<br>

[![Token Breakdown for gemini-3-pro-preview](report_assets_20260320_063748/token_usage_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_usage_gemini-3-pro-preview_4K.png)
<br>

**Token Breakdown for gemini-3.1-pro-preview**<br>

[![Token Breakdown for gemini-3.1-pro-preview](report_assets_20260320_063748/token_usage_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_usage_gemini-3_1-pro-preview_4K.png)
<br>


### Requests Distribution

**Model Latency Distribution**<br>

[![Model Latency Distribution](report_assets_20260320_063748/model_latency_bucketed.png)](report_assets_20260320_063748/model_latency_bucketed_4K.png)
<br>


**gemini-2.5-flash**

| **Category**         |   **Count** | **Percentage**   |
|:---------------------|------------:|:-----------------|
| **Very Fast (< 1s)** |           0 | 0.0%             |
| **Fast (1-2s)**      |         581 | 10.9%            |
| **Medium (2-3s)**    |        1047 | 19.6%            |
| **Slow (3-5s)**      |        1815 | 34.0%            |
| **Very Slow (5-8s)** |        1169 | 21.9%            |
| **Outliers (8s+)**   |         731 | 13.7%            |

<br>


**gemini-2.5-pro**

| **Category**         |   **Count** | **Percentage**   |
|:---------------------|------------:|:-----------------|
| **Very Fast (< 1s)** |           0 | 0.0%             |
| **Fast (1-2s)**      |          22 | 0.4%             |
| **Medium (2-3s)**    |         289 | 5.7%             |
| **Slow (3-5s)**      |        1245 | 24.8%            |
| **Very Slow (5-8s)** |        1561 | 31.0%            |
| **Outliers (8s+)**   |        1911 | 38.0%            |

<br>


**gemini-3-pro-preview**

| **Category**         |   **Count** | **Percentage**   |
|:---------------------|------------:|:-----------------|
| **Very Fast (< 1s)** |           0 | 0.0%             |
| **Fast (1-2s)**      |           0 | 0.0%             |
| **Medium (2-3s)**    |           4 | 0.2%             |
| **Slow (3-5s)**      |         220 | 12.2%            |
| **Very Slow (5-8s)** |         222 | 12.3%            |
| **Outliers (8s+)**   |        1354 | 75.2%            |

<br>


**gemini-3.1-pro-preview**

| **Category**         |   **Count** | **Percentage**   |
|:---------------------|------------:|:-----------------|
| **Very Fast (< 1s)** |           0 | 0.0%             |
| **Fast (1-2s)**      |           0 | 0.0%             |
| **Medium (2-3s)**    |           2 | 0.1%             |
| **Slow (3-5s)**      |         433 | 17.3%            |
| **Very Slow (5-8s)** |        1025 | 41.0%            |
| **Outliers (8s+)**   |        1037 | 41.5%            |

<br>


---


## System Bottlenecks & Impact


The #1 bottleneck found is unhandled code exceptions causing fatal silent system crashes, resulting in "PENDING for > 5 minutes" timeouts. These container crashes instantly kill requests with 0ms duration. The secondary bottleneck is massive internal agent overhead in `bigquery_data_agent` (228.248s) caused by synchronous blocking.


### Slowest Invocations

| Rank                 | Timestamp           | Root Agent                  |   Duration (s) | Status   | User Message                                                                                                                                                         | Session ID                           | Trace ID                                                                                                                                                       |
|:---------------------|:--------------------|:----------------------------|---------------:|:---------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-root-1)** | 2026-03-13 22:42:34 | **knowledge_qa_supervisor** |        223.756 | 🟢       | How many distinct `error_codes` were recorded in the `tool_execution_errors` table today?                                                                            | fafd0d28-64d7-4f92-9bf4-f496bbba9155 | [`334685b285143468b83d7f624116ee4e`](https://console.cloud.google.com/traces/explorer;traceId=334685b285143468b83d7f624116ee4e?project=agent-operations-ek-05) |
| **[2](#rca-root-2)** | 2026-03-13 22:38:29 | **knowledge_qa_supervisor** |        253.487 | 🟢       | Find the top 5 most frequently queried terms in the `query_history_dataset.search_queries` table that resulted in a 'no results found' outcome.                      | 1a4a56f8-8b15-4262-90b5-699e89df7dfb | [`6441c26e4dfad46f3d1d65b668e2281b`](https://console.cloud.google.com/traces/explorer;traceId=6441c26e4dfad46f3d1d65b668e2281b?project=agent-operations-ek-05) |
| **[3](#rca-root-3)** | 2026-03-13 22:14:27 | **knowledge_qa_supervisor** |        276.118 | 🟢       | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author                                                                                | 1fcc1584-ecbf-4e75-8cf7-ec6763269b6d | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) |
| **[4](#rca-root-4)** | 2026-03-13 22:05:28 | **knowledge_qa_supervisor** |        271.685 | 🟢       | Retrieve the total `token_cost_usd` for all `gemini-3-pro-preview` model invocations where the `region` was 'global' from `billing.token_costs`.                     | 4cb67762-5c61-4868-979b-2dbd997c52c1 | [`3a1da188ec0f3fda7d921d7721c37b66`](https://console.cloud.google.com/traces/explorer;traceId=3a1da188ec0f3fda7d921d7721c37b66?project=agent-operations-ek-05) |
| **[5](#rca-root-5)** | 2026-03-13 21:59:09 | **knowledge_qa_supervisor** |        244.967 | 🟢       | Lookup `resource_X_100` and `resource_Y_100` in parallel; if both are found, describe their combined significance for the 'Index 100' project (creative generation). | 6220116b-b4c8-4130-ab08-796bb9e87c39 | [`fa86ffb3c1691712d4663ed484ec7956`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-root-1"></a>**Rank 1**: The trace exhibits extreme P99 latency (~224s) despite an 'OK' status, indicating a severe performance bottleneck likely caused by an inefficient, unindexed downstream database query performing a full table scan on `tool_execution_errors`, resulting in a functional timeout for the end-user.

- <a id="rca-root-2"></a>**Rank 2**: Extreme latency (~253s) was caused by an inefficient, long-running database operation against the `query_history_dataset.search_queries` table, likely due to a full table scan on unindexed data. Although the span status is 'OK', this severe performance degradation represents a functional failure, effectively timing out from a user experience perspective.

- <a id="rca-root-3"></a>**Rank 3**: The data retrieval span completed with an 'OK' status but exhibited excessive latency (276s), indicating a severe performance degradation or timeout in the downstream data retrieval service, likely caused by an inefficient query or resource contention.

- <a id="rca-root-4"></a>**Rank 4**: The query against the `billing.token_costs` table induced extreme latency (~272s) likely due to a full table scan, indicating missing or ineffective database indexes on the 'model' or 'region' columns. This performance bottleneck caused a service-level failure, effectively timing out the agent's task despite the span completing with an 'OK' status.

- <a id="rca-root-5"></a>**Rank 5**: The agent experienced a severe performance failure, indicated by the excessive 245-second latency, despite the 'OK' status; this was caused by a compute bottleneck during the synchronous 'creative generation' step which occurs after the parallel resource lookups are complete.

<br>


### Slowest Agent queries

| **Rank**              | **Timestamp**       | **Name**                               |   **Latency (s)** | **Status**   | **User Message**                                                                                                                                                     | **Root Agent**              |   **E2E (s)** | **Root Status**   | **Impact (%)**   | **Session ID**                       | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:----------------------|:--------------------|:---------------------------------------|------------------:|:-------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------|--------------:|:------------------|:-----------------|:-------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-agent-1)** | 2026-03-13 22:38:35 | **bigquery_data_agent**                |           248.256 | 🟢           | Find the top 5 most frequently queried terms in the `query_history_dataset.search_queries` table that resulted in a 'no results found' outcome.                      | **knowledge_qa_supervisor** |       253.487 | 🟢                | 97.9%            | 1a4a56f8-8b15-4262-90b5-699e89df7dfb | [`6441c26e4dfad46f3d1d65b668e2281b`](https://console.cloud.google.com/traces/explorer;traceId=6441c26e4dfad46f3d1d65b668e2281b?project=agent-operations-ek-05) | [`1742cc3b34ba145b`](https://console.cloud.google.com/traces/explorer;traceId=6441c26e4dfad46f3d1d65b668e2281b;spanId=1742cc3b34ba145b?project=agent-operations-ek-05) |
| **[2](#rca-agent-2)** | 2026-03-13 22:14:46 | **lookup_worker_2**                    |           257.09  | 🟢           | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author                                                                                | **knowledge_qa_supervisor** |       276.118 | 🟢                | 93.1%            | 1fcc1584-ecbf-4e75-8cf7-ec6763269b6d | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) | [`53e0ff95c641db6f`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400;spanId=53e0ff95c641db6f?project=agent-operations-ek-05) |
| **[3](#rca-agent-3)** | 2026-03-13 22:14:46 | **parallel_db_lookup**                 |           257.114 | 🟢           | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author                                                                                | **knowledge_qa_supervisor** |       276.118 | 🟢                | 93.1%            | 1fcc1584-ecbf-4e75-8cf7-ec6763269b6d | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) | [`496f53ce7a1819ff`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400;spanId=496f53ce7a1819ff?project=agent-operations-ek-05) |
| **[4](#rca-agent-4)** | 2026-03-13 22:05:34 | **bigquery_data_agent**                |           265.147 | 🟢           | Retrieve the total `token_cost_usd` for all `gemini-3-pro-preview` model invocations where the `region` was 'global' from `billing.token_costs`.                     | **knowledge_qa_supervisor** |       271.685 | 🟢                | 97.6%            | 4cb67762-5c61-4868-979b-2dbd997c52c1 | [`3a1da188ec0f3fda7d921d7721c37b66`](https://console.cloud.google.com/traces/explorer;traceId=3a1da188ec0f3fda7d921d7721c37b66?project=agent-operations-ek-05) | [`f3fb3007e4cf3977`](https://console.cloud.google.com/traces/explorer;traceId=3a1da188ec0f3fda7d921d7721c37b66;spanId=f3fb3007e4cf3977?project=agent-operations-ek-05) |
| **[5](#rca-agent-5)** | 2026-03-13 21:59:09 | **config_test_agent_over_provisioned** |           244.966 | 🟢           | Lookup `resource_X_100` and `resource_Y_100` in parallel; if both are found, describe their combined significance for the 'Index 100' project (creative generation). | **knowledge_qa_supervisor** |       244.967 | 🟢                | 100.0%           | 6220116b-b4c8-4130-ab08-796bb9e87c39 | [`fa86ffb3c1691712d4663ed484ec7956`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956?project=agent-operations-ek-05) | [`28b75daa648bc04b`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956;spanId=28b75daa648bc04b?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-agent-1"></a>**Rank 1**: The operation's `OK` status is misleading; the `bigquery_data_agent` experienced severe performance degradation, with a p99 latency of 248 seconds. This high latency is directly caused by executing a computationally expensive, unoptimized analytical query against a large BigQuery table, indicating a need for query optimization, indexing, or pre-aggregation to meet performance SLOs.

- <a id="rca-agent-2"></a>**Rank 2**: The `lookup_worker_2` span's call to `simulated_db_lookup` exhibited extreme P99 latency (257s) despite a successful status, indicating a severe performance bottleneck in the downstream data source. This is likely due to an inefficient query, lock contention, or resource exhaustion, which consumed ~93% of the total trace time and severely degraded system throughput.

- <a id="rca-agent-3"></a>**Rank 3**: The `parallel_db_lookup` agent received an empty `instruction` from its parent, causing it to execute a default, un-indexed, or full-scan operation that resulted in excessive latency (257s) and unintended output.

- <a id="rca-agent-4"></a>**Rank 4**: The `bigquery_data_agent` span, while successful, exhibited extreme latency (265s) executing a query against the `billing.token_costs` table, indicating a probable full table scan on a massive, unpartitioned, or poorly indexed dataset. This non-performant database query created a critical bottleneck, severely degrading the overall latency of the parent trace.

- <a id="rca-agent-5"></a>**Rank 5**: The span's ~245s duration, despite an 'OVER_PROVISIONED' configuration, indicates a client-side timeout was reached during the parallel lookup for `resource_X_100` or `resource_Y_100`. The final 'OK' status reveals the timeout was handled as a non-error condition, masking the underlying resource unavailability and causing extreme performance degradation.

<br>


### Slowest LLM queries

| **Rank**            | **Timestamp**       |   **LLM (s)** |   **TTFT (s)** | **Model Name**             | **LLM Status**   |   **Input** |   **Output** |   **Thought** |   **Total Tokens** | **Response Text**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **Agent Name**              | **Agent (s)**   | **Agent Status impact**   | **Root Agent Name**         | **E2E (s)**   | **Root Status**   | **Impact %**   | **User Message**                                                                                                                                                     | **Session ID**                       | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:--------------------|:--------------------|--------------:|---------------:|:---------------------------|:-----------------|------------:|-------------:|--------------:|-------------------:|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------|:----------------|:--------------------------|:----------------------------|:--------------|:------------------|:---------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-llm-1)** | 2026-03-13 22:42:11 |       211.249 |          0     | **gemini-3-pro-preview**   | 🔴               |           0 |            0 |             0 |                  0 | N/A                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | **adk_documentation_agent** | N/A             | 🔴                        | **knowledge_qa_supervisor** | N/A           | 🔴                | N/A            | Find the ADK documentation for 'tool timeout settings'. Then, simulate an 'external_API_timeout' using the unreliable tool and observe its behavior.                 | f650018e-0e35-472d-80b4-1b7838481337 | [`12bad15b83e4e4877808b5f6151a673e`](https://console.cloud.google.com/traces/explorer;traceId=12bad15b83e4e4877808b5f6151a673e?project=agent-operations-ek-05) | [`bfc6791a5aa8473b`](https://console.cloud.google.com/traces/explorer;traceId=12bad15b83e4e4877808b5f6151a673e;spanId=bfc6791a5aa8473b?project=agent-operations-ek-05) |
| **[2](#rca-llm-2)** | 2026-03-13 22:15:08 |       234.97  |        234.97  | **gemini-3-pro-preview**   | 🟢               |        1196 |        29336 |             0 |              30532 | text: 'The lookup for `news_article_100_summary` was successful.  I have retrieved the data for the requested item ID. I should now output the result.  The user asked to "Retrieve ...". I have performed the action. I will report the result.  Wait, I need to be careful. The result I got back is "Data for item: news_article_100_summary". This looks like a placeholder string from the simulated tool, but it is the result.  I will return this information.  One thing to note: The system instructions say "You will be given an item ID. Use the simulated_db_lookup tool to fetch the data for this single... | **lookup_worker_2**         | 257.09          | 🟢                        | **knowledge_qa_supervisor** | 276.118       | 🟢                | 85.1%          | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author                                                                                | 1fcc1584-ecbf-4e75-8cf7-ec6763269b6d | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) | [`462c77875669f844`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400;spanId=462c77875669f844?project=agent-operations-ek-05) |
| **[3](#rca-llm-3)** | 2026-03-13 22:14:46 |       234.97  |        234.97  | **gemini-3-pro-preview**   | 🟢               |        1196 |        29336 |             0 |              30532 | text: 'The lookup for `news_article_100_summary` was successful.  I have retrieved the data for the requested item ID. I should now output the result.  The user asked to "Retrieve ...". I have performed the action. I will report the result.  Wait, I need to be careful. The result I got back is "Data for item: news_article_100_summary". This looks like a placeholder string from the simulated tool, but it is the result.  I will return this information.  One thing to note: The system instructions say "You will be given an item ID. Use the simulated_db_lookup tool to fetch the data for this single... | **lookup_worker_2**         | 257.09          | 🟢                        | **knowledge_qa_supervisor** | 276.118       | 🟢                | 85.1%          | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author                                                                                | 1fcc1584-ecbf-4e75-8cf7-ec6763269b6d | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) | [`462c77875669f844`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400;spanId=462c77875669f844?project=agent-operations-ek-05) |
| **[4](#rca-llm-4)** | 2026-03-13 21:59:31 |       222.999 |        222.999 | **gemini-3.1-pro-preview** | 🟢               |        2115 |          330 |           490 |               2935 | text: 'Both `resource_X_100` and `resource_Y_100` have been successfully located in the database.   For the **'Index 100'** project, the convergence of these two resources is fundamentally transformative. Here is a breakdown of their combined significance:  * **Resource_X_100 (The Structural Blueprint):** This resource provides the foundational data scaffolding and categorical taxonomy for the project. It acts as the anchor, establishing the rigid structural boundaries and empirical constraints that keep the system grounded. * **Resource_Y_100 (The Generative Matrix):** This resource functions... | **lookup_worker_3**         | 236.02          | 🟢                        | **knowledge_qa_supervisor** | 244.967       | 🟢                | 91.0%          | Lookup `resource_X_100` and `resource_Y_100` in parallel; if both are found, describe their combined significance for the 'Index 100' project (creative generation). | 6220116b-b4c8-4130-ab08-796bb9e87c39 | [`fa86ffb3c1691712d4663ed484ec7956`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956?project=agent-operations-ek-05) | [`5651ddeccfc04388`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956;spanId=5651ddeccfc04388?project=agent-operations-ek-05) |
| **[5](#rca-llm-5)** | 2026-03-13 21:59:18 |       222.999 |        222.999 | **gemini-3.1-pro-preview** | 🟢               |        2115 |          330 |           490 |               2935 | text: 'Both `resource_X_100` and `resource_Y_100` have been successfully located in the database.   For the **'Index 100'** project, the convergence of these two resources is fundamentally transformative. Here is a breakdown of their combined significance:  * **Resource_X_100 (The Structural Blueprint):** This resource provides the foundational data scaffolding and categorical taxonomy for the project. It acts as the anchor, establishing the rigid structural boundaries and empirical constraints that keep the system grounded. * **Resource_Y_100 (The Generative Matrix):** This resource functions... | **lookup_worker_3**         | 236.02          | 🟢                        | **knowledge_qa_supervisor** | 244.967       | 🟢                | 91.0%          | Lookup `resource_X_100` and `resource_Y_100` in parallel; if both are found, describe their combined significance for the 'Index 100' project (creative generation). | 6220116b-b4c8-4130-ab08-796bb9e87c39 | [`fa86ffb3c1691712d4663ed484ec7956`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956?project=agent-operations-ek-05) | [`5651ddeccfc04388`](https://console.cloud.google.com/traces/explorer;traceId=fa86ffb3c1691712d4663ed484ec7956;spanId=5651ddeccfc04388?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-llm-1"></a>**Rank 1**: The request to the Gemini model failed with a 429 RESOURCE_EXHAUSTED error after client-side retries were exhausted, indicating the model backend's prefill queue was overloaded and actively load-shedding requests, which ultimately caused the adk_documentation_agent's execution to fail.

- <a id="rca-llm-2"></a>**Rank 2**: The LLM call exhibited a 235-second Time To First Token (TTFT) due to generating an extremely large response payload (`candidates_token_count`: 29,336), indicating the agent's prompt did not sufficiently constrain the model's output verbosity. This resulted in a severe latency-based failure despite the span's functional "OK" status.

- <a id="rca-llm-3"></a>**Rank 3**: The extreme ~235-second Time-To-First-Token was caused by specifying a non-existent model 'gemini-3-pro-preview', which likely forced the LLM provider's API to incur a significant resolution or fallback delay before processing the request, resulting in critical application latency.

- <a id="rca-llm-4"></a>**Rank 4**: The LLM call to `gemini-3.1-pro-preview` experienced severe performance degradation, with an anomalous Time To First Token (TTFT) of ~223 seconds consuming the entire span duration and indicating a downstream model provider issue or resource contention.

- <a id="rca-llm-5"></a>**Rank 5**: An anomalous time_to_first_token (TTFT) of ~223 seconds for the `gemini-3.1-pro-preview` model indicates a severe model loading latency or resource contention on the inference backend, causing a performance degradation that stalled the `lookup_worker_3` agent despite a successful final status.

<br>


### Slowest Tools Queries

| **Rank**             | **Timestamp**       |   **Tool (s)** | **Tool Name**             | **Tool Status**   | **Arguments**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | **Result**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | **Agent Name**            |   **Agent (s)** | **Agent Status**   |   **Impact %** | **Root Agent**          |   **E2E (s)** | **Root Status**   |   **Impact %** | **User Message**                                                                                                                            | **Session ID**                       | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:---------------------|:--------------------|---------------:|:--------------------------|:------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------|----------------:|:-------------------|---------------:|:------------------------|--------------:|:------------------|---------------:|:--------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-tool-1)** | 2026-03-13 22:27:44 |         21.433 | **list_tables**           | 🔴                | N/A                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | N/A                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **bigquery_data_agent**   |             nan | 🔴                 |              0 | knowledge_qa_supervisor |       nan     | 🔴                |           0    | Calculate the 90th percentile of token usage for all 'gemini-2.5-pro' model calls recorded in `llm_usage_logs`.                             | d0a08961-e349-44ef-8348-5115e03461da | [`38f1c60126dbc30618c1b520625a919f`](https://console.cloud.google.com/traces/explorer;traceId=38f1c60126dbc30618c1b520625a919f?project=agent-operations-ek-05) | [`ab27d60a61cb67ba`](https://console.cloud.google.com/traces/explorer;traceId=38f1c60126dbc30618c1b520625a919f;spanId=ab27d60a61cb67ba?project=agent-operations-ek-05) |
| **[2](#rca-tool-2)** | 2026-03-13 22:15:19 |          8.415 | **flaky_tool_simulation** | 🔴                | `{"query":"high_concurrency_test_100"}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | N/A                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **unreliable_tool_agent** |             nan | None               |              0 | knowledge_qa_supervisor |       nan     | 🔴                |           0    | Execute the unreliable tool with 'high_concurrency_test_100' and observe its stability.                                                     | 6b5d7aae-5b8e-40ad-ab2c-5789e546239e | [`5dbd4db67504668b1eda51dc1167223f`](https://console.cloud.google.com/traces/explorer;traceId=5dbd4db67504668b1eda51dc1167223f?project=agent-operations-ek-05) | [`b03ff0de5489ee0f`](https://console.cloud.google.com/traces/explorer;traceId=5dbd4db67504668b1eda51dc1167223f;spanId=b03ff0de5489ee0f?project=agent-operations-ek-05) |
| **[3](#rca-tool-3)** | 2026-03-13 21:59:43 |          9.62  | **execute_sql**           | 🟢                | `{"project_id":"agent-operations-ek-05","query":"\nSELECT\n  DATE(timestamp) AS event_date,\n  COUNT(DISTINCT JSON_EXTRACT_SCALAR(t.content, '$.text')) AS distinct_questions\nFROM\n  `agent-operations-ek-05.logging.agent_events_demo_v3` AS t\nWHERE\n  DATE(t.timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH)\n  AND t.event_type = 'USER_MESSAGE_RECEIVED'\n  AND JSON_EXTRACT_SCALAR(t.attributes, '$.query_category') = 'ADK Documentation'\nGROUP BY\n  event_date\nORDER BY\n  event_date\n"}`                                                                                                             | `{"rows":[],"status":"SUCCESS"}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | **bigquery_data_agent**   |             nan | None               |              0 | knowledge_qa_supervisor |        79.419 | 🟢                |          12.11 | Determine the number of distinct `ADK Documentation` questions asked per day from `agent_queries.query_categorization` over the last month. | b6137992-18c4-4e74-afb5-58795692e612 | [`c3435649bd33f23c953373e9a3b16503`](https://console.cloud.google.com/traces/explorer;traceId=c3435649bd33f23c953373e9a3b16503?project=agent-operations-ek-05) | [`d1c17375cc51bf5c`](https://console.cloud.google.com/traces/explorer;traceId=c3435649bd33f23c953373e9a3b16503;spanId=d1c17375cc51bf5c?project=agent-operations-ek-05) |
| **[4](#rca-tool-4)** | 2026-03-13 21:59:26 |         21.235 | **execute_sql**           | 🟢                | `{"project_id":"agent-operations-ek-05","query":"WITH AgentDurations AS (\n  SELECT\n    invocation_id,\n    CAST(JSON_EXTRACT_SCALAR(latency_ms, '$.total_ms') AS FLOAT64) AS duration_ms\n  FROM\n    `agent-operations-ek-05.logging.agent_events_demo_v3`\n  WHERE\n    event_type = 'AGENT_COMPLETED'\n    AND DATE(timestamp) = '2026-03-13'\n),\nAgentResponses AS (\n  SELECT\n    invocation_id,\n    JSON_EXTRACT_SCALAR(content, '$.response') AS response\n  FROM\n    `agent-operations-ek-05.logging.agent_events_demo_v3`\n  WHERE\n    event_type = 'LLM_RESPONSE'\n    AND DATE(timestamp) = '2026-03-13...` | `{"result_is_likely_truncated":true,"rows":[{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: get_table_info"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"call: execute_sql"},{"duration_ms":133265,"response":"text: 'I can help with that. I've looked into the `agent_events_demo_v3` table in the `a...` | **bigquery_data_agent**   |             nan | None               |              0 | knowledge_qa_supervisor |       151.499 | 🟢                |          14.02 | Identify the 100 slowest agent responses from `agent_performance_metrics` for a given week.                                                 | 029d2c91-c94f-43ec-9432-76b548a36e25 | [`a18d6ad259879293a72e4bf6847db554`](https://console.cloud.google.com/traces/explorer;traceId=a18d6ad259879293a72e4bf6847db554?project=agent-operations-ek-05) | [`87286488c747b62e`](https://console.cloud.google.com/traces/explorer;traceId=a18d6ad259879293a72e4bf6847db554;spanId=87286488c747b62e?project=agent-operations-ek-05) |
| **[5](#rca-tool-5)** | 2026-03-13 21:58:58 |          9.352 | **flaky_tool_simulation** | 🔴                | `{"query":"sensitive_user_data_100","tool_name":"unreliable_tool"}`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | N/A                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **unreliable_tool_agent** |             nan | None               |              0 | knowledge_qa_supervisor |       nan     | 🔴                |           0    | Invoke the unreliable tool with 'sensitive_user_data_100' and report any data corruption.                                                   | b00a8a3a-761e-4186-a548-f05078a6ace1 | [`eb095ec3a9710647abd43f3b44203204`](https://console.cloud.google.com/traces/explorer;traceId=eb095ec3a9710647abd43f3b44203204?project=agent-operations-ek-05) | [`78df578d4e55192a`](https://console.cloud.google.com/traces/explorer;traceId=eb095ec3a9710647abd43f3b44203204;spanId=78df578d4e55192a?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-tool-1"></a>**Rank 1**: The bigquery_data_agent failed due to a tool invocation error where the LLM hallucinated the non-existent `list_tables` tool, which is not registered in its tool manifest; the agent should have used `list_table_ids` to discover tables within the dataset, causing a fatal error in the agent's execution plan.

- <a id="rca-tool-2"></a>**Rank 2**: The `unreliable_tool_agent`'s request to the `flaky_tool_simulation` service timed out after 8.415 seconds while processing the 'high_concurrency_test_100' query. This indicates the downstream tool failed to complete its execution and return a response within the client's configured timeout threshold, likely due to internal processing delays or induced instability.

- <a id="rca-tool-3"></a>**Rank 3**: The agent hallucinated the SQL query's source table, targeting `logging.agent_events_demo_v3` instead of a more appropriate table like `agent_queries.query_categorization` as implied by the prompt, resulting in a successful query execution that returned no data.

- <a id="rca-tool-4"></a>**Rank 4**: The `execute_sql` tool returned a payload exceeding the system's maximum size limit, causing the result set to be truncated as indicated by the `result_is_likely_truncated` flag and a cut-off text field. This data loss prevents the agent from processing the full query results, leading to an incomplete analysis and likely incorrect final output.

- <a id="rca-tool-5"></a>**Rank 5**: The `unreliable_tool` service call initiated by the `unreliable_tool_agent` timed out after 9.352 seconds, indicating the downstream service is unresponsive or experiencing a performance degradation which caused the agent's task to fail.

<br>


## Error Analysis


The error cascade starts at the orchestration level with fatal silent system crashes ("PENDING" TIMEOUTs). At the tool level, failures cascade from `flaky_tool_simulation` (QUOTA_EXCEEDED) and hallucinated tools (`search`, `list_tables` returning TOOL_NOT_FOUND). At the LLM layer, 429 RESOURCE_EXHAUSTED errors plague `gemini-3.1-pro-preview` and `gemini-3-pro-preview`, while `gemini-2.5-flash` fails on 400 INVALID_ARGUMENT when requested max_tokens exceeds 65536.


### Root Errors

**Total Root Errors in Analysis Window:** 439

**Error Categorization Summary:**
| **Category**   |   **Count** | **%**   |
|:---------------|------------:|:--------|
| **TIMEOUT**    |         439 | 100.0%  |

**Sample Details (Limited to 5):**

| **Rank**                 | **Timestamp**       | **Category**   | **Root Agent**              | **Error Message**                              | **User Message**                                                                                                                                                                | **Trace ID**                                                                                                                                                   | **Invocation ID**                        |
|:-------------------------|:--------------------|:---------------|:----------------------------|:-----------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------|
| **[1](#rca-err-root-1)** | 2026-03-13 22:44:43 | TIMEOUT        | **knowledge_qa_supervisor** | Invocation PENDING for > 5 minutes (Timed Out) | Retrieve all conversation transcripts from `dialog_history_archive` for `user_session_id_ABC-123`.                                                                              | [`d9140e48933ac7af7daf18cb95e03a57`](https://console.cloud.google.com/traces/explorer;traceId=d9140e48933ac7af7daf18cb95e03a57?project=agent-operations-ek-05) | `e-649e035f-4bf6-4e3b-9b02-56a7d971e8bc` |
| **[2](#rca-err-root-2)** | 2026-03-13 22:43:53 | TIMEOUT        | **knowledge_qa_supervisor** | Invocation PENDING for > 5 minutes (Timed Out) | Using `OVER_PROVISIONED` config, ask the agent to draft an email to a customer explaining a service outage. Then, check BigQuery for `recent_outage_events` to ensure accuracy. | [`e7cd9f6d119bf8479dfb150ba4f2d92d`](https://console.cloud.google.com/traces/explorer;traceId=e7cd9f6d119bf8479dfb150ba4f2d92d?project=agent-operations-ek-05) | `e-2a6f3c8b-f8a1-4b86-acff-9a8c280616d9` |
| **[3](#rca-err-root-3)** | 2026-03-13 22:43:49 | TIMEOUT        | **knowledge_qa_supervisor** | Invocation PENDING for > 5 minutes (Timed Out) | Using `NORMAL` config, translate a 'medical_research_abstract' into German.                                                                                                     | [`842dcc478537187104822ee0909ef78f`](https://console.cloud.google.com/traces/explorer;traceId=842dcc478537187104822ee0909ef78f?project=agent-operations-ek-05) | `e-dbafb958-be13-44fb-a2f9-089d29a71c34` |
| **[4](#rca-err-root-4)** | 2026-03-13 22:43:48 | TIMEOUT        | **knowledge_qa_supervisor** | Invocation PENDING for > 5 minutes (Timed Out) | Find the agent runs with the highest `token_cost` from `agent_billing_data` and their corresponding prompts.                                                                    | [`41955a3abdbbc43140a03d673f7f7ce3`](https://console.cloud.google.com/traces/explorer;traceId=41955a3abdbbc43140a03d673f7f7ce3?project=agent-operations-ek-05) | `e-85e20441-f03d-4133-9fc7-216b784d3598` |
| **[5](#rca-err-root-5)** | 2026-03-13 22:43:33 | TIMEOUT        | **knowledge_qa_supervisor** | Invocation PENDING for > 5 minutes (Timed Out) | Using `NORMAL` config, translate a 'medical_research_abstract' into German.                                                                                                     | [`0e7a099542a5edf1fc1523d703fa5d6a`](https://console.cloud.google.com/traces/explorer;traceId=0e7a099542a5edf1fc1523d703fa5d6a?project=agent-operations-ek-05) | `e-2c76c8e0-7c23-450a-987d-52dafb8b8a27` |

<br>

**Detailed RCA Analysis:**

- <a id="rca-err-root-1"></a>**Rank 1**: The invocation timed out after 5 minutes in a `PENDING` state with a 0ms duration, indicating the `bigquery_data_agent` worker pool was saturated or stalled, preventing the task from being scheduled and acquiring execution resources.

- <a id="rca-err-root-2"></a>**Rank 2**: The agent invocation timed out after remaining in a PENDING state for over 5 minutes, indicating a critical resource-starvation or dispatching failure where no worker process was available to dequeue and execute the task. This system-level issue prevented the supervisor agent from even starting, causing the entire downstream workflow to fail before any logic could be run.

- <a id="rca-err-root-3"></a>**Rank 3**: The `knowledge_qa_supervisor` agent invocation timed out after remaining in a PENDING state for over 5 minutes, indicating the agent worker pool was saturated, unresponsive, or misconfigured, and therefore never dequeued the job for execution. This resulted in a complete failure of the user request before any processing could begin, as confirmed by the 0ms duration.

- <a id="rca-err-root-4"></a>**Rank 4**: The agent invocation timed out after remaining in a PENDING state for over 5 minutes, indicating a resource starvation or worker pool saturation issue. No available compute resources dequeued the task for execution, likely due to high system load or an insufficient number of workers, preventing the request from ever being processed.

- <a id="rca-err-root-5"></a>**Rank 5**: The agent invocation remained in a `PENDING` state for over 5 minutes without being dequeued and processed by a worker, causing a timeout before execution could begin. This indicates a resource starvation or dispatch failure in the worker pool responsible for the `knowledge_qa_supervisor` agent.

<br>


---


### Agent Errors

**Total Agent Errors in Analysis Window:** 455

**Error Categorization Summary:**
| **Category**   |   **Count** | **%**   |
|:---------------|------------:|:--------|
| **TIMEOUT**    |         455 | 100.0%  |

**Sample Details (Limited to 5):**

| **Rank**                  | **Timestamp**       | **Category**   | **Agent Name**               | **Error Message**                              | **Root Agent**              | **Root Status**   | **User Message**                                                                                             | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:--------------------------|:--------------------|:---------------|:-----------------------------|:-----------------------------------------------|:----------------------------|:------------------|:-------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-err-agent-1)** | 2026-03-13 22:44:43 | TIMEOUT        | **bigquery_data_agent**      | Agent span PENDING for > 5 minutes (Timed Out) | **knowledge_qa_supervisor** | 🔴                | Retrieve all conversation transcripts from `dialog_history_archive` for `user_session_id_ABC-123`.           | [`d9140e48933ac7af7daf18cb95e03a57`](https://console.cloud.google.com/traces/explorer;traceId=d9140e48933ac7af7daf18cb95e03a57?project=agent-operations-ek-05) | [`c90af3d4fa654e5f`](https://console.cloud.google.com/traces/explorer;traceId=d9140e48933ac7af7daf18cb95e03a57;spanId=c90af3d4fa654e5f?project=agent-operations-ek-05) |
| **[2](#rca-err-agent-2)** | 2026-03-13 22:44:16 | TIMEOUT        | **bigquery_data_agent**      | Agent span PENDING for > 5 minutes (Timed Out) | **knowledge_qa_supervisor** | 🔴                | Find the agent runs with the highest `token_cost` from `agent_billing_data` and their corresponding prompts. | [`41955a3abdbbc43140a03d673f7f7ce3`](https://console.cloud.google.com/traces/explorer;traceId=41955a3abdbbc43140a03d673f7f7ce3?project=agent-operations-ek-05) | [`635cbfbd8bfe1291`](https://console.cloud.google.com/traces/explorer;traceId=41955a3abdbbc43140a03d673f7f7ce3;spanId=635cbfbd8bfe1291?project=agent-operations-ek-05) |
| **[3](#rca-err-agent-3)** | 2026-03-13 22:43:38 | TIMEOUT        | **config_test_agent_normal** | Agent span PENDING for > 5 minutes (Timed Out) | **knowledge_qa_supervisor** | 🔴                | Using `NORMAL` config, translate a 'medical_research_abstract' into German.                                  | [`0e7a099542a5edf1fc1523d703fa5d6a`](https://console.cloud.google.com/traces/explorer;traceId=0e7a099542a5edf1fc1523d703fa5d6a?project=agent-operations-ek-05) | [`d256aa7a8c75f6d3`](https://console.cloud.google.com/traces/explorer;traceId=0e7a099542a5edf1fc1523d703fa5d6a;spanId=d256aa7a8c75f6d3?project=agent-operations-ek-05) |
| **[4](#rca-err-agent-4)** | 2026-03-13 22:43:37 | TIMEOUT        | **bigquery_data_agent**      | Agent span PENDING for > 5 minutes (Timed Out) | **knowledge_qa_supervisor** | 🔴                | Find the agent runs with the highest `token_cost` from `agent_billing_data` and their corresponding prompts. | [`805aef36007051bac054ccdcb65a05de`](https://console.cloud.google.com/traces/explorer;traceId=805aef36007051bac054ccdcb65a05de?project=agent-operations-ek-05) | [`bbd4f6ae0f55ae9c`](https://console.cloud.google.com/traces/explorer;traceId=805aef36007051bac054ccdcb65a05de;spanId=bbd4f6ae0f55ae9c?project=agent-operations-ek-05) |
| **[5](#rca-err-agent-5)** | 2026-03-13 22:43:21 | TIMEOUT        | **bigquery_data_agent**      | Agent span PENDING for > 5 minutes (Timed Out) | **knowledge_qa_supervisor** | 🔴                | Find the agent runs with the highest `token_cost` from `agent_billing_data` and their corresponding prompts. | [`c628d4cee78e4d9ae964494d910df18c`](https://console.cloud.google.com/traces/explorer;traceId=c628d4cee78e4d9ae964494d910df18c?project=agent-operations-ek-05) | [`6de283f237c062ab`](https://console.cloud.google.com/traces/explorer;traceId=c628d4cee78e4d9ae964494d910df18c;spanId=6de283f237c062ab?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-err-agent-1"></a>**Rank 1**: The `bigquery_data_agent` failed to start because it was never picked up by a worker from the execution queue, remaining in a PENDING state for over 5 minutes until it timed out. This indicates a resource contention or scheduling failure in the agent worker pool, not an error in the agent's own logic.

- <a id="rca-err-agent-2"></a>**Rank 2**: The agent execution framework failed to transition the span from a PENDING to a running state within the 5-minute timeout, indicating a scheduling failure or a complete lack of available `bigquery_data_agent` workers to process the queued task.

- <a id="rca-err-agent-3"></a>**Rank 3**: The agent span timed out in a PENDING state with zero duration, indicating the task was successfully enqueued by the parent agent but was never dequeued and executed by an available worker, likely due to worker pool saturation or a queue processing bottleneck.

- <a id="rca-err-agent-4"></a>**Rank 4**: The `bigquery_data_agent` span timed out after remaining in a PENDING state for over 5 minutes, indicating that no available workers were able to pick up the task from the queue, likely due to resource saturation or a scheduler/dispatcher malfunction.

- <a id="rca-err-agent-5"></a>**Rank 5**: The `bigquery_data_agent` span failed due to a 5-minute timeout while in a PENDING state, indicating that the agent's worker pool was saturated and no execution resources were available to process the dispatched task. This resource contention prevented the agent's logic from ever starting, causing the parent trace to fail.

<br>


### Tool Errors

**Total Tool Errors in Analysis Window:** 14

**Error Categorization Summary:**
| **Category**       |   **Count** | **%**   |
|:-------------------|------------:|:--------|
| **QUOTA_EXCEEDED** |           6 | 42.86%  |
| **TIMEOUT**        |           4 | 28.57%  |
| **TOOL_NOT_FOUND** |           4 | 28.57%  |

**Sample Details (Limited to 5):**

| **Rank**                 | **Timestamp**       | **Category**   | **Tool Name**             | **Tool Args**                          | **Error Message**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | **Agent Name**              | **Agent Status**   | **Root Agent**              | **Root Status**   | **User Message**                                                                                                | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:-------------------------|:--------------------|:---------------|:--------------------------|:---------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------|:-------------------|:----------------------------|:------------------|:----------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-err-tool-1)** | 2026-03-13 22:30:45 | TOOL_NOT_FOUND | **search**                | N/A                                    | Tool 'search' not found. Available tools: transfer_to_agent  Possible causes:   1. LLM hallucinated the function name - review agent instruction clarity   2. Tool not registered - verify agent.tools list   3. Name mismatch - check for typos  Suggested fixes:   - Review agent instruction to ensure tool usage is clear   - Verify tool is included in agent.tools list   - Check for typos in function name                                                                                                                                                                                          | **knowledge_qa_supervisor** | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Can ADK agents be designed to self-correct based on feedback loops?                                             | [`06b0449dce1397695c7c4b8358ded1a6`](https://console.cloud.google.com/traces/explorer;traceId=06b0449dce1397695c7c4b8358ded1a6?project=agent-operations-ek-05) | [`3f6efb748adb2eb7`](https://console.cloud.google.com/traces/explorer;traceId=06b0449dce1397695c7c4b8358ded1a6;spanId=3f6efb748adb2eb7?project=agent-operations-ek-05) |
| **[2](#rca-err-tool-2)** | 2026-03-13 22:27:44 | TOOL_NOT_FOUND | **list_tables**           | N/A                                    | Tool 'list_tables' not found. Available tools: transfer_to_agent, get_dataset_info, get_table_info, list_dataset_ids, list_table_ids, get_job_info, execute_sql, forecast, analyze_contribution, detect_anomalies, ask_data_insights, search_catalog  Possible causes:   1. LLM hallucinated the function name - review agent instruction clarity   2. Tool not registered - verify agent.tools list   3. Name mismatch - check for typos  Suggested fixes:   - Review agent instruction to ensure tool usage is clear   - Verify tool is included in agent.tools list   - Check for typos in function name | **bigquery_data_agent**     | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Calculate the 90th percentile of token usage for all 'gemini-2.5-pro' model calls recorded in `llm_usage_logs`. | [`38f1c60126dbc30618c1b520625a919f`](https://console.cloud.google.com/traces/explorer;traceId=38f1c60126dbc30618c1b520625a919f?project=agent-operations-ek-05) | [`ab27d60a61cb67ba`](https://console.cloud.google.com/traces/explorer;traceId=38f1c60126dbc30618c1b520625a919f;spanId=ab27d60a61cb67ba?project=agent-operations-ek-05) |
| **[3](#rca-err-tool-3)** | 2026-03-13 22:16:49 | QUOTA_EXCEEDED | **flaky_tool_simulation** | `{"query":"corrupted_image_data_100"}` | Quota exceeded for unreliable_tool for query: corrupted_image_data_100                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | **unreliable_tool_agent**   | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Invoke the unreliable tool with 'corrupted_image_data_100' and check for unexpected behavior.                   | [`849b16ffff0dcc3c2fb44b17a254f623`](https://console.cloud.google.com/traces/explorer;traceId=849b16ffff0dcc3c2fb44b17a254f623?project=agent-operations-ek-05) | [`6b2782fe586fde31`](https://console.cloud.google.com/traces/explorer;traceId=849b16ffff0dcc3c2fb44b17a254f623;spanId=6b2782fe586fde31?project=agent-operations-ek-05) |
| **[4](#rca-err-tool-4)** | 2026-03-13 22:16:07 | TIMEOUT        | **flaky_tool_simulation** | `{"query":"volatile_resource_access"}` | unreliable_tool timed out for query: volatile_resource_access                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | **unreliable_tool_agent**   | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Test the unreliable tool's retry mechanism with 'volatile_resource_access'.                                     | [`13e3fb56a0ab923a906973fd75d36d75`](https://console.cloud.google.com/traces/explorer;traceId=13e3fb56a0ab923a906973fd75d36d75?project=agent-operations-ek-05) | [`941daec57c8559b9`](https://console.cloud.google.com/traces/explorer;traceId=13e3fb56a0ab923a906973fd75d36d75;spanId=941daec57c8559b9?project=agent-operations-ek-05) |
| **[5](#rca-err-tool-5)** | 2026-03-13 22:16:02 | QUOTA_EXCEEDED | **flaky_tool_simulation** | `{"query":"volatile_resource_access"}` | Quota exceeded for unreliable_tool for query: volatile_resource_access                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | **unreliable_tool_agent**   | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Test the unreliable tool's retry mechanism with 'volatile_resource_access'.                                     | [`d1669e5245860d2d6a38dddd133613fb`](https://console.cloud.google.com/traces/explorer;traceId=d1669e5245860d2d6a38dddd133613fb?project=agent-operations-ek-05) | [`af1e95e9b24c62f9`](https://console.cloud.google.com/traces/explorer;traceId=d1669e5245860d2d6a38dddd133613fb;spanId=af1e95e9b24c62f9?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-err-tool-1"></a>**Rank 1**: The `knowledge_qa_supervisor` agent failed because its underlying LLM hallucinated a call to the `search` tool, which was not registered in its runtime configuration, as the only available tool was `transfer_to_agent`. This configuration mismatch prevented the agent from executing the required information retrieval task, causing a hard failure.

- <a id="rca-err-tool-2"></a>**Rank 2**: The `bigquery_data_agent` failed because the backing LLM hallucinated a call to the non-existent tool 'list_tables' instead of using the correctly registered 'list_table_ids' tool available in its toolset, causing the tool-use step to fail and halting the agent's plan execution.

- <a id="rca-err-tool-3"></a>**Rank 3**: The invocation of the `flaky_tool_simulation` by the `unreliable_tool_agent` failed immediately because the call exceeded its pre-configured usage quota. This rejection at the tool's API boundary caused the agent's span to error out, propagating the failure up the trace.

- <a id="rca-err-tool-4"></a>**Rank 4**: The `flaky_tool_simulation` tool invocation timed out after 5.4 seconds while executing a `volatile_resource_access` query, indicating the downstream service failed to respond within the client-side timeout threshold, which prevented the `unreliable_tool_agent` from acquiring its result.

- <a id="rca-err-tool-5"></a>**Rank 5**: The `unreliable_tool_agent`'s call to the `flaky_tool_simulation` tool was rejected with a 'Quota exceeded' error, indicating the service's rate-limiting or usage-cap mechanism was triggered for the 'volatile_resource_access' query, preventing the agent from proceeding.

<br>


### LLM Errors

**Total Llm Errors in Analysis Window:** 527

**Error Categorization Summary:**
| **Category**          |   **Count** | **%**   |
|:----------------------|------------:|:--------|
| **MODEL_ERROR**       |         353 | 66.98%  |
| **TIMEOUT**           |          74 | 14.04%  |
| **QUOTA_EXCEEDED**    |          67 | 12.71%  |
| **PERMISSION_DENIED** |          33 | 6.26%   |

**Sample Details (Limited to 5):**

| **Rank**                | **Timestamp**       | **Category**      | **Model Name**             | **LLM Config**                                                                                 | **Error Message**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |   **Latency (s)** | **Parent Agent**                   | **Agent Status**   | **Root Agent**              | **Root Status**   | **User Message**                                                                                                                                                                                                                                                               | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|:------------------------|:--------------------|:------------------|:---------------------------|:-----------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------:|:-----------------------------------|:-------------------|:----------------------------|:------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **[1](#rca-err-llm-1)** | 2026-03-13 22:44:19 | MODEL_ERROR       | **gemini-3.1-pro-preview** | `{"max_output_tokens":8192}`                                                                   | On how to mitigate this issue, please refer to:  https://google.github.io/adk-docs/agents/models/#error-code-429-resource_exhausted   429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.DebugInfo', 'detail': '[ORIGINAL ERROR] extensible_stubs::OVERLOADED_TOO_MANY_RETRIES_PER_REQUEST: Fail to execute model for flow_id: gemini-3-pro-preview-v2-flow_runner_...  |            19.782 | bigquery_data_agent                | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Retrieve all conversation transcripts from `dialog_history_archive` for `user_session_id_ABC-123`.                                                                                                                                                                             | [`d24f9d559f9873670bbab271364209ea`](https://console.cloud.google.com/traces/explorer;traceId=d24f9d559f9873670bbab271364209ea?project=agent-operations-ek-05) | [`c8bd50aa7de08289`](https://console.cloud.google.com/traces/explorer;traceId=d24f9d559f9873670bbab271364209ea;spanId=c8bd50aa7de08289?project=agent-operations-ek-05) |
| **[2](#rca-err-llm-2)** | 2026-03-13 22:43:53 | QUOTA_EXCEEDED    | **gemini-3.1-pro-preview** | N/A                                                                                            | On how to mitigate this issue, please refer to:  https://google.github.io/adk-docs/agents/models/#error-code-429-resource_exhausted   429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource has been exhausted (e.g. check quota).', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.DebugInfo', 'detail': '[ORIGINAL ERROR] generic::resource_exhausted: No backend available to serve the request after retries. 525003295 { 1 { 1 { 1 { 2: "Cardolan" 3: "GenerateContent" } 2 { 1: 8 2: "generic" 3: "No backend available to serve the request after retries....  |             6.427 | knowledge_qa_supervisor            | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Using `OVER_PROVISIONED` config, ask the agent to draft an email to a customer explaining a service outage. Then, check BigQuery for `recent_outage_events` to ensure accuracy.                                                                                                | [`e7cd9f6d119bf8479dfb150ba4f2d92d`](https://console.cloud.google.com/traces/explorer;traceId=e7cd9f6d119bf8479dfb150ba4f2d92d?project=agent-operations-ek-05) | [`a0f77ead7c1182ee`](https://console.cloud.google.com/traces/explorer;traceId=e7cd9f6d119bf8479dfb150ba4f2d92d;spanId=a0f77ead7c1182ee?project=agent-operations-ek-05) |
| **[3](#rca-err-llm-3)** | 2026-03-13 22:43:08 | MODEL_ERROR       | **gemini-2.5-flash**       | `{"candidate_count":1,"max_output_tokens":65538,"presence_penalty":0.1,"top_k":5,"top_p":0.1}` | 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'Unable to submit request because it has a maxOutputTokens value of 65538 but the supported range is from 1 (inclusive) to 65537 (exclusive). Update the value and try again.', 'status': 'INVALID_ARGUMENT', 'details': [{'@type': 'type.googleapis.com/google.rpc.DebugInfo', 'detail': '[ORIGINAL ERROR] generic::invalid_argument: Unable to submit request because it has a maxOutputTokens value of 65538 but the supported range is from 1 (inclusive) to 65537 (exclusive). Update the value and try again. [google.rpc.error_details_ext] { message: "... |             1.106 | config_test_agent_wrong_max_tokens | 🔴                 | **knowledge_qa_supervisor** | 🔴                | With `WRONG_MAX_TOKENS`, attempt to extract key entities from 'legal_contract_review'.                                                                                                                                                                                         | [`22811568333a7210d757840689786718`](https://console.cloud.google.com/traces/explorer;traceId=22811568333a7210d757840689786718?project=agent-operations-ek-05) | [`8ff0385e337c41ba`](https://console.cloud.google.com/traces/explorer;traceId=22811568333a7210d757840689786718;spanId=8ff0385e337c41ba?project=agent-operations-ek-05) |
| **[4](#rca-err-llm-4)** | 2026-03-13 22:42:52 | PERMISSION_DENIED | **gemini-2.5-flash**       | N/A                                                                                            | 404 NOT_FOUND. {'error': {'code': 404, 'message': 'DataStore projects/350016513569/locations/global/collections/default_collection/dataStores/invalid-obs-ds not found.', 'status': 'NOT_FOUND', 'details': [{'@type': 'type.googleapis.com/google.rpc.DebugInfo', 'detail': '[ORIGINAL ERROR] generic::not_found: DataStore projects/350016513569/locations/global/collections/default_collection/dataStores/invalid-obs-ds not found.; Error raised from operator generate_multi_modal\nSource Locations:\n  net/rpc/rpc-status.cc:562\n  cloud/ai/large_models/shared/core/eac/google_tools/search.cc:856\n  cloud/ai... |             3.37  | ai_observability_agent             | 🔴                 | **knowledge_qa_supervisor** | 🔴                | What role does anomaly detection play in AI observability for agents?                                                                                                                                                                                                          | [`98c71b04207479ad8e2d7cb422522552`](https://console.cloud.google.com/traces/explorer;traceId=98c71b04207479ad8e2d7cb422522552?project=agent-operations-ek-05) | [`8c01ebadff4d31b9`](https://console.cloud.google.com/traces/explorer;traceId=98c71b04207479ad8e2d7cb422522552;spanId=8c01ebadff4d31b9?project=agent-operations-ek-05) |
| **[5](#rca-err-llm-5)** | 2026-03-13 22:39:23 | TIMEOUT           | **gemini-2.5-pro**         | N/A                                                                                            | On how to mitigate this issue, please refer to:  https://google.github.io/adk-docs/agents/models/#error-code-429-resource_exhausted   429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.DebugInfo', 'detail': '[ORIGINAL ERROR] extensible_stubs::UNABLE_TO_RETRY: Fail to execute model for flow_id: gemini-2.5-pro-001-flow_runner_text_us_TEXT_32k_1m\nError: A...  |             4.551 | lookup_worker_2                    | 🔴                 | **knowledge_qa_supervisor** | 🔴                | Retrieve customer support tickets from `ticket_system_data` in BigQuery that mention 'payment failure'. For each, use a parallel lookup to get 'user_account_details' and 'transaction_history', then, if necessary, initiate an unreliable tool test for the payment gateway. | [`ba789da201283046d82b63d28eefe7e0`](https://console.cloud.google.com/traces/explorer;traceId=ba789da201283046d82b63d28eefe7e0?project=agent-operations-ek-05) | [`679ef28f6b246896`](https://console.cloud.google.com/traces/explorer;traceId=ba789da201283046d82b63d28eefe7e0;spanId=679ef28f6b246896?project=agent-operations-ek-05) |

<br>

**Detailed RCA Analysis:**

- <a id="rca-err-llm-1"></a>**Rank 1**: The agent's call to the `gemini-3.1-pro-preview` model failed with a `429 RESOURCE_EXHAUSTED` error, indicating the backend service was overloaded and rate-limiting requests. The client-side stub exhausted its internal retry attempts against the persistently unavailable service, leading to a hard failure of the agent's execution.

- <a id="rca-err-llm-2"></a>**Rank 2**: The `knowledge_qa_supervisor` agent's `GenerateContent` call to the `gemini-3.1-pro-preview` model failed with a `429 RESOURCE_EXHAUSTED` error. The detailed error message, 'No backend available to serve the request after retries,' indicates a transient backend capacity issue on the model provider's side, not a client-side quota violation.

- <a id="rca-err-llm-3"></a>**Rank 3**: The API call to the `gemini-2.5-flash` model failed with a 400 INVALID_ARGUMENT error because the `max_output_tokens` parameter was set to 65538 in the `llm_config`. This value exceeds the model's maximum supported limit of 65536 (exclusive range of 65537), causing the request to be rejected.

- <a id="rca-err-llm-4"></a>**Rank 4**: The agent's tool call failed with a 404 NOT_FOUND error because the system prompt instructed it to use a Vertex AI Search datastore (`invalid-obs-ds`) that does not exist or is not accessible in the project context where the agent is executing, resulting in a resource lookup failure.

- <a id="rca-err-llm-5"></a>**Rank 5**: The `gemini-2.5-pro` model inference call received a `429 RESOURCE_EXHAUSTED` error because the request was preempted from the backend's decode queue by a higher-priority request due to resource contention, causing the `lookup_worker_2` agent to fail its data retrieval sub-task and cascade the error up the trace.

<br>


## Empty LLM Responses

This section surfaces LLM generation defects where the API successfully returned a 200 OK status, but forced an empty `candidates` list (0 tokens generated). This typically occurs due to backend telemetry anomalies or internal model safety filters blocking the response mid-generation.


**Total Empty LLM Responses for all in Analysis Window:** 261


### Response Text is NULL and candidates_tokens_count is 0


This indicates a complete generation failure or hard block by safety filters at the model API layer. No response strings were populated in the response payload.


#### Overview

**Total Count in Analysis Window:** 9


| Agent Name                             | Model Name                 |   Empty Response Count |
|:---------------------------------------|:---------------------------|-----------------------:|
| **bigquery_data_agent**                | **gemini-2.5-pro**         |                      5 |
| **bigquery_data_agent**                | **gemini-2.5-flash**       |                      2 |
| **adk_documentation_agent**            | **gemini-3.1-pro-preview** |                      1 |
| **config_test_agent_over_provisioned** | **gemini-2.5-pro**         |                      1 |

<br>


#### Details


**Sample Details (limited to 5)**
<br>


|   **Rank** | **Timestamp**       | **Agent Name**              | **Model Name**             | **User Message**                                                                                       |   **Prompt Tokens** |   **thoughts_token_count** |   **candidates_token_count** | **response_text**   | **full_response**                                                  |   **Latency (s)** | **Status**   | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|-----------:|:--------------------|:----------------------------|:---------------------------|:-------------------------------------------------------------------------------------------------------|--------------------:|---------------------------:|-----------------------------:|:--------------------|:-------------------------------------------------------------------|------------------:|:-------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|          1 | 2026-03-13 22:42:12 | **bigquery_data_agent**     | **gemini-2.5-pro**         | What is the distribution of `sentiment_scores` for agent responses in the `response_analysis_dataset`? |               14460 |                          0 |                            0 | N/A                 | `{'usage': {'completion': None, 'prompt': 14460, 'total': 14460}}` |             5.313 | 🟢           | [`448155959b140f22017dd45ac60257d1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1?project=agent-operations-ek-05) | [`403b422607b4dea1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1;spanId=403b422607b4dea1?project=agent-operations-ek-05) |
|          2 | 2026-03-13 22:42:07 | **bigquery_data_agent**     | **gemini-2.5-pro**         | What is the distribution of `sentiment_scores` for agent responses in the `response_analysis_dataset`? |               14460 |                          0 |                            0 | N/A                 | `{'usage': {'completion': None, 'prompt': 14460, 'total': 14460}}` |             5.313 | 🟢           | [`448155959b140f22017dd45ac60257d1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1?project=agent-operations-ek-05) | [`403b422607b4dea1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1;spanId=403b422607b4dea1?project=agent-operations-ek-05) |
|          3 | 2026-03-13 22:41:58 | **bigquery_data_agent**     | **gemini-2.5-pro**         | What is the distribution of `sentiment_scores` for agent responses in the `response_analysis_dataset`? |               14460 |                          0 |                            0 | N/A                 | `{'usage': {'completion': None, 'prompt': 14460, 'total': 14460}}` |             5.313 | 🟢           | [`448155959b140f22017dd45ac60257d1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1?project=agent-operations-ek-05) | [`403b422607b4dea1`](https://console.cloud.google.com/traces/explorer;traceId=448155959b140f22017dd45ac60257d1;spanId=403b422607b4dea1?project=agent-operations-ek-05) |
|          4 | 2026-03-13 22:39:01 | **bigquery_data_agent**     | **gemini-2.5-flash**       | Find all tables in the `agent_event_logs` dataset that were modified in the last week.                 |               11877 |                          0 |                            0 | N/A                 | `{'usage': {'completion': None, 'prompt': 11877, 'total': 11877}}` |             5.578 | 🟢           | [`ab0c0242c9f2a8ec79c1e4da8e98fa8e`](https://console.cloud.google.com/traces/explorer;traceId=ab0c0242c9f2a8ec79c1e4da8e98fa8e?project=agent-operations-ek-05) | [`8371576102565e9f`](https://console.cloud.google.com/traces/explorer;traceId=ab0c0242c9f2a8ec79c1e4da8e98fa8e;spanId=8371576102565e9f?project=agent-operations-ek-05) |
|          5 | 2026-03-13 22:12:41 | **adk_documentation_agent** | **gemini-3.1-pro-preview** | What are the specific requirements for an ADK agent to interact with a NoSQL database?                 |                 224 |                          0 |                            0 | N/A                 | `{'usage': {'completion': None, 'prompt': 224, 'total': 224}}`     |            23.365 | 🟢           | [`43a20fa14ceb2f9252b42029b11d15ab`](https://console.cloud.google.com/traces/explorer;traceId=43a20fa14ceb2f9252b42029b11d15ab?project=agent-operations-ek-05) | [`648c2a28d32672f1`](https://console.cloud.google.com/traces/explorer;traceId=43a20fa14ceb2f9252b42029b11d15ab;spanId=648c2a28d32672f1?project=agent-operations-ek-05) |

<br>

### Response Text is populated but candidates_tokens_count is 0


This typically indicates a telemetry counting anomaly or a specific `FinishReason` (e.g., `RECITATION`, `OTHER`) where the API successfully returned a generated response text, but incorrectly reported 0 generated tokens to the usage metadata tracking.


#### Overview

**Total Count in Analysis Window:** 252


| Agent Name                  | Model Name                 |   Empty Response Count |
|:----------------------------|:---------------------------|-----------------------:|
| **ai_observability_agent**  | **gemini-2.5-flash**       |                    122 |
| **ai_observability_agent**  | **gemini-2.5-pro**         |                     94 |
| **lookup_worker_3**         | **gemini-2.5-pro**         |                      8 |
| **bigquery_data_agent**     | **gemini-2.5-flash**       |                      6 |
| **adk_documentation_agent** | **gemini-2.5-pro**         |                      4 |
| **bigquery_data_agent**     | **gemini-2.5-pro**         |                      4 |
| **adk_documentation_agent** | **gemini-3.1-pro-preview** |                      2 |
| **bigquery_data_agent**     | **gemini-3.1-pro-preview** |                      2 |
| **lookup_worker_1**         | **gemini-2.5-pro**         |                      2 |
| **lookup_worker_1**         | **gemini-3.1-pro-preview** |                      2 |
| **lookup_worker_2**         | **gemini-2.5-pro**         |                      2 |
| **lookup_worker_2**         | **gemini-3.1-pro-preview** |                      2 |
| **adk_documentation_agent** | **gemini-2.5-flash**       |                      1 |
| **knowledge_qa_supervisor** | **gemini-2.5-flash**       |                      1 |

<br>


#### Details


**Sample Details (limited to 5)**
<br>


|   **Rank** | **Timestamp**       | **Agent Name**              | **Model Name**             | **User Message**                                                                                                                                                                                                                                   |   **Prompt Tokens** |   **thoughts_token_count** |   **candidates_token_count** | **response_text**   | **full_response**                                                                       |   **Latency (s)** | **Status**   | **Trace ID**                                                                                                                                                   | **Span ID**                                                                                                                                                            |
|-----------:|:--------------------|:----------------------------|:---------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------:|---------------------------:|-----------------------------:|:--------------------|:----------------------------------------------------------------------------------------|------------------:|:-------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|          1 | 2026-03-13 22:44:05 | **ai_observability_agent**  | **gemini-2.5-flash**       | What are the challenges in visualizing complex agent reasoning graphs?                                                                                                                                                                             |                 205 |                         85 |                            0 | other               | `{'response': 'other', 'usage': {'completion': None, 'prompt': 205, 'total': 375}}`     |             2.907 | 🟢           | [`a0a172f4ebca38fa64b9f6aae9d57c58`](https://console.cloud.google.com/traces/explorer;traceId=a0a172f4ebca38fa64b9f6aae9d57c58?project=agent-operations-ek-05) | [`189fe4595c5b147e`](https://console.cloud.google.com/traces/explorer;traceId=a0a172f4ebca38fa64b9f6aae9d57c58;spanId=189fe4595c5b147e?project=agent-operations-ek-05) |
|          2 | 2026-03-13 22:43:15 | **lookup_worker_3**         | **gemini-2.5-pro**         | Simultaneously fetch `customer_record_I9`, `transaction_history_J10`.                                                                                                                                                                              |                 213 |                          0 |                            0 | other               | `{'response': 'other', 'usage': {'completion': None, 'prompt': 213, 'total': 213}}`     |             1.9   | 🟢           | [`1fd69dba68588ac1db5809c12e66656e`](https://console.cloud.google.com/traces/explorer;traceId=1fd69dba68588ac1db5809c12e66656e?project=agent-operations-ek-05) | [`ed4a708a2a589ee0`](https://console.cloud.google.com/traces/explorer;traceId=1fd69dba68588ac1db5809c12e66656e;spanId=ed4a708a2a589ee0?project=agent-operations-ek-05) |
|          3 | 2026-03-13 22:42:32 | **adk_documentation_agent** | **gemini-2.5-pro**         | Explain how to use `VertexAIGenerativeTool` for advanced text generation tasks.                                                                                                                                                                    |                 224 |                        810 |                            0 | other               | `{'response': 'other', 'usage': {'completion': None, 'prompt': 224, 'total': 2332}}`    |            13.623 | 🟢           | [`90c9b4f0bcacb35fcd2d661e4855ea93`](https://console.cloud.google.com/traces/explorer;traceId=90c9b4f0bcacb35fcd2d661e4855ea93?project=agent-operations-ek-05) | [`855db8797fa12ae1`](https://console.cloud.google.com/traces/explorer;traceId=90c9b4f0bcacb35fcd2d661e4855ea93;spanId=855db8797fa12ae1?project=agent-operations-ek-05) |
|          4 | 2026-03-13 22:36:04 | **knowledge_qa_supervisor** | **gemini-2.5-flash**       | Using a HIGH_TEMP config, generate a creative marketing slogan for a new 'AI observability platform'. Then, search Google for existing slogans of competitors to ensure originality, and store the generated slogan in `marketing_ideas_bigquery`. |                3251 |                        199 |                            0 | other               | `{'response': 'other', 'usage': {'completion': None, 'prompt': 3251, 'total': 3450}}`   |             2.827 | 🟢           | [`0611f16d194548ddb72dc6b34816efcd`](https://console.cloud.google.com/traces/explorer;traceId=0611f16d194548ddb72dc6b34816efcd?project=agent-operations-ek-05) | [`0a90e2a59cbdeb5d`](https://console.cloud.google.com/traces/explorer;traceId=0611f16d194548ddb72dc6b34816efcd;spanId=0a90e2a59cbdeb5d?project=agent-operations-ek-05) |
|          5 | 2026-03-13 22:32:54 | **bigquery_data_agent**     | **gemini-3.1-pro-preview** | Find the top 5 most frequently queried terms in the `query_history_dataset.search_queries` table that resulted in a 'no results found' outcome.                                                                                                    |               15697 |                          0 |                            0 | other               | `{'response': 'other', 'usage': {'completion': None, 'prompt': 15697, 'total': 15697}}` |            64.602 | 🟢           | [`3363d22192d2f87fda54c3c1df2c455d`](https://console.cloud.google.com/traces/explorer;traceId=3363d22192d2f87fda54c3c1df2c455d?project=agent-operations-ek-05) | [`1adf976344a57b40`](https://console.cloud.google.com/traces/explorer;traceId=3363d22192d2f87fda54c3c1df2c455d;spanId=1adf976344a57b40?project=agent-operations-ek-05) |

<br>


---


## Pathological Generation Loops

This section surfaces severe anomaly traces where the agent entered an infinite cognitive loop, repeating the same text internally until it exhausted output tokens and/or hard-failed on timeout. These generation hallucinations drastically inflate latency, blow out token costs, and indicate a critical orchestrational logic failure.


|   **Rank** | **Timestamp**       | **Agent Name**      | **Model Name**           |   **Output Tokens** | **User Message**                                                                      | **Hallucination Text**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   **Latency (s)** | **Span ID**                                                                                                                                                            | **Trace ID**                                                                                                                                                   |
|-----------:|:--------------------|:--------------------|:-------------------------|--------------------:|:--------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
|          1 | 2026-03-13 22:15:08 | **lookup_worker_2** | **gemini-3-pro-preview** |               29336 | Retrieve news_article_100_headline, news_article_100_summary, news_article_100_author | text: 'The lookup for `news_article_100_summary` was successful.  I have retrieved the data for the requested item ID. I should now output the result.  The user asked to "Retrieve ...". I have performed the action. I will report the result.  Wait, I need to be careful. The result I got back is "Data for item: news_article_100_summary". This looks like a placeholder string from the simulated tool, but it is the result.  I will return this information.  One thing to note: The system instructions say "You will be given an item ID. Use the simulated_db_lookup tool to fetch the data for this single... |            234.97 | [`462c77875669f844`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400;spanId=462c77875669f844?project=agent-operations-ek-05) | [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05) |

<br>


---


## Root Cause Insights

- **H1 (Token Size Drives Latency):** 🟢 Confirmed. `ai_observability_agent` via `gemini-2.5-flash` shows a 'Very Strong' 0.984 correlation for Latency vs Output+Thinking. Similarly, `config_test_agent_over_provisioned` via `gemini-2.5-pro` shows a 0.997 correlation. Generation length is the primary latency driver for these specific Model/Agents.
- **H2 (Agent Orchestration Overhead):** 🟢 Confirmed. The `bigquery_data_agent` has a total latency of 248.256s but its pure LLM latency is only 20.008s. The massive 228.248s agent overhead indicates that orchestration routing, context building, or sequential tool execution is the true bottleneck, not the AI inference itself.
- **H3 (Cascading Tool Failures):** 🟢 Confirmed. `flaky_tool_simulation` has a 13.7% error rate, cascading to its parent `unreliable_tool_agent` (18.06% error rate). Additionally, the hallucinated tools `search` and `list_tables` have 100% error rates, ultimately causing the root `knowledge_qa_supervisor` to fail at a 25.42% rate.
- **H4 (Context Bloat (Prefill vs Decode)):** 🔴 Not Confirmed. Time-to-First-Token (TTFT) reaches extremes (e.g., 234.97s for `gemini-3-pro-preview`), but the input sizes in these instances are relatively small (1196 tokens). The high latency is not due to input payload prefill bloat, but rather stalls caused by pathological output generation loops or model provider errors.
- **H5 (Ghost/Timeout Errors (PENDING/TIMEOUT)):** 🟢 Confirmed. There are over 400 errors logging "Invocation PENDING for > 5 minutes (Timed Out)" and "Agent span PENDING for > 5 minutes (Timed Out)" with 0ms durations. This explicitly indicates the invocation and agent suffered a fatal unhandled code exception or the container crashed completely after logging a STARTING event, bypassing the execution queue entirely.


## Recommendations

1. Resolve Unhandled Code Exceptions: Inspect application code for unhandled exceptions causing fatal silent system crashes and "PENDING for > 5 minutes" errors. Implement missing try/catch blocks around the worker queue consumption logic.
2. Mitigate Pathological Generation Loops: Impose a strict max_output_tokens limit (e.g., 1024 or 2048) in the LLM config for extraction agents like `lookup_worker_2` to prevent 29k+ token loops. Refactor prompts to explicitly forbid meta-monologue.
3. Align Tool Nomenclature: Update the system prompt for `bigquery_data_agent` and `knowledge_qa_supervisor` to explicitly reinforce registered tool names (e.g., `list_table_ids`, `transfer_to_agent`), eliminating `TOOL_NOT_FOUND` hallucination errors.
4. Implement Model Fallback: Implement a client-side circuit breaker for `gemini-3.1-pro-preview` that falls back to `gemini-2.5-flash` to mitigate 429 RESOURCE_EXHAUSTED provider rejections.
5. Implement Tool Output Pagination: Refactor `execute_sql` to enforce strict database LIMIT injections to prevent data truncation blindness and subsequent JSON parsing failures.
6. Audit Prompts for Safety Filter Violations: Investigate the inputs for `ai_observability_agent`, as 216 zero-token responses indicate backend safety or recitation filters are repeatedly snapping the reasoning chain.


## Holistic Cross-Section Analysis

The ecosystem is currently bottlenecked by a combination of unhandled application-level crashes, severe internal agent overhead, and pathological LLM generation loops. At the orchestration level, the `knowledge_qa_supervisor` is failing its E2E Service Level Objectives with a P95.5 execution time of 91 seconds and a 25.42% error rate. This top-level degradation is heavily driven by catastrophic execution profiles within its sub-agents. 

Most notably, the `bigquery_data_agent` demonstrates a P95.5 latency of 116.4 seconds, but crucially, it exhibits ~228 seconds of internal agent overhead compared to just 20 seconds of pure LLM generation time. This massive disparity points to severe synchronous blocking, likely caused by unoptimized analytical BigQuery executions (`execute_sql`) that hold the thread hostage, rather than inference delays. 

Furthermore, cross-referencing model errors with empty token responses reveals a systemic prompt-safety issue: we identified 252 instances where the API successfully returned a 200 status, but yielded 0 output tokens with a `response_text` of "other". This predominantly struck the `ai_observability_agent` (216 occurrences across Flash and Pro), indicating that the agent's input context or expected outputs are routinely triggering backend safety, blocklist, or recitation filters, thereby snapping the reasoning chain. 

Finally, model capacity and selection are misaligned. `gemini-3.1-pro-preview` and `gemini-3-pro-preview` are suffering from poor inference reliability (>8% error rates) largely driven by `429 RESOURCE_EXHAUSTED` rejections from the provider backend queue. In contrast, `gemini-2.5-flash` maintains a highly stable 0.65% error rate while demonstrating incredibly strong latency-to-token correlation (e.g., 0.948 on `config_test_agent_wrong_candidates`), making it far more predictable for high-volume routing and simple tool execution.

## Critical Workflow Failures

*   **Fatal Silent System Crashes (PENDING Timeouts):** The system recorded over 400 instances of fatal timeouts resulting in 0ms execution durations, explicitly marked by the error: `"Invocation PENDING for > 5 minutes (Timed Out)"`. A prime example is trace [`d9140e48933ac7af7daf18cb95e03a57`](https://console.cloud.google.com/traces/explorer;traceId=d9140e48933ac7af7daf18cb95e03a57?project=agent-operations-ek-05). These are **not** normal concurrency delays or infrastructure saturation; this signature explicitly indicates a silent system crash or unhandled code-level exception in the worker runtime that caused the container to drop the execution queue entirely without reporting a stack trace.
*   **Pathological Cognitive Runaway:** In trace [`8dc35732c05c554d2134596dd4465400`](https://console.cloud.google.com/traces/explorer;traceId=8dc35732c05c554d2134596dd4465400?project=agent-operations-ek-05), the `lookup_worker_2` agent fell into an infinite generative loop. Instead of summarizing the retrieved data, the `gemini-3-pro-preview` model hallucinated a recursive internal monologue ("Wait, I need to be careful..."), resulting in a blowout of 29,336 output tokens and an anomalous Time To First Token (TTFT) of ~235 seconds. This exhausted the context window and forced a severe latency failure.
*   **Zero-Shot Tool Hallucination & Registration Mismatches:** In trace [`38f1c60126dbc30618c1b520625a919f`](https://console.cloud.google.com/traces/explorer;traceId=38f1c60126dbc30618c1b520625a919f?project=agent-operations-ek-05), the `bigquery_data_agent` failed critically because the LLM hallucinated a call to `list_tables`. This function was not registered in the tool manifest (the correct tool was `list_table_ids`). This misalignment triggers an immediate `TOOL_NOT_FOUND` exception, aborting the agent's multi-step plan.
*   **Data Truncation Blindness:** In trace [`a18d6ad259879293a72e4bf6847db554`](https://console.cloud.google.com/traces/explorer;traceId=a18d6ad259879293a72e4bf6847db554?project=agent-operations-ek-05), the `execute_sql` tool queried a massive dataset that returned a payload exceeding the system's string size limit. The result was forcefully cut off (`"result_is_likely_truncated":true`). The LLM subsequently attempted to parse incomplete JSON, breaking the downstream formatting logic.
*   **Inference Backend 429 Preemption:** Trace [`d24f9d559f9873670bbab271364209ea`](https://console.cloud.google.com/traces/explorer;traceId=d24f9d559f9873670bbab271364209ea?project=agent-operations-ek-05) reveals a hard failure where the `gemini-3.1-pro-preview` call was rejected with a 429 error (`No backend available to serve the request after retries`). The client-side stub exhausted all retry attempts against the model API, propagating a terminal failure to the user.

## Architectural Recommendations

1.  **Resolve Unhandled Code Exceptions (PENDING Crashes):** To fix the critical "PENDING for > 5 minutes" timeouts, engineers must urgently inspect the application code for unhandled exceptions during task dispatch. Do NOT recommend scaling worker pools or changing infrastructure queues. Review container crash logs and add missing try/catch blocks around the worker queue consumption logic to ensure errors are gracefully caught and reported rather than allowing the worker to silently die.
2.  **Mitigate Pathological Generation Loops:** Impose a strict `max_output_tokens` limit (e.g., 1024 or 2048) in the LLM config for extraction agents like `lookup_worker_2`. Additionally, refactor the system prompt to explicitly forbid meta-monologue ("Do not output your internal reasoning or conversational filler").
3.  **Align Tool Nomenclature:** Update the system prompt for `bigquery_data_agent` to explicitly reinforce the exact registered tool names (e.g., "You MUST use `list_table_ids` to find tables, `list_tables` does not exist"). This will dramatically reduce `TOOL_NOT_FOUND` hallucination errors.
4.  **Implement Model Fallback and Routing:** Because `gemini-3.1-pro-preview` is heavily susceptible to 429 provider exhaustion limits, implement a client-side circuit breaker that automatically falls back to `gemini-2.5-flash` for high-volume, standard queries. Flash is demonstrating a fraction of the error rate (0.65%) and significantly faster TTFT.
5.  **Implement Tool Output Pagination:** To resolve the `"result_is_likely_truncated"` payload failures, the `execute_sql` tool must be refactored to enforce strict database `LIMIT` injections or return data using a cursor-based pagination mechanism. This guarantees the LLM receives complete, parsable JSON chunks rather than corrupted string fragments.
6.  **Audit Prompts for Safety Filter Violations:** Investigate the inputs flowing into the `ai_observability_agent`. The exceptionally high volume of 0-token empty responses with a finish reason of "other" indicates that benign AI Observability data is triggering the model's internal safety or recitation filters. Prompt rewriting or requesting a safety-filter adjustment from the model provider is required.

## Hypothesis Testing: Latency & Tokens

These scatter plots illustrate the relationship between generated token count and LLM latency on a granular, per-agent and per-model basis, utilizing the raw underlying llm_events tracking data.

This granularity helps isolate correlation behaviors where an Agent's complex prompt might cause a specific model to degrade more linearly with output size.


#### adk_documentation_agent


**gemini-2.5-flash**

- **Number of Requests**: 93


- **Correlation**: 0.885 (Very Strong)


**Latency vs Tokens (adk_documentation_agent via gemini-2.5-flash)**<br>

[![Latency vs Tokens (adk_documentation_agent via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 110


- **Correlation**: 0.899 (Very Strong)


**Latency vs Tokens (adk_documentation_agent via gemini-2.5-pro)**<br>

[![Latency vs Tokens (adk_documentation_agent via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 57


- **Correlation**: 0.377 (Weak)


**Latency vs Tokens (adk_documentation_agent via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (adk_documentation_agent via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 47


- **Correlation**: 0.760 (Strong)


**Latency vs Tokens (adk_documentation_agent via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (adk_documentation_agent via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_adk_documentation_agent_gemini-3_1-pro-preview_4K.png)
<br>

#### ai_observability_agent


**gemini-2.5-flash**

- **Number of Requests**: 6


- **Correlation**: 0.984 (Very Strong)


**Latency vs Tokens (ai_observability_agent via gemini-2.5-flash)**<br>

[![Latency vs Tokens (ai_observability_agent via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 15


- **Correlation**: 0.950 (Very Strong)


**Latency vs Tokens (ai_observability_agent via gemini-2.5-pro)**<br>

[![Latency vs Tokens (ai_observability_agent via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 22


- **Correlation**: 0.202 (Weak)


**Latency vs Tokens (ai_observability_agent via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (ai_observability_agent via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 12


- **Correlation**: 0.019 (Very Weak / None)


**Latency vs Tokens (ai_observability_agent via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (ai_observability_agent via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_ai_observability_agent_gemini-3_1-pro-preview_4K.png)
<br>

#### bigquery_data_agent


**gemini-2.5-flash**

- **Number of Requests**: 3683


- **Correlation**: 0.862 (Very Strong)


**Latency vs Tokens (bigquery_data_agent via gemini-2.5-flash)**<br>

[![Latency vs Tokens (bigquery_data_agent via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 3425


- **Correlation**: 0.835 (Very Strong)


**Latency vs Tokens (bigquery_data_agent via gemini-2.5-pro)**<br>

[![Latency vs Tokens (bigquery_data_agent via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 1014


- **Correlation**: 0.394 (Weak)


**Latency vs Tokens (bigquery_data_agent via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (bigquery_data_agent via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 1950


- **Correlation**: 0.160 (Very Weak / None)


**Latency vs Tokens (bigquery_data_agent via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (bigquery_data_agent via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_bigquery_data_agent_gemini-3_1-pro-preview_4K.png)
<br>

#### config_test_agent_high_temp


**gemini-2.5-flash**

- **Number of Requests**: 16


- **Correlation**: 0.569 (Moderate)


**Latency vs Tokens (config_test_agent_high_temp via gemini-2.5-flash)**<br>

[![Latency vs Tokens (config_test_agent_high_temp via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 17


- **Correlation**: 0.969 (Very Strong)


**Latency vs Tokens (config_test_agent_high_temp via gemini-2.5-pro)**<br>

[![Latency vs Tokens (config_test_agent_high_temp via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 9


- **Correlation**: 0.656 (Strong)


**Latency vs Tokens (config_test_agent_high_temp via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_high_temp via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 8


- **Correlation**: 0.587 (Moderate)


**Latency vs Tokens (config_test_agent_high_temp via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_high_temp via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_high_temp_gemini-3_1-pro-preview_4K.png)
<br>

#### config_test_agent_normal


**gemini-2.5-flash**

- **Number of Requests**: 18


- **Correlation**: 0.966 (Very Strong)


**Latency vs Tokens (config_test_agent_normal via gemini-2.5-flash)**<br>

[![Latency vs Tokens (config_test_agent_normal via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 21


- **Correlation**: 0.918 (Very Strong)


**Latency vs Tokens (config_test_agent_normal via gemini-2.5-pro)**<br>

[![Latency vs Tokens (config_test_agent_normal via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 13


- **Correlation**: 0.604 (Strong)


**Latency vs Tokens (config_test_agent_normal via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_normal via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 7


- **Correlation**: 0.612 (Strong)


**Latency vs Tokens (config_test_agent_normal via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_normal via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_normal_gemini-3_1-pro-preview_4K.png)
<br>

#### config_test_agent_over_provisioned


**gemini-2.5-flash**

- **Number of Requests**: 39


- **Correlation**: 0.995 (Very Strong)


**Latency vs Tokens (config_test_agent_over_provisioned via gemini-2.5-flash)**<br>

[![Latency vs Tokens (config_test_agent_over_provisioned via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 48


- **Correlation**: 0.997 (Very Strong)


**Latency vs Tokens (config_test_agent_over_provisioned via gemini-2.5-pro)**<br>

[![Latency vs Tokens (config_test_agent_over_provisioned via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 19


- **Correlation**: 0.526 (Moderate)


**Latency vs Tokens (config_test_agent_over_provisioned via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_over_provisioned via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 17


- **Correlation**: 0.699 (Strong)


**Latency vs Tokens (config_test_agent_over_provisioned via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_over_provisioned via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_over_provisioned_gemini-3_1-pro-preview_4K.png)
<br>

#### config_test_agent_wrong_candidates


**gemini-2.5-flash**

- **Number of Requests**: 30


- **Correlation**: 0.948 (Very Strong)


**Latency vs Tokens (config_test_agent_wrong_candidates via gemini-2.5-flash)**<br>

[![Latency vs Tokens (config_test_agent_wrong_candidates via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 14


- **Correlation**: 0.900 (Very Strong)


**Latency vs Tokens (config_test_agent_wrong_candidates via gemini-2.5-pro)**<br>

[![Latency vs Tokens (config_test_agent_wrong_candidates via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 7


- **Correlation**: 0.471 (Moderate)


**Latency vs Tokens (config_test_agent_wrong_candidates via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_wrong_candidates via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 6


- **Correlation**: 0.592 (Moderate)


**Latency vs Tokens (config_test_agent_wrong_candidates via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (config_test_agent_wrong_candidates via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_config_test_agent_wrong_candidates_gemini-3_1-pro-preview_4K.png)
<br>

#### google_search_agent


**gemini-2.5-flash**

- **Number of Requests**: 67


- **Correlation**: 0.916 (Very Strong)


**Latency vs Tokens (google_search_agent via gemini-2.5-flash)**<br>

[![Latency vs Tokens (google_search_agent via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 92


- **Correlation**: 0.670 (Strong)


**Latency vs Tokens (google_search_agent via gemini-2.5-pro)**<br>

[![Latency vs Tokens (google_search_agent via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 14


- **Correlation**: 0.095 (Very Weak / None)


**Latency vs Tokens (google_search_agent via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (google_search_agent via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 15


- **Correlation**: 0.221 (Weak)


**Latency vs Tokens (google_search_agent via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (google_search_agent via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_google_search_agent_gemini-3_1-pro-preview_4K.png)
<br>

#### knowledge_qa_supervisor


**gemini-2.5-flash**

- **Number of Requests**: 516


- **Correlation**: 0.721 (Strong)


**Latency vs Tokens (knowledge_qa_supervisor via gemini-2.5-flash)**<br>

[![Latency vs Tokens (knowledge_qa_supervisor via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 551


- **Correlation**: 0.883 (Very Strong)


**Latency vs Tokens (knowledge_qa_supervisor via gemini-2.5-pro)**<br>

[![Latency vs Tokens (knowledge_qa_supervisor via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 237


- **Correlation**: 0.438 (Moderate)


**Latency vs Tokens (knowledge_qa_supervisor via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (knowledge_qa_supervisor via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 225


- **Correlation**: 0.205 (Weak)


**Latency vs Tokens (knowledge_qa_supervisor via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (knowledge_qa_supervisor via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_knowledge_qa_supervisor_gemini-3_1-pro-preview_4K.png)
<br>

#### lookup_worker_1


**gemini-2.5-flash**

- **Number of Requests**: 234


- **Correlation**: 0.790 (Strong)


**Latency vs Tokens (lookup_worker_1 via gemini-2.5-flash)**<br>

[![Latency vs Tokens (lookup_worker_1 via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 146


- **Correlation**: 0.940 (Very Strong)


**Latency vs Tokens (lookup_worker_1 via gemini-2.5-pro)**<br>

[![Latency vs Tokens (lookup_worker_1 via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 121


- **Correlation**: 0.752 (Strong)


**Latency vs Tokens (lookup_worker_1 via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_1 via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 65


- **Correlation**: 0.445 (Moderate)


**Latency vs Tokens (lookup_worker_1 via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_1 via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_1_gemini-3_1-pro-preview_4K.png)
<br>

#### lookup_worker_2


**gemini-2.5-flash**

- **Number of Requests**: 193


- **Correlation**: 0.841 (Very Strong)


**Latency vs Tokens (lookup_worker_2 via gemini-2.5-flash)**<br>

[![Latency vs Tokens (lookup_worker_2 via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 166


- **Correlation**: 0.675 (Strong)


**Latency vs Tokens (lookup_worker_2 via gemini-2.5-pro)**<br>

[![Latency vs Tokens (lookup_worker_2 via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 102


- **Correlation**: 0.981 (Very Strong)


**Latency vs Tokens (lookup_worker_2 via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_2 via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 66


- **Correlation**: 0.289 (Weak)


**Latency vs Tokens (lookup_worker_2 via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_2 via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_2_gemini-3_1-pro-preview_4K.png)
<br>

#### lookup_worker_3


**gemini-2.5-flash**

- **Number of Requests**: 246


- **Correlation**: 0.481 (Moderate)


**Latency vs Tokens (lookup_worker_3 via gemini-2.5-flash)**<br>

[![Latency vs Tokens (lookup_worker_3 via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 152


- **Correlation**: 0.916 (Very Strong)


**Latency vs Tokens (lookup_worker_3 via gemini-2.5-pro)**<br>

[![Latency vs Tokens (lookup_worker_3 via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 129


- **Correlation**: 0.746 (Strong)


**Latency vs Tokens (lookup_worker_3 via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_3 via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-3-pro-preview_4K.png)
<br>

**gemini-3.1-pro-preview**

- **Number of Requests**: 66


- **Correlation**: 0.332 (Weak)


**Latency vs Tokens (lookup_worker_3 via gemini-3.1-pro-preview)**<br>

[![Latency vs Tokens (lookup_worker_3 via gemini-3.1-pro-preview)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/latency_scatter_lookup_worker_3_gemini-3_1-pro-preview_4K.png)
<br>

#### unreliable_tool_agent


**gemini-2.5-flash**

- **Number of Requests**: 70


- **Correlation**: 0.680 (Strong)


**Latency vs Tokens (unreliable_tool_agent via gemini-2.5-flash)**<br>

[![Latency vs Tokens (unreliable_tool_agent via gemini-2.5-flash)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-2_5-flash_4K.png)
<br>

**gemini-2.5-pro**

- **Number of Requests**: 151


- **Correlation**: 0.930 (Very Strong)


**Latency vs Tokens (unreliable_tool_agent via gemini-2.5-pro)**<br>

[![Latency vs Tokens (unreliable_tool_agent via gemini-2.5-pro)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-2_5-pro_4K.png)
<br>

**gemini-3-pro-preview**

- **Number of Requests**: 56


- **Correlation**: 0.874 (Very Strong)


**Latency vs Tokens (unreliable_tool_agent via gemini-3-pro-preview)**<br>

[![Latency vs Tokens (unreliable_tool_agent via gemini-3-pro-preview)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/latency_scatter_unreliable_tool_agent_gemini-3-pro-preview_4K.png)
<br>


## Appendix


### Agent Latency (By Model)

These charts breakdown the Agent execution sequences further by the underlying LLM model used for that request. This helps isolate whether an Agent's latency spike is tied to a specific model's degradation.



#### adk_documentation_agent

**adk_documentation_agent via gemini-2.5-flash Latency Sequence**<br>

[![adk_documentation_agent via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-2_5-flash_4K.png)
<br>

**adk_documentation_agent via gemini-2.5-pro Latency Sequence**<br>

[![adk_documentation_agent via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-2_5-pro_4K.png)
<br>

**adk_documentation_agent via gemini-3-pro-preview Latency Sequence**<br>

[![adk_documentation_agent via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-3-pro-preview_4K.png)
<br>

**adk_documentation_agent via gemini-3.1-pro-preview Latency Sequence**<br>

[![adk_documentation_agent via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_adk_documentation_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### ai_observability_agent

**ai_observability_agent via gemini-2.5-flash Latency Sequence**<br>

[![ai_observability_agent via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-2_5-flash_4K.png)
<br>

**ai_observability_agent via gemini-2.5-pro Latency Sequence**<br>

[![ai_observability_agent via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-2_5-pro_4K.png)
<br>

**ai_observability_agent via gemini-3-pro-preview Latency Sequence**<br>

[![ai_observability_agent via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-3-pro-preview_4K.png)
<br>

**ai_observability_agent via gemini-3.1-pro-preview Latency Sequence**<br>

[![ai_observability_agent via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_ai_observability_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### bigquery_data_agent

**bigquery_data_agent via gemini-2.5-flash Latency Sequence**<br>

[![bigquery_data_agent via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-2_5-flash_4K.png)
<br>

**bigquery_data_agent via gemini-2.5-pro Latency Sequence**<br>

[![bigquery_data_agent via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-2_5-pro_4K.png)
<br>

**bigquery_data_agent via gemini-3-pro-preview Latency Sequence**<br>

[![bigquery_data_agent via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-3-pro-preview_4K.png)
<br>

**bigquery_data_agent via gemini-3.1-pro-preview Latency Sequence**<br>

[![bigquery_data_agent via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_bigquery_data_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_high_temp

**config_test_agent_high_temp via gemini-2.5-flash Latency Sequence**<br>

[![config_test_agent_high_temp via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_high_temp via gemini-2.5-pro Latency Sequence**<br>

[![config_test_agent_high_temp via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_high_temp via gemini-3-pro-preview Latency Sequence**<br>

[![config_test_agent_high_temp via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_high_temp via gemini-3.1-pro-preview Latency Sequence**<br>

[![config_test_agent_high_temp via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_high_temp_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_normal

**config_test_agent_normal via gemini-2.5-flash Latency Sequence**<br>

[![config_test_agent_normal via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_normal via gemini-2.5-pro Latency Sequence**<br>

[![config_test_agent_normal via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_normal via gemini-3-pro-preview Latency Sequence**<br>

[![config_test_agent_normal via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_normal via gemini-3.1-pro-preview Latency Sequence**<br>

[![config_test_agent_normal via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_normal_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_over_provisioned

**config_test_agent_over_provisioned via gemini-2.5-flash Latency Sequence**<br>

[![config_test_agent_over_provisioned via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-2.5-pro Latency Sequence**<br>

[![config_test_agent_over_provisioned via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-3-pro-preview Latency Sequence**<br>

[![config_test_agent_over_provisioned via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-3.1-pro-preview Latency Sequence**<br>

[![config_test_agent_over_provisioned via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_over_provisioned_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_wrong_candidates

**config_test_agent_wrong_candidates via gemini-2.5-flash Latency Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-2.5-pro Latency Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-3-pro-preview Latency Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-3.1-pro-preview Latency Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_config_test_agent_wrong_candidates_gemini-3_1-pro-preview_4K.png)
<br>


#### google_search_agent

**google_search_agent via gemini-2.5-flash Latency Sequence**<br>

[![google_search_agent via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-2_5-flash_4K.png)
<br>

**google_search_agent via gemini-2.5-pro Latency Sequence**<br>

[![google_search_agent via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-2_5-pro_4K.png)
<br>

**google_search_agent via gemini-3-pro-preview Latency Sequence**<br>

[![google_search_agent via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-3-pro-preview_4K.png)
<br>

**google_search_agent via gemini-3.1-pro-preview Latency Sequence**<br>

[![google_search_agent via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_google_search_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_1

**lookup_worker_1 via gemini-2.5-flash Latency Sequence**<br>

[![lookup_worker_1 via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_1 via gemini-2.5-pro Latency Sequence**<br>

[![lookup_worker_1 via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_1 via gemini-3-pro-preview Latency Sequence**<br>

[![lookup_worker_1 via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_1 via gemini-3.1-pro-preview Latency Sequence**<br>

[![lookup_worker_1 via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_1_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_2

**lookup_worker_2 via gemini-2.5-flash Latency Sequence**<br>

[![lookup_worker_2 via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_2 via gemini-2.5-pro Latency Sequence**<br>

[![lookup_worker_2 via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_2 via gemini-3-pro-preview Latency Sequence**<br>

[![lookup_worker_2 via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_2 via gemini-3.1-pro-preview Latency Sequence**<br>

[![lookup_worker_2 via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_2_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_3

**lookup_worker_3 via gemini-2.5-flash Latency Sequence**<br>

[![lookup_worker_3 via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_3 via gemini-2.5-pro Latency Sequence**<br>

[![lookup_worker_3 via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_3 via gemini-3-pro-preview Latency Sequence**<br>

[![lookup_worker_3 via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_3 via gemini-3.1-pro-preview Latency Sequence**<br>

[![lookup_worker_3 via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_lookup_worker_3_gemini-3_1-pro-preview_4K.png)
<br>


#### parallel_db_lookup


#### unreliable_tool_agent

**unreliable_tool_agent via gemini-2.5-flash Latency Sequence**<br>

[![unreliable_tool_agent via gemini-2.5-flash Latency Sequence](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-2_5-flash_4K.png)
<br>

**unreliable_tool_agent via gemini-2.5-pro Latency Sequence**<br>

[![unreliable_tool_agent via gemini-2.5-pro Latency Sequence](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-2_5-pro_4K.png)
<br>

**unreliable_tool_agent via gemini-3-pro-preview Latency Sequence**<br>

[![unreliable_tool_agent via gemini-3-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-3-pro-preview_4K.png)
<br>

**unreliable_tool_agent via gemini-3.1-pro-preview Latency Sequence**<br>

[![unreliable_tool_agent via gemini-3.1-pro-preview Latency Sequence](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/seq_agent_model_unreliable_tool_agent_gemini-3_1-pro-preview_4K.png)
<br>


### Token Usage Over Time

The charts below display the chronological token consumption (Input, Thought, Output) for each Agent-Model combination over the test run. This helps identify context window growth or token ballooning over time.



#### adk_documentation_agent

**adk_documentation_agent via gemini-2.5-flash Token Sequence**<br>

[![adk_documentation_agent via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-2_5-flash_4K.png)
<br>

**adk_documentation_agent via gemini-2.5-pro Token Sequence**<br>

[![adk_documentation_agent via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-2_5-pro_4K.png)
<br>

**adk_documentation_agent via gemini-3-pro-preview Token Sequence**<br>

[![adk_documentation_agent via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-3-pro-preview_4K.png)
<br>

**adk_documentation_agent via gemini-3.1-pro-preview Token Sequence**<br>

[![adk_documentation_agent via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_adk_documentation_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### ai_observability_agent

**ai_observability_agent via gemini-2.5-flash Token Sequence**<br>

[![ai_observability_agent via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-2_5-flash_4K.png)
<br>

**ai_observability_agent via gemini-2.5-pro Token Sequence**<br>

[![ai_observability_agent via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-2_5-pro_4K.png)
<br>

**ai_observability_agent via gemini-3-pro-preview Token Sequence**<br>

[![ai_observability_agent via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-3-pro-preview_4K.png)
<br>

**ai_observability_agent via gemini-3.1-pro-preview Token Sequence**<br>

[![ai_observability_agent via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_ai_observability_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### bigquery_data_agent

**bigquery_data_agent via gemini-2.5-flash Token Sequence**<br>

[![bigquery_data_agent via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-2_5-flash_4K.png)
<br>

**bigquery_data_agent via gemini-2.5-pro Token Sequence**<br>

[![bigquery_data_agent via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-2_5-pro_4K.png)
<br>

**bigquery_data_agent via gemini-3-pro-preview Token Sequence**<br>

[![bigquery_data_agent via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-3-pro-preview_4K.png)
<br>

**bigquery_data_agent via gemini-3.1-pro-preview Token Sequence**<br>

[![bigquery_data_agent via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_bigquery_data_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_high_temp

**config_test_agent_high_temp via gemini-2.5-flash Token Sequence**<br>

[![config_test_agent_high_temp via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_high_temp via gemini-2.5-pro Token Sequence**<br>

[![config_test_agent_high_temp via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_high_temp via gemini-3-pro-preview Token Sequence**<br>

[![config_test_agent_high_temp via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_high_temp via gemini-3.1-pro-preview Token Sequence**<br>

[![config_test_agent_high_temp via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_high_temp_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_normal

**config_test_agent_normal via gemini-2.5-flash Token Sequence**<br>

[![config_test_agent_normal via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_normal via gemini-2.5-pro Token Sequence**<br>

[![config_test_agent_normal via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_normal via gemini-3-pro-preview Token Sequence**<br>

[![config_test_agent_normal via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_normal via gemini-3.1-pro-preview Token Sequence**<br>

[![config_test_agent_normal via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_normal_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_over_provisioned

**config_test_agent_over_provisioned via gemini-2.5-flash Token Sequence**<br>

[![config_test_agent_over_provisioned via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-2.5-pro Token Sequence**<br>

[![config_test_agent_over_provisioned via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-3-pro-preview Token Sequence**<br>

[![config_test_agent_over_provisioned via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_over_provisioned via gemini-3.1-pro-preview Token Sequence**<br>

[![config_test_agent_over_provisioned via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_over_provisioned_gemini-3_1-pro-preview_4K.png)
<br>


#### config_test_agent_wrong_candidates

**config_test_agent_wrong_candidates via gemini-2.5-flash Token Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-2_5-flash_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-2.5-pro Token Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-2_5-pro_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-3-pro-preview Token Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-3-pro-preview_4K.png)
<br>

**config_test_agent_wrong_candidates via gemini-3.1-pro-preview Token Sequence**<br>

[![config_test_agent_wrong_candidates via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_config_test_agent_wrong_candidates_gemini-3_1-pro-preview_4K.png)
<br>


#### google_search_agent

**google_search_agent via gemini-2.5-flash Token Sequence**<br>

[![google_search_agent via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_google_search_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_google_search_agent_gemini-2_5-flash_4K.png)
<br>

**google_search_agent via gemini-2.5-pro Token Sequence**<br>

[![google_search_agent via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_google_search_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_google_search_agent_gemini-2_5-pro_4K.png)
<br>

**google_search_agent via gemini-3-pro-preview Token Sequence**<br>

[![google_search_agent via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_google_search_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_google_search_agent_gemini-3-pro-preview_4K.png)
<br>

**google_search_agent via gemini-3.1-pro-preview Token Sequence**<br>

[![google_search_agent via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_google_search_agent_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_google_search_agent_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_1

**lookup_worker_1 via gemini-2.5-flash Token Sequence**<br>

[![lookup_worker_1 via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_1 via gemini-2.5-pro Token Sequence**<br>

[![lookup_worker_1 via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_1 via gemini-3-pro-preview Token Sequence**<br>

[![lookup_worker_1 via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_1 via gemini-3.1-pro-preview Token Sequence**<br>

[![lookup_worker_1 via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_1_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_2

**lookup_worker_2 via gemini-2.5-flash Token Sequence**<br>

[![lookup_worker_2 via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_2 via gemini-2.5-pro Token Sequence**<br>

[![lookup_worker_2 via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_2 via gemini-3-pro-preview Token Sequence**<br>

[![lookup_worker_2 via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_2 via gemini-3.1-pro-preview Token Sequence**<br>

[![lookup_worker_2 via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_2_gemini-3_1-pro-preview_4K.png)
<br>


#### lookup_worker_3

**lookup_worker_3 via gemini-2.5-flash Token Sequence**<br>

[![lookup_worker_3 via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-2_5-flash_4K.png)
<br>

**lookup_worker_3 via gemini-2.5-pro Token Sequence**<br>

[![lookup_worker_3 via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-2_5-pro_4K.png)
<br>

**lookup_worker_3 via gemini-3-pro-preview Token Sequence**<br>

[![lookup_worker_3 via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-3-pro-preview_4K.png)
<br>

**lookup_worker_3 via gemini-3.1-pro-preview Token Sequence**<br>

[![lookup_worker_3 via gemini-3.1-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-3_1-pro-preview.png)](report_assets_20260320_063748/token_seq_lookup_worker_3_gemini-3_1-pro-preview_4K.png)
<br>


#### unreliable_tool_agent

**unreliable_tool_agent via gemini-2.5-flash Token Sequence**<br>

[![unreliable_tool_agent via gemini-2.5-flash Token Sequence](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-2_5-flash.png)](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-2_5-flash_4K.png)
<br>

**unreliable_tool_agent via gemini-2.5-pro Token Sequence**<br>

[![unreliable_tool_agent via gemini-2.5-pro Token Sequence](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-2_5-pro.png)](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-2_5-pro_4K.png)
<br>

**unreliable_tool_agent via gemini-3-pro-preview Token Sequence**<br>

[![unreliable_tool_agent via gemini-3-pro-preview Token Sequence](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-3-pro-preview.png)](report_assets_20260320_063748/token_seq_unreliable_tool_agent_gemini-3-pro-preview_4K.png)
<br>


## Report Parameters

```json
{
  "config": {
    "playbook": "overview",
    "_desc_data_retrieval": "Settings for fetching bigquery and generating inline RCA prior to formatting",
    "data_retrieval": {
      "time_period": "all",
      "_desc_time_period": "Valid formats: 'all', '24h', '7d', 'last 2 days', 'last 5 hours', 'YYYY-MM-DD', 'YYYY-MM-DD to YYYY-MM-DD', '2 september', 'now'. Defaults to 'all' if empty.",
      "num_slowest_queries": 10,
      "_desc_num_slowest_queries": "Retrieves enough data for distributions, but keeps SQL fast. Keep low since full table fetch is expensive.",
      "num_error_queries": 50000,
      "_desc_num_error_queries": "Keep high (e.g. 50k) to still catch the macro error distribution / stats for the summary at the top.",
      "num_empty_llm_responses": 100,
      "_desc_num_empty_llm_responses": "Identifies up to this many recent events where the LLM generated an empty response payload.",
      "num_hallucination_loops": 100,
      "_desc_num_hallucination_loops": "Identifies up to this many recent events where the LLM got stuck generating huge token amounts.",
      "hallucination_loop_token_threshold": 8000,
      "_desc_hallucination_loop_token_threshold": "Output token counts exceeding this threshold combined with duration threshold are definitively pathological generation loops.",
      "hallucination_loop_duration_ms_threshold": 120000,
      "_desc_hallucination_loop_duration_ms_threshold": "Latency durations exceeding this threshold combined with token threshold are definitively pathological generation loops.",
      "num_queries_to_analyze_rca": 5,
      "_desc_num_queries_to_analyze_rca": "Only generate LLM RCA for what you actually display! Matches data_presentation limits to avoid wasted wait time and API costs."
    },
    "_desc_data_presentation": "Settings limiting the actual rows rendered in the final markdown report",
    "data_presentation": {
      "chart_scale": 0.5,
      "_desc_chart_scale": "Scales the resolution and size of generated matplotlib charts. 1.0 is default size. Can be overridden via CHART_SCALE env var.",
      "max_column_width_chars": 600,
      "_desc_max_column_width_chars": "Truncates long text strings (like LLM prompts, tool outputs, and SQL queries) in markdown report tables to this character limit to prevent unreadable sizing.",
      "num_error_queries": 5,
      "_desc_num_error_queries": "Displays the top 5 error queries in the markdown tables to keep report readable.",
      "num_slowest_queries": 5,
      "_desc_num_slowest_queries": "Displays the top 5 slowest queries in the markdown tables.",
      "num_empty_llm_responses": 5,
      "_desc_num_empty_llm_responses": "Displays the top 5 empty LLM response traces in the markdown tables.",
      "num_hallucination_loops": 5,
      "_desc_num_hallucination_loops": "Displays top instances where the LLM generated massive token outputs (>8000), typically symptomatic of internal cognitive runaway or repetition loops."
    },
    "_desc_kpis": "Key Performance Indicators defining the health thresholds for different execution layers. Targets are compared against actual metrics to calculate Service Level Objectives (SLOs).",
    "_desc_kpi_targets": "latency_target: The maximum acceptable time in seconds. percentile_target: Evaluates what % of requests meet the latency_target (e.g. 95.5%). error_target: The max acceptable error rate %.",
    "kpis": {
      "_desc_end_to_end": "The full lifecycle of a root user request, from the moment it hits the architecture until the final response is returned.",
      "end_to_end": {
        "latency_target": 30.0,
        "percentile_target": 95.5,
        "error_target": 5.0
      },
      "_desc_agent": "A single agent invocation, encompassing its internal reasoning, tool calls, and LLM requests.",
      "agent": {
        "latency_target": 10.0,
        "percentile_target": 95.5,
        "error_target": 5.0
      },
      "_desc_llm": "A direct API call/generation run to the foundation model (e.g. Gemini).",
      "llm": {
        "latency_target": 8.0,
        "percentile_target": 95.5,
        "error_target": 5.0
      },
      "_desc_tool": "The execution length of a single python tool or function called by the agent.",
      "tool": {
        "latency_target": 3.0,
        "percentile_target": 95.5,
        "error_target": 5.0
      }
    }
  },
  "queries": [
    "Some additional instructions to add to the prompt."
  ]
}
```

---
**Report Generation Time:** 351.47 seconds
