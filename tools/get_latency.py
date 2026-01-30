import asyncio
import argparse
import json
import os
import sys
import logging
from dotenv import load_dotenv

import pandas as pd

# 1. Setup path immediately so we can import agents modules
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))

# 2. Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# 3. Load Environment
load_dotenv(os.path.join(dir_path, "../.env"))

try:
    from agents.analytics_agent.agent_tools.analytics.latency import (
        analyze_latency_distribution,
        analyze_latency_performance,
        get_slowest_queries,
        analyze_latency_grouped,
        get_active_metadata
    )
    from agents.analytics_agent.config import PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID
except ImportError as e:
    logger.error(f"Failed to import analytics tools: {e}")
    sys.exit(1)

async def main():
    parser = argparse.ArgumentParser(description="Run Latency Analysis")
    parser.add_argument("--tool", choices=["all", "distribution", "performance", "slowest", "breakdown"], default="all", help="Tool to run")
    parser.add_argument("--time_range", default="24h", help="Time range (e.g. 24h, 7d)")
    parser.add_argument("--agent", help="Filter by agent name")
    parser.add_argument("--model", help="Filter by model name")
    parser.add_argument("--table_id", help="BigQuery table/view ID (e.g. llm_events_view)")
    parser.add_argument("--view_id", help="Alias for table_id")
    parser.add_argument("--limit", type=int, default=10, help="Limit for slowest queries (default: 10)")

    args = parser.parse_args()
    
    # Handle view_id alias
    if args.view_id and not args.table_id:
        args.table_id = args.view_id

    # If no table_id provided, tools default to config default (LLM_EVENTS_VIEW_ID)
    target_table = args.table_id or LLM_EVENTS_VIEW_ID
    
    tools_to_run = [args.tool]
    if args.tool == "all":
        tools_to_run = ["distribution", "performance", "breakdown", "slowest"]
        
    logger.info("Latency Analysis initialized.")
    
    results = {}
    
    if "distribution" in tools_to_run:
        logger.info("Running Latency Distribution...")
        try:
            res = await analyze_latency_distribution(
                time_range=args.time_range,
                agent_name=args.agent,
                model_name=args.model,
                view_id=target_table
            )
            print(f"\n--- Distribution ---\n{res}")
        except Exception as e:
            logger.error(f"Distribution analysis failed: {e}")

    if "performance" in tools_to_run:
        logger.info("Running Latency Performance...")
        try:
            res = await analyze_latency_performance(
                time_range=args.time_range,
                agent_name=args.agent,
                model_name=args.model,
                view_id=target_table
            )
            print(f"\n--- Performance ---\n{res}")
        except Exception as e:
            logger.error(f"Performance analysis failed: {e}")
            
    if "breakdown" in tools_to_run:
        logger.info("Running Latency Breakdown (Agent, Root Agent, Model)...")
        for group in ["agent_name", "root_agent_name", "model_name"]:
            try:
                res = await analyze_latency_grouped(
                    group_by=group,
                    time_range=args.time_range,
                    model_name=args.model,
                    view_id=target_table
                )
                print(f"\n--- Breakdown by {group} ---\n{res}")
            except Exception as e:
                logger.error(f"Breakdown analysis for {group} failed: {e}")

    if "slowest" in tools_to_run:
        logger.info("Running Slowest Queries...")
        try:
            res = await get_slowest_queries(
                time_range=args.time_range,
                limit=args.limit,
                agent_name=args.agent,
                root_agent_name=args.agent,
                model_name=args.model,
                view_id=target_table
            )
            print(f"\n--- Slowest Queries ---\n{res}")
        except Exception as e:
            logger.error(f"Slowest queries failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
