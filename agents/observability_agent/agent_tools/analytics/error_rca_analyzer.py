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
1. "rca_analysis": A dense, highly technical 1-2 sentence Root Cause Analysis explaining exactly WHY this error occurred and the impact.
2. "category": A 1-2 word category for this error (e.g., 'RATE_LIMIT', 'CONFIGURATION_ERROR', 'NETWORK_TIMEOUT').

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
                "rca_analysis": data.get("rca_analysis", "Extracted text but missing rca_analysis key."),
                "category": data.get("category", "OTHER_ERROR")
            }
        except Exception as e:
            logger.error(f"Failed to generate RCA for {df_name} row {idx}: {e}")
            return {
                "rca_analysis": "RCA Generation failed.",
                "category": "OTHER_ERROR"
            }

def _categorize_error_message(error_message: str) -> str:
    """Categorizes the error message based on the exact same logic as BigQuery ANALYZE_ERROR_CATEGORIES_QUERY."""
    if not isinstance(error_message, str):
        return 'OTHER_ERROR'
    msg_lower = error_message.lower()
    if 'quota' in msg_lower or 'rate limit' in msg_lower:
        return 'QUOTA_EXCEEDED'
    elif 'timeout' in msg_lower or 'timed out' in msg_lower or 'deadline' in msg_lower:
        return 'TIMEOUT'
    elif 'permission' in msg_lower or 'unauthorized' in msg_lower or '403' in msg_lower:
        return 'PERMISSION_DENIED'
    elif 'model' in msg_lower or 'generation' in msg_lower or '500' in msg_lower:
        return 'MODEL_ERROR'
    elif 'not found' in msg_lower and 'tool' in msg_lower:
        return 'TOOL_NOT_FOUND'
    elif 'tool' in msg_lower or 'function' in msg_lower:
        return 'TOOL_ERROR'
    elif 'parse' in msg_lower or 'json' in msg_lower:
        return 'PARSING_ERROR'
    else:
        return 'OTHER_ERROR'

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
                    tasks.append(asyncio.sleep(0, result={"rca_analysis": "RCA Generation failed (preparation error).", "category": "OTHER_ERROR"}))
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
                    rca_list.append({"rca_analysis": "Not Analyzed (Out of Top N)", "category": "OTHER_ERROR"})
                
            # Inject into DataFrame
            # Process categories leveraging a hybrid approach
            categories = []
            for i, (idx, row) in enumerate(df.iterrows()):
                try:
                    det_cat = _categorize_error_message(row.get('error_message', ''))
                except Exception:
                    det_cat = 'OTHER_ERROR'
                
                if det_cat == 'OTHER_ERROR' and i < len(rca_list):
                    llm_cat = rca_list[i].get('category', 'OTHER_ERROR')
                    if llm_cat and isinstance(llm_cat, str) and llm_cat != 'OTHER_ERROR':
                        cat = llm_cat.strip().replace(' ', '_').upper()
                    else:
                        cat = 'OTHER_ERROR'
                else:
                    cat = det_cat
                categories.append(cat)
                
            df['category'] = categories
            df['rca_analysis'] = [item.get('rca_analysis', 'Unknown') for item in rca_list]
            data[df_name] = df
            
            # Reconcile the static Error Categorization Summary with the hybrid LLM assignments
            if 'error_summary' in df.attrs and "categories" in df.attrs['error_summary']:
                cat_list = df.attrs['error_summary']["categories"]
                
                # Count how many of the top N samples were re-categorized from OTHER_ERROR
                replacements = {}
                other_error_reductions = 0
                for i, row in df.iterrows():
                    det_cat = 'OTHER_ERROR'
                    try:
                        det_cat = _categorize_error_message(row.get('error_message', ''))
                    except Exception:
                        pass
                        
                    final_cat = row.get('category', 'OTHER_ERROR')
                    if det_cat == 'OTHER_ERROR' and final_cat != 'OTHER_ERROR':
                        replacements[final_cat] = replacements.get(final_cat, 0) + 1
                        other_error_reductions += 1
                        
                if other_error_reductions > 0:
                    # Decrement OTHER_ERROR from the overview
                    for c_dict in cat_list:
                        if c_dict.get("category") == "OTHER_ERROR":
                            c_dict["total_count"] = max(0, c_dict["total_count"] - other_error_reductions)
                            break
                            
                    # Inject the newly discovered LLM categories into the overview
                    for new_cat, count in replacements.items():
                        found = False
                        for c_dict in cat_list:
                            if c_dict.get("category") == new_cat:
                                c_dict["total_count"] += count
                                found = True
                                break
                        if not found:
                            cat_list.append({"category": new_cat, "total_count": count})
                            
                    # Sort the list descending by count
                    cat_list.sort(key=lambda x: x.get("total_count", 0), reverse=True)
                    # Filter out 0 count items
                    df.attrs['error_summary']["categories"] = [c for c in cat_list if c.get("total_count", 0) > 0]


            
    logger.info("✅ Inline RCA analysis complete.")
    return data
