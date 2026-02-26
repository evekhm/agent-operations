#!/usr/bin/env python3
"""
Stress test script that runs multiple instances of `adk run` logic in parallel.
Usage: python3 test_suit.py [num_concurrent_users]

This version accesses the ADK Runner API directly to ensure unique user_ids per session.
It also instantiates plugins per-thread to avoid event loop binding issues.
"""

import asyncio
import argparse
import concurrent.futures
import multiprocessing
import time
import sys
import json
import logging
import os
from pathlib import Path

# Add shared library path if needed (pattern from replay_queries.py)
CURRENT_DIR = Path(__file__).resolve().parent

from dotenv import load_dotenv

load_dotenv()

# Import ADK components
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.genai import types
from agent import root_agent

# Disable noisy logs
logging.getLogger("google_adk").setLevel(logging.WARNING)

def create_per_thread_plugins():
    """Creates fresh plugin instances for the current thread/event loop."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        # Fallback if not set (should be set by load_dotenv or agent import)
        import google.auth
        _, project_id = google.auth.default()

    dataset_id = os.environ.get("BIG_QUERY_DATASET_ID", "logging")
    table_id = os.environ.get("TABLE_ID", "agent_events_v4")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "US")

    bq_config = BigQueryLoggerConfig(
        enabled=True,
        max_content_length=500 * 1024,
        batch_size=1,
        shutdown_timeout=10.0
    )
    
    bq_plugin = BigQueryAgentAnalyticsPlugin(
        project_id=project_id,
        dataset_id=dataset_id,
        table_id=table_id,
        config=bq_config,
        location=location
    )
    
    return [bq_plugin, LoggingPlugin()]

async def run_single_session_async(user_id: str, app_name: str, queries: list[str], state: dict):
    """Async function to run a single user session."""
    session_service = InMemorySessionService()
    
    # Resolve the agent
    agent = root_agent
    if hasattr(root_agent, "root_agent"):
        agent = root_agent.root_agent
        
    # Create fresh plugins for this thread's loop
    plugins = create_per_thread_plugins()
    
    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name=app_name,
        plugins=plugins,
    )

    start_time = time.time()
    try:
        # Create session with unique user_id
        session = await session_service.create_session(
            user_id=user_id,
            app_name=app_name,
            state=state.copy()
        )
        
        for q in queries:
            try:
                # Send query
                async for event in runner.run_async(
                    new_message=types.Content(role="user", parts=[types.Part(text=q)]),
                    user_id=user_id,
                    session_id=session.id
                ):
                    pass # Consume stream
            except Exception as e:
                # Log error but continue execution of next queries
                print(f"⚠️ [{user_id}] Query failed: '{q}' -> {e}")
                # Optional: Add small delay after error
                await asyncio.sleep(0.5)

        duration = time.time() - start_time
        return {"success": True, "duration": duration, "user_id": user_id}

    except Exception as e:
        duration = time.time() - start_time
        return {"success": False, "duration": duration, "user_id": user_id, "error": str(e)}
    finally:
        # Cleanup runner (and plugins) if necessary
        # runner doesn't have explicit close, but plugins might need cleanup if they have background tasks
        pass

def run_single_user_wrapper(args):
    """Wrapper to run async code in a new event loop for thread safety."""
    user_id, queries, state = args
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    return asyncio.run(run_single_session_async(user_id, "stress_test_app", queries, state))

def main():
    parser = argparse.ArgumentParser(description="Run parallel load test for ADK agent.")
    parser.add_argument("users", type=int, nargs="?", default=5, help="Number of concurrent users")
    parser.add_argument("--replay-file", type=str, default=None, help="Path to replay JSON file")
    args = parser.parse_args()

    # Load replay config
    if args.replay_file:
         replay_file = Path(args.replay_file)
    else:
         replay_file = CURRENT_DIR / "replay_test.json"
    if not replay_file.exists():
        print(f"Error: Replay file not found at {replay_file}")
        sys.exit(1)
        
    try:
        with open(replay_file, 'r', encoding='utf-8') as f:
            replay_data = json.load(f)
            queries = replay_data.get("queries", [])
            state = replay_data.get("state", {})
    except Exception as e:
        print(f"Error reading replay file: {e}")
        sys.exit(1)

    print(f"Starting load test with {args.users} concurrent users...")
    print(f"Target Agent: {CURRENT_DIR}")
    print(f"Replay File: {replay_file}")
    print(f"Queries per user: {len(queries)}")
    print("-" * 50)

    start_time = time.time()
    results = []
    
    # Prepare arguments for each user
    work_items = [
        (f"load_test_user_{i}", queries, state) 
        for i in range(args.users)
    ]

    # Use ProcessPoolExecutor with 'spawn' context to avoid gRPC fork issues
    # This avoids 'Lock bound to different event loop' and gRPC channel inheritance issues.
    mp_context = multiprocessing.get_context('spawn')
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.users, mp_context=mp_context) as executor:
        # Submit all tasks
        futures = {executor.submit(run_single_user_wrapper, item): item[0] for item in work_items}
        
        for future in concurrent.futures.as_completed(futures):
            user_id = futures[future]
            try:
                res = future.result()
                results.append(res)
                status = "✅" if res["success"] else "❌"
                print(f"{status} [{user_id}] Finished in {res['duration']:.2f}s")
            except Exception as exc:
                print(f"🔥 [{user_id}] Process exception: {exc}")
                results.append({"success": False, "user_id": user_id, "duration": 0, "error": str(exc)})

    total_duration = time.time() - start_time
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    avg_duration = sum(r["duration"] for r in results) / len(results) if results else 0

    print("-" * 50)
    print(f"Results Summary:")
    print(f"Total Wall Time: {total_duration:.2f}s")
    print(f"Successful Sessions: {success_count}/{args.users}")
    print(f"Failed Sessions: {fail_count}/{args.users}")
    print(f"Average Session Duration: {avg_duration:.2f}s")
    
    if fail_count > 0:
        print("\nErrors:")
        for r in results:
            if not r["success"]:
                print(f"[{r['user_id']}] {r.get('error')}")

if __name__ == "__main__":
    main()
