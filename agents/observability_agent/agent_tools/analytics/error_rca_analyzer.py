import os
import json
import logging
import asyncio
import pandas as pd
from typing import Dict, Any
from google import genai

from agents.observability_agent.config import RCA_MAX_CONCURRENT_REQUESTS

logger = logging.getLogger(__name__)

RCA_PROMPT = """
You are an expert Observability Engineer. You are analyzing a failed trace/span in our autonomous agent architecture.

Given the telemetry data below, output a strictly valid JSON object with the following keys:
1. "category": A concise 2-4 word classification of the error (e.g., "Timeout / Pending", "Rate Limit", "Configuration Error", "Tool Execution Error", "Parsing Error", "Safety Block", etc.).
2. "rca_analysis": A dense, highly technical 1-2 sentence Root Cause Analysis explaining exactly WHY this error occurred and the impact.

Telemetry Event Data:
{error_data}

Return ONLY valid JSON. No markdown blocks, no prefixes.
"""

async def _get_rca(client, df_name, idx, row_dict, prompt, semaphore):
    async with semaphore:
        try:
            response = await client.aio.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
            )
            text = response.text.strip()
            # Remove markdown blocks if agent hallucinated them
            if text.startswith("```json"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            elif text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                
            data = json.loads(text)
            return {
                "category": data.get("category", "Unknown Priority"),
                "rca_analysis": data.get("rca_analysis", "Extracted text but missing rca_analysis key.")
            }
        except Exception as e:
            logger.error(f"Failed to generate RCA for {df_name} row {idx}: {e}")
            return {
                "category": "Generation Failed",
                "rca_analysis": "RCA Generation failed."
            }

async def perform_inline_rca(data: Dict[str, Any], limit: int = 3) -> Dict[str, Any]:
    """
    Iterates through the error DataFrames in the data payload, requests an AI-generated
    RCA for the top N records concurrently, and appends an 'rca_analysis' column back into the DataFrame.
    """
    logger.info("🤖 Starting Inline Root Cause Analysis (RCA) concurrently on error datasets...")
    
    try:
        client = genai.Client()
    except Exception as e:
        logger.warning(f"Failed to initialize GenAI client for RCA: {e}. Skipping RCA phase.")
        return data

    error_dfs = [
        'root_errors',
        'agent_errors',
        'llm_errors',
        'tool_errors',
        'root_bottlenecks',
        'agent_bottlenecks',
        'llm_bottlenecks',
        'tool_bottlenecks'
    ]
    # Grab concurrency limit from environment variables, throttle to max 5 concurrent LLM calls by default to prevent 429 / Deadline errors
    try:
        max_concurrent_requests = int(RCA_MAX_CONCURRENT_REQUESTS)
    except ValueError:
        max_concurrent_requests = 5
        logger.warning("Invalid integer in RCA_MAX_CONCURRENT_REQUESTS. Defaulting to 5.")
        
    sem = asyncio.Semaphore(max_concurrent_requests)
    tasks = []
    task_mapping = []
    
    for df_name in error_dfs:
        df = data.get(df_name)
        if df is not None and not df.empty and isinstance(df, pd.DataFrame):
            # Check if this df is actually just a single row containing an error message 
            # (e.g. from get_agent_requests returning {"message": "No data found..."})
            if len(df.columns) == 1 and df.columns[0] in ['error', 'message']:
                continue
                
            logger.info(f"   [DEBUG] DF {df_name} shape: {df.shape}, cols: {df.columns.tolist()}, data: {df.head(1).to_dict('records')}")
            # Drop rows where all elements are missing, to prevent generating RCAs for completely empty/null records
            df = df.dropna(how='all')
            if df.empty:
                continue

            actual_limit = min(limit, len(df))
            logger.info(f"   Queuing {actual_limit} traces in {df_name} for concurrent analysis...")
            
            for idx, row in df.head(actual_limit).iterrows():
                try:
                    # Convert row to dict, dropping NaNs for a cleaner prompt
                    row_dict = row.dropna().to_dict()
                    
                    # Optional: drop columns that don't help RCA to save tokens
                    for col in ['session_id', 'timestamp']:
                        row_dict.pop(col, None)
                        
                    prompt = RCA_PROMPT.format(error_data=json.dumps(row_dict, indent=2, default=str))
                    tasks.append(_get_rca(client, df_name, idx, row_dict, prompt, sem))
                    task_mapping.append(df_name)
                except Exception as e:
                    logger.warning(f"   Failed to prepare RCA prompt for row {idx} in {df_name}: {e}")
                    tasks.append(asyncio.sleep(0, result={"category": "Preparation Error", "rca_analysis": "RCA Generation failed (preparation error)."}))
                    task_mapping.append(df_name)

    if tasks:
        logger.info(f"   Executing {len(tasks)} RCA generation tasks concurrently across all datasets...")
        results = await asyncio.gather(*tasks)
    else:
        results = []

    # Map the flattened results back to their respective dataframes
    results_by_df = {name: [] for name in error_dfs}
    for idx, res in enumerate(results):
        df_name = task_mapping[idx]
        results_by_df[df_name].append(res)

    for df_name in error_dfs:
        df = data.get(df_name)
        if df is not None and not df.empty and isinstance(df, pd.DataFrame):
            rca_list = results_by_df[df_name]
            
            # Pad the rest of the dataframe if there are rows beyond the limit
            if len(df) > limit:
                for _ in range(len(df) - limit):
                    rca_list.append({"category": "Not Analyzed", "rca_analysis": "Not Analyzed (Out of Top N)"})
                
            # Inject into DataFrame
            df['category'] = [item.get('category', 'Unknown') for item in rca_list]
            df['rca_analysis'] = [item.get('rca_analysis', 'Unknown') for item in rca_list]
            data[df_name] = df
            
    logger.info("✅ Inline RCA analysis complete.")
    return data
