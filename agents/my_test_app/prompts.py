TEST_CASE_GENERATION_PROMPT = """
You are a test case generator. Your task is to generate {TOTAL_LINES} lines, each representing a test scenario for an AI agent system. Each line must strictly follow the format:

"$SCENARIO_TARGET|$MODEL|$CONFIG|$REGION|$QUESTION_1|...|$QUESTION_N"

**Instructions & Constraints:**

1.  **$SCENARIO_TARGET**: Randomly select one value from the following list. Distribute it so that 90% are `VALID_ALL`, 5% are `NOK_ADK_DATASTORE`, and 5% are `NOK_OBS_DATASTORE`:
    *   `VALID_ALL`: Both datastores are valid. Questions can be about anything.
    *   `NOK_ADK_DATASTORE`: Represents a failed Vertex AI ADK connection. **CRITICAL:** If you choose this, EVERY question on this line MUST be about "ADK Documentation".
    *   `NOK_OBS_DATASTORE`: Represents a failed Local PDF directory. **CRITICAL:** If you choose this, EVERY question on this line MUST be about "AI Observability".

2.  **$MODEL**: Randomly select one value from the following list, adhering to the specified probabilities:
    *   {MODEL_OPTIONS}

3.  **$CONFIG**: Randomly select one value from the following list, adhering to the specified probabilities:
    *   {CONFIG_OPTIONS}

4.  **$REGION**: 
    *   **If $MODEL starts with "gemini-3":** You MUST use "global".
    *   **Otherwise:** You MUST use "$DEFAULT_REGION".

5.  **Questions ($QUESTION_1 to $QUESTION_N):**
    *   Each line should contain between {MIN_QUESTIONS} and {MAX_QUESTIONS} questions, separated by pipes (|).
    *   If `$SCENARIO_TARGET` is `VALID_ALL`, distribute the questions across the following categories according to the target percentages:

        *   **ADK Documentation ({ADK_PCT}%):** Questions for `adk_documentation_agent` about ADK Application Structure.
            *   *Examples:* "How do I use VertexAiSearchTool in ADK?", "What is the structure of an ADK App?"

        *   **AI Observability ({OBS_PCT}%):** Questions for `ai_observability_agent` about AI Agent Observability, Tracing, and Langfuse.
            *   *Examples:* "How does Langfuse handle tracing data models in observability?", "What are the best open source observability solutions for agents?"

        *   **BigQuery Analysis ({BQ_PCT}%):** Questions for `bigquery_data_agent`.
            *   *Examples:* "What's the latest timestamp in `{TABLE_ID}`?", "List tables in dataset."

        *   **Google Search ({GOOGLE_SEARCH_PCT}%):** Questions for `google_search_agent`.
            *   *Examples:* "What is the current version of Python?", "Who is the CEO of Google?", "Latest news about Vertex AI."

        *   **Unreliable Tool ({UNRELIABLE_PCT}%):** Questions for `unreliable_tool_agent`.
            *   *Examples:* "Simulate a flaky action for 'test case 1'", "Try the unreliable tool with very_slow_topic input."

        *   **Parallel Lookups ({PARALLEL_PCT}%):** Requests for `parallel_db_lookup`.
            *   *Examples:* "Get item_1, large_record_F", "Lookup item_8, item_9"

        *   **Config Testing ({CONFIG_TEST_PCT}%):** Questions for config test agents.
            *   *Examples:* "Using config WRONG_MAX_TOKENS, calculate for 'test A'", "With WRONG_CANDIDATES, process 'test B'"

        *   **Complex/Chained ({COMPLEX_PCT}%):** Questions requiring multiple sub-agents.
            *   *Examples:* "Find the number of errors in BigQuery, if it's high, search Google for common causes."

    *   Vary the phrasing and complexity. Ensure questions are distinct within a single line and unique across all {TOTAL_LINES} lines in this batch.
    
    *   **CRITICAL: DO NOT use the provided examples verbatim.** They are provided for format inspiration only. Create entirely new, creative, and realistic questions.
    
    *   **Diversity:** Explore a wide range of topics, scenarios, and user intents within each category. Avoid repetitive patterns or themes.

Please generate {TOTAL_LINES} unique and creative lines adhering to all the above rules.

"""
