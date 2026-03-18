# Release Notes

## v0.0.4  (Bug Fixes & Observability Hardening)
### 📊 Report Generation & Visualizations
* **Empty LLM Responses Analysis:** Enhanced "Empty LLM Responses".
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