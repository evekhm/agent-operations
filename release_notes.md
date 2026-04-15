# Release Notes

## v0.1.1  (Agent Quality Report, Knowledge Supervisor & A2A Support)

### 📊 Agent Response Quality Analysis
* **AI-Powered Quality Evaluation:** Added a new "Response Quality Analysis" section to the observability report. Each agent session is evaluated by AI on two dimensions: **Response Usefulness** (meaningful / unhelpful / partial) and **Task Grounding** (grounded / ungrounded / no tool needed).
* **AI Analysis Summary:** LLM-generated summary identifies failing agents, patterns, and root causes (e.g., detecting that a specific agent fails on most queries due to a broken datastore).
* **Per-Agent Quality Breakdown:** Table showing per-agent helpful/unhelpful/grounded rates with status indicators, making it easy to spot which agents need attention.
* **Quality Scorecard & Pie Charts:** Report includes a quality scorecard with pass/warn/fail indicators, category distribution tables, and pie charts for visual breakdown.
* **Executive Summary Integration:** Quality metrics (quality rate, unhelpful rate, grounding rate) are now surfaced in the executive summary at the top of the report.
* **Configurable Limits:** Quality evaluation session limit (`quality_eval_limit`) and number of example sessions (`num_quality_examples`) are configurable via `config.json`.

### 📡 Query & Response CLI (`query_responses_sdk.sh`)
* **Combined CLI:** Single script for browsing Q&A pairs and running full quality evaluation. Eval is on by default; use `--no-eval` to browse only.
* **Usage:**
  - `query_responses_sdk.sh` — Evaluate last 100 sessions (default)
  - `query_responses_sdk.sh --limit 500` — Evaluate more sessions
  - `query_responses_sdk.sh --time_period 7d` — Evaluate last 7 days
  - `query_responses_sdk.sh --no-eval` — Browse Q&A pairs without evaluation
  - `query_responses_sdk.sh --session <id>` — Single-session deep dive
  - `query_responses_sdk.sh --persist` — Persist results to BigQuery
* **Per-Agent Breakdown:** Eval output includes per-agent quality summary with helpful/unhelpful percentages.
* **Auto-Logging:** Eval runs are automatically logged to `logs/quality_eval_<timestamp>.log`.

