#!/usr/bin/env python3
"""
Stress test script that runs multiple varying instances of `adk run` logic in parallel.
Usage: python3 generate_data.py --scenarios-file test_scenarios.txt --max-workers 5

This version parses test scenarios natively, maps them to environment variables,
and runs them in parallel using ProcessPoolExecutor.
"""

import argparse
import asyncio
import concurrent.futures
import json
import logging
import multiprocessing
import os
import sys
import time
import uuid
from pathlib import Path

# Add shared library path if needed (pattern from replay_queries.py)
CURRENT_DIR = Path(__file__).resolve().parent

from dotenv import load_dotenv

load_dotenv(dotenv_path=CURRENT_DIR / "../../.env", override=False)

# We can import ADK core at top level, but NOT the agent (since it resolves env vars on import).
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.plugins import LoggingPlugin
from google.genai import types

# Import the agent definitions safely as a standard module

# Disable noisy logs
logging.getLogger("google_adk").setLevel(logging.WARNING)

async def run_single_session_async(user_id: str, app_name: str, queries: list[str], state: dict):
    """Async function to run a single user session."""
    session_service = InMemorySessionService()

    # Import the agent definitions safely as a standard module
    import agent

    # Instantiate the exact Agent graph for this user's injected OS environment
    factory = agent.AgentFactory(os.environ)
    resolved_agent = factory.create_root_agent()

    # Create fresh plugins for this thread's loop using the factory
    plugins = [factory.create_bq_plugin(), LoggingPlugin()]

    runner = Runner(
        agent=resolved_agent,
        session_service=session_service,
        app_name=app_name,
        plugins=plugins,
    )

    start_time = time.time()
    try:
        session = await session_service.create_session(
            user_id=user_id,
            app_name=app_name,
            state=state.copy()
        )

        for q in queries:
            max_retries = 3
            base_delay = 2
            
            for attempt in range(max_retries):
                try:
                    # Send query
                    async for event in runner.run_async(
                            new_message=types.Content(role="user", parts=[types.Part(text=q)]),
                            user_id=user_id,
                            session_id=session.id
                    ):
                        pass # Consume stream
                    break # Success, break out of retry loop
                except Exception as e:
                    delay = base_delay * (2 ** attempt)
                    if attempt < max_retries - 1:
                        print(f"⚠️ [{user_id}] Query failed (attempt {attempt + 1}/{max_retries}): '{q}' -> {e}. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        print(f"🔥 [{user_id}] Query failed permanently after {max_retries} attempts: '{q}' -> {e}")
                        raise e # Re-raise to be caught by the outer exception handler

        duration = time.time() - start_time
        return {"success": True, "duration": duration, "user_id": user_id}

    except Exception as e:
        duration = time.time() - start_time
        return {"success": False, "duration": duration, "user_id": user_id, "error": str(e)}

def run_single_user_wrapper(args):
    """Wrapper to run async code in a new event loop for thread safety."""
    user_id, env_vars, queries, state = args
    
    # 1. Apply environment variables for this scenario
    for k, v in env_vars.items():
        if v is not None:
            os.environ[k] = str(v)
            
    # 2. Set event loop policy if needed
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return asyncio.run(run_single_session_async(user_id, "stress_test_app", queries, state))

def parse_scenarios(scenarios_file: str, valid_datastore: str, valid_web_datastore: str):
    """Parses test_scenarios.txt into a list of workload parameters."""
    with open(scenarios_file, 'r') as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        
    work_items = []
    default_region = "us-central1"
    
    for i, line in enumerate(lines):
        # Strip quotes
        line = line.strip('"')
        fields = line.split('|')
        
        if len(fields) < 5:
            print(f"⚠️ Skipping invalid scenario (not enough fields): {line}")
            continue
            
        scenario_target = fields[0]
        model = fields[1]
        config = fields[2]
        current_region = fields[3]
        
        current_region = current_region.replace("$DEFAULT_REGION", default_region)
        if model.startswith("gemini-3"):
            current_region = "global"
        elif current_region == default_region:
            current_region = "us-central1"
            
        # Determine environment variables
        env_vars = {
            "TEST_AGENT_MODEL_ID": model,
            "AGENT_CONFIG": config,
            "GCP_LOCATION": current_region,
            "TEST_AGENT_LOCATION": current_region,
            "PYTHONWARNINGS": "ignore"
        }
        
        if scenario_target == "NOK_ADK_DATASTORE":
            env_vars["TEST_DATASTORE_ID"] = "invalid-adk-ds-123"
            env_vars["TEST_WEB_DATASTORE_ID"] = valid_web_datastore
        elif scenario_target == "NOK_OBS_DATASTORE":
            env_vars["TEST_DATASTORE_ID"] = valid_datastore
            env_vars["TEST_WEB_DATASTORE_ID"] = "invalid-obs-ds"
        else:
            env_vars["TEST_DATASTORE_ID"] = valid_datastore
            env_vars["TEST_WEB_DATASTORE_ID"] = valid_web_datastore
            
        # Parse queries or replay file
        queries = []
        state = {}
        if fields[4].endswith(".json"):
            replay_file = Path(fields[4])
            if not replay_file.is_absolute():
                replay_file = CURRENT_DIR / replay_file
            if replay_file.exists():
                try:
                    with open(replay_file, 'r', encoding='utf-8') as rf:
                        replay_data = json.load(rf)
                        queries = replay_data.get("queries", [])
                        state = replay_data.get("state", {})
                except Exception as e:
                    print(f"Error reading replay file {replay_file}: {e}")
        else:
            queries = fields[4:]
            
        if not queries:
            print(f"Skipping scenario, no replay file or questions: {line}")
            continue
            
        user_id = f"{scenario_target}_{model}_{i}_{uuid.uuid4().hex[:8]}"
        user_id = user_id.replace("-", "_").replace(".", "_") # Sanitize user_id
        work_items.append((user_id, env_vars, queries, state))
        
    return work_items

def main():
    parser = argparse.ArgumentParser(description="Run parallel load test for ADK agent across multiple scenarios.")
    parser.add_argument("--max-workers", type=int, default=5, help="Number of concurrent users/processes")
    parser.add_argument("--scenarios-file", type=str, default="test_scenarios.txt", help="Path to test_scenarios.txt file")
    
    # Optional legacy fallback or single user overrides
    parser.add_argument("users", type=int, nargs="?", default=None, help="Legacy users argument (ignored if scenarios-file used)")
    parser.add_argument("--replay-file", type=str, default=None, help="Legacy single replay test (overrides scenarios if provided)")
    args = parser.parse_args()

    max_workers = args.max_workers
    if args.users is not None and args.users > 0:
        max_workers = args.users
        
    # We must resolve VALID_DATASTORE and VALID_WEB_DATASTORE similar to bash
    valid_datastore = os.environ.get("TEST_DATASTORE_ID")
    valid_web_datastore = os.environ.get("TEST_WEB_DATASTORE_ID")

    work_items = []
    
    if args.replay_file:
        # Legacy single replay behavior but duplicated max_workers times
        replay_file = Path(args.replay_file)
        if not replay_file.is_absolute():
            if not replay_file.exists() and (CURRENT_DIR / replay_file).exists():
                replay_file = CURRENT_DIR / replay_file
        with open(replay_file, 'r', encoding='utf-8') as f:
            replay_data = json.load(f)
            queries = replay_data.get("queries", [])
            state = replay_data.get("state", {})
            
        env_vars = {
            "DATASTORE_ID": valid_datastore,
            "WEB_DATASTORE_ID": valid_web_datastore,
        }
        for i in range(max_workers):
            work_items.append((f"load_test_user_{i}_{uuid.uuid4().hex[:8]}", env_vars, queries, state))
    else:
        scenarios_file = Path(args.scenarios_file)
        if not scenarios_file.is_absolute():
            if not scenarios_file.exists() and (CURRENT_DIR / scenarios_file).exists():
                scenarios_file = CURRENT_DIR / scenarios_file
            
        if not scenarios_file.exists():
            print(f"Error: Scenarios file not found at {scenarios_file} (or relative to {CURRENT_DIR})")
            sys.exit(1)
            
        work_items = parse_scenarios(scenarios_file, valid_datastore, valid_web_datastore)

    print(f"Starting load test with {max_workers} concurrent processes (Processing {len(work_items)} total workloads)...")
    print(f"Target Agent: {CURRENT_DIR}")
    print("-" * 50)

    start_time = time.time()
    results = []

    # Use ProcessPoolExecutor with 'spawn' context to avoid gRPC fork issues
    mp_context = multiprocessing.get_context('spawn')
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_context) as executor:
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
    print(f"Successful Sessions: {success_count}/{len(work_items)}")
    print(f"Failed Sessions: {fail_count}/{len(work_items)}")
    print(f"Average Session Duration: {avg_duration:.2f}s")

    if fail_count > 0:
        print("\nErrors:")
        for r in results:
            if not r["success"]:
                print(f"[{r['user_id']}] {r.get('error')}")

if __name__ == "__main__":
    main()
