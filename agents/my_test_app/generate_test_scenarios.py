from prompts import TEST_CASE_GENERATION_PROMPT
import os
_dir_path = os.path.dirname(os.path.realpath(__file__))

def _format_weights(weights_dict):
    """Turns a python dictionary into a prompt string for Gemini, e.g `{"OK_CONFIG1": 50}` -> `'"OK_CONFIG1" (50%)'`"""
    return ", ".join([f'"{k}" ({v}%)' for k, v in weights_dict.items()])

def fill_prompt_template(
    total_lines=100,
    model_weights=None,
    config_weights=None,
    min_questions=1,
    max_questions=4,
    adk_pct=30,
    obs_pct=15, # Added obs_pct parameter
    bq_pct=10,
    google_search_pct=10,
    unreliable_pct=20,
    parallel_pct=10,
    config_test_pct=5,
    complex_pct=5,
    agent_events_table_id="{TEST_TABLE_ID}"
):
    """Fills the placeholders in the prompt template."""
    if model_weights is None:
        model_weights = {"gemini-2.5-pro": 30,
                         "gemini-2.5-flash": 30,
                         "gemini-3-pro-preview": 20,
                         "gemini-3.1-pro-preview": 20,
                         }

    if config_weights is None:
        config_weights = {
            "NORMAL": 60,
            "OVER_PROVISIONED": 10,
            "HIGH_TEMP": 16,
            "WRONG_MAX_TOKENS": 2,
            "WRONG_CANDIDATES": 2,
        }

    return TEST_CASE_GENERATION_PROMPT.format(
        TOTAL_LINES=total_lines,
        MODEL_OPTIONS=_format_weights(model_weights),
        CONFIG_OPTIONS=_format_weights(config_weights),
        MIN_QUESTIONS=min_questions,
        MAX_QUESTIONS=max_questions,
        ADK_PCT=adk_pct,
        OBS_PCT=obs_pct, # Mapped obs_pct to OBS_PCT
        BQ_PCT=bq_pct,
        GOOGLE_SEARCH_PCT=google_search_pct,
        UNRELIABLE_PCT=unreliable_pct,
        PARALLEL_PCT=parallel_pct,
        CONFIG_TEST_PCT=config_test_pct,
        COMPLEX_PCT=complex_pct,
        TABLE_ID=agent_events_table_id
    )

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Disable noisy logs
logging.getLogger("google_adk").setLevel(logging.WARNING)

async def llm_call(prompt):
    """Calls Gemini to generate test cases dynamically."""
    print("--- CALLING LLM TO GENERATE SCENARIOS ---")
    print(f"Prompt length: {len(prompt)} characters. This may take a moment...")
    
    agent = LlmAgent(
        name="test_case_generator",
        model="gemini-2.5-flash",
        instruction="You are a data generation system. You strictly follow instructions. Never output markdown, "
                    "backticks, or intro/outro text. ONLY output the raw pip-delimited data lines.",
        generate_content_config=types.GenerateContentConfig(temperature=1.0)
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, session_service=session_service, app_name="test_generator")
    session = await session_service.create_session(user_id="test_gen_user", app_name="test_generator")
    
    full_response = ""
    async for event in runner.run_async(
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        session_id=session.id,
        user_id="test_gen_user"
    ):
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                if getattr(part, "text", None):
                    full_response += part.text

    print("--- LLM GENERATION COMPLETE ---")
    
    # Clean possible markdown block
    full_response = full_response.strip()
    if full_response.startswith('```'):
        lines = full_response.split('\n')
        # Remove first block marker
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        # Remove trailing block marker
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        full_response = '\n'.join(lines).strip()
    return full_response

async def batch_generate_test_lines(total_lines_needed, kwargs):
    chunk_size = 400
    tasks = []
    
    # Create a schedule of tasks
    lines_scheduled = 0
    while lines_scheduled < total_lines_needed:
        lines_to_request = min(chunk_size, total_lines_needed - lines_scheduled)
        current_kwargs = kwargs.copy()
        current_kwargs['total_lines'] = lines_to_request
        filled_prompt = fill_prompt_template(**current_kwargs)
        # Add a subtle random seed to the prompt to encourage variety between batches
        filled_prompt += f"\n\nNote: For this specific batch, try to think of topics related to index {lines_scheduled}."
        tasks.append(llm_call(filled_prompt))
        lines_scheduled += lines_to_request
        
    print(f"Executing {len(tasks)} parallel LLM calls...")
    # Run all calls concurrently
    results = await asyncio.gather(*tasks)
    
    all_lines = []
    for llm_output in results:
        lines = [line.strip() for line in llm_output.split('\n') if line.strip() and '|' in line]
        all_lines.extend(lines)
        
    return all_lines

def generate_test_lines(output_file="test_scenario.txt", **kwargs):
    """Generates the prompt, calls the LLM, and saves the output."""
    total_lines_needed = kwargs.get('total_lines', 100)
    
    all_lines = asyncio.run(batch_generate_test_lines(total_lines_needed, kwargs))

    final_lines = all_lines[:total_lines_needed]

    with open(output_file, 'w') as f:
        for line in final_lines:
            f.write(line + '\n')

    print(f"Generated {len(final_lines)} test lines and saved to {output_file}")
    return final_lines

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Dynamically generate pipe-delimited test scenarios.")
    parser.add_argument("--output-file", type=str, default=os.path.join(_dir_path, "test_scenarios.txt"), help="Output file path.")
    parser.add_argument("--total-lines", type=int, default=15, help="Total number of test scenario lines to generate.")
    parser.add_argument("--max-questions", type=int, default=3, help="Maximum number of sub-questions per scenario.")
    parser.add_argument("--adk-pct", type=int, default=15, help="Percentage of ADK datastore knowledge questions.")
    parser.add_argument("--obs-pct", type=int, default=15, help="Percentage of Observability datastore knowledge questions.")
    parser.add_argument("--bq-pct", type=int, default=15, help="Percentage of BigQuery knowledge questions.")
    parser.add_argument("--google-search-pct", type=int, default=15, help="Percentage of Google Search questions.")
    parser.add_argument("--unreliable-pct", type=int, default=5, help="Percentage of unreliable tool questions.")
    parser.add_argument("--parallel-pct", type=int, default=10, help="Percentage of parallel execution questions.")
    parser.add_argument("--config-test-pct", type=int, default=15, help="Percentage of config testing questions.")
    parser.add_argument("--complex-pct", type=int, default=10, help="Percentage of complex/multi-step questions.")
    
    args = parser.parse_args()

    # Example usage: Customize parameters here
    generated_lines = generate_test_lines(
        output_file=args.output_file,
        total_lines=args.total_lines,
        max_questions=args.max_questions,
        adk_pct=args.adk_pct,
        obs_pct=args.obs_pct,
        bq_pct=args.bq_pct,
        google_search_pct=args.google_search_pct,
        unreliable_pct=args.unreliable_pct,
        parallel_pct=args.parallel_pct,
        config_test_pct=args.config_test_pct,
        complex_pct=args.complex_pct,
        config_weights={
            "NORMAL": 60,
            "OVER_PROVISIONED": 10,
            "HIGH_TEMP": 10,
            "WRONG_MAX_TOKENS": 10,
            "WRONG_CANDIDATES": 10,
        }
    )
    print("--- First 3 Generated Lines ---")
    for i in range(min(3, len(generated_lines))):
        print(generated_lines[i])
    print("-----------------------------")