### 🔗 A2A Trace Correlation Gap Workaround
* **Problem:** When the supervisor agent transfers to a remote A2A agent (e.g., `pto_agent` on Cloud Run), the remote agent logs under a different `session_id`. The SDK's `trace.final_response` returns `None` or `"call:..."` strings, causing sessions to appear as "no response" and be rated as unhelpful.
* **`tool_origin` Detection:** Uses `tool_origin` field (`TRANSFER_A2A` vs `TRANSFER_AGENT`) to accurately distinguish remote A2A agents from local sub-agents, preventing false A2A detection.
* **`A2A_INTERACTION` Support:** Parses `A2A_INTERACTION` events (from ADK PR #5325) to extract remote agent responses from `artifacts[].parts[].text`.
* **Single-Word Filter:** Filters out routing/classification outputs like `"other"` that are not real responses.
* **Time-Window Fallback:** For older data without `tool_origin`, falls back to time-window matching against `AGENT_STARTING`/`COMPLETED` timestamps.
* **A2A Re-Evaluation:** Sessions rated "unhelpful" due to missing A2A responses are automatically re-evaluated with the resolved response. Disable with `--no-a2a-fix`.
* **Upstream PR:** Contributed fix to ADK: [google/adk-python#5325](https://github.com/google/adk-python/pull/5325) — adds `A2A_INTERACTION` event type and `TRANSFER_A2A` classification.

### 🤖 Knowledge Supervisor Agent (New)
* **Multi-Agent Supervisor:** Added `knowledge_supervisor` agent that orchestrates sub-agents and remote A2A agents for knowledge-based Q&A.
* **Agent Engine Deployment:** Deployable to Vertex AI Agent Engine with full Terraform infrastructure (Cloud Build triggers, IAM, telemetry, storage).
* **Remote A2A Integration:** Supports `transfer_to_agent` to remote agents (e.g., `pto_agent`) deployed on Cloud Run.
* **Deploy Script:** `deploy.sh` handles Agent Engine deployment with environment configuration.
* **Evaluation & Testing:** Includes eval sets, integration tests, and notebook-based evaluation (`evaluating_adk_agent.ipynb`).

### 🏖️ PTO Agent (New)
* **Remote A2A Agent:** Added `pto_agent` — a standalone agent deployed to Cloud Run that handles PTO/leave-related queries via A2A protocol.
* **Cloud Run Deployment:** Includes `deploy.sh`, `Makefile`, and `agent.json` for Cloud Run deployment with A2A support.
* **Test Suite:** Remote agent tests and agent card validation scripts.

### 🔄 Load Test Agent (New)
* **Load Generator:** Added `load_test_agent` — a Cloud Run Job that generates synthetic load against the knowledge supervisor agent.
* **Configurable Load:** Supports configurable concurrency, query count, and target agent URL.
* **Deploy & Run Scripts:** `deploy.sh` for Cloud Run Job deployment, `run_job.sh` to trigger load generation.

### 🧪 CA Agent (New)
* **Conversational Agent:** Added `ca_agent` with MCP Developer Knowledge API tool integration, custom tools, glossary support, and example queries.

### ⚙️ Infrastructure & Configuration
* **`config.json` Enhancements:** Added `quality_eval_limit` (default 1000) and `num_quality_examples` (default 10) to control quality evaluation scope and report detail.
* **`tool_origin` in Views:** Added `tool_origin` column to tool events SQL view for distinguishing local, MCP, A2A, and transfer tools.
* **Deployment Script:** Added top-level `deploy.sh` for coordinated agent deployment.
* **Setup Script Updates:** Updated `setup.sh` with additional dependencies and configuration.

## v0.0.5  (Bug Fixes)
### 📊 Report Generation & Visualizations
* **Query Initialization**: Added strict logic to verify if target BigQuery views exist or require creation before issuing queries.
### ⚙️ Data Pipeline & OpenTelemetry Support
* **Observability Agent Plugin**: Enabled the `BigQueryAgentAnalyticsPlugin` by default when running via the `generate_report.sh` script.
* **Telemetry Cleanup**: Resolved a telemetry typo that prevented deterministic event tracking across different stages of the execution cycle.
### 🛠️ Tooling & Configuration
* **Logging Architecture**: Unified the logging configuration across all files.
* **Codebase Cleanup**: Removed stale and unused prompt files and deprecated reference scripts.

## v0.0.4  (Bug Fixes & Observability Hardening)
### 📊 Report Generation & Visualizations
* **Empty LLM Responses Analysis:** Enhanced "Empty LLM Responses".
* **Pathological Generation Loops:** Added detection and reporting for massive token exhaustive hallucinations.
* **RCA Rate Limit Recovery:** Added exponential backoff retry loop (up to 5 attempts) to gracefully handle intermittent Vertex AI 429 Rate Limits during automated root cause analysis.
* **Massive Payload Safeguard:** Added strict text truncation inside the RCA prompt generation to prevent pathological token loops from intentionally crashing the Vertex API quota (controlled via the new `RCA_PAYLOAD_TRUNCATION_LIMIT` parameter in `.env.sample`).
* **RCA Metadata Tracking:** Introduced detailed logging that summarizes success, retry recovery, and failure rates at the conclusion of the inline RCA phase.
* **RCA Column Persistence:** fixed arbitrary truncation limits on the Root Cause Analysis (`rca_analysis`) dataset, ensuring full AI SRE explanations render cleanly in the markdown payload.
* **Correlated Metrics:** Introduced new "Latency vs Input Token" correlation charts to the underlying observability pipeline.
* **Metadata Transparency:** The underlying agent model used to generate the report itself is now explicitly tagged in the metadata table.
* **Performance**: Disabled PDF generation since iot was taking up time and generated layout still needs significant improvements and was not usable as is.
### 🧠 AI SRE & Prompt Hardening
* **Timeout Hallucinations:** Implemented strict negative prompting boundaries for the AI SRE to prevent it from inventing infrastructure lockups, worker starvation, or queue exhaustion during unresolved `PENDING` timeout events.
* **Chronological Hypothesis Testing:** Reordered the AI insight injection pipeline so hypothesis charts evaluate chronologically under architectural recommendations.
### ⚙️ Data Pipeline & OpenTelemetry Support
* **Robust OTel Join Logic:** With OTel enabled, LLM_REQUEST/LLM_RESPONSE appear in different spans (see [#4851](https://github.com/google/adk-python/issues/4851)). To workaround that issue, updated  pipeline to accurately map requests to their corresponding responses and errors using deeply nested parent-child span relationships. Previously it would miss LLM errors and requests due to that issue.
* **SQL Limit Parity:** Fixed SQL threshold constraints so they strictly inherit `num_slowest` and `num_empty_llm_responses` targets from your explicit user configuration, eliminating arbitrary hardcoded overrides.
### 🛠️ Tooling & Configuration
* **Config Explanations:** Expanded `config.json` with documented explanations for all SRE configuration thresholds and performance limits.
* **Dynamic Test Generation:** Updated test generation scripts across `my_test_app` to use dynamic environment variable placeholders instead of hardcoded BigQuery paths.