#!/usr/bin/env python3
"""
Self-contained script to REPRODUCE the 'TimeoutError()' issue exactly 
as it happens in generate_data.py.

HOW IT HAPPENS:
1. We import `from agent import root_agent` at the top level.
2. This top-level import initializes some Google Cloud / gRPC objects inside the parent process.
3. We use `ProcessPoolExecutor` (which defaults to 'fork' on Linux).
4. The child processes inherit a corrupted gRPC state.
5. Even though the BigQuery plugin is created *inside* the worker, its background
   Write API gRPC channel gets stuck forever because of the fork corruption.
6. After 30 seconds, `asyncio.wait_for` raises `TimeoutError()`.
"""

import asyncio
import concurrent.futures
import os
import sys
import logging

# Ensure we see the ADK warnings
logging.basicConfig(level=logging.WARNING)

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin, 
    BigQueryLoggerConfig
)
from google.genai import types

# 🚨 THE TRIGGER: 
# Importing the agent at the top level initializes gRPC/Cloud objects in the parent process.
# When Linux then `fork()`s for the ProcessPoolExecutor, the gRPC state in the child is corrupted!
from agent import root_agent

def create_bq_plugin(table_id_suffix: str):
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        import google.auth
        _, project_id = google.auth.default()

    config = BigQueryLoggerConfig(
        enabled=True,
        table_id=f"agent_events_{table_id_suffix}",
        batch_size=1, 
        shutdown_timeout=10.0
    )
    
    return BigQueryAgentAnalyticsPlugin(
        project_id=project_id,
        dataset_id=os.environ.get("BIG_QUERY_DATASET_ID", "logging"),
        config=config,
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    )

async def run_single_session_async(worker_id: int):
    session_service = InMemorySessionService()
    
    agent = root_agent
    if hasattr(root_agent, "root_agent"):
        agent = root_agent.root_agent
        
    plugins = [create_bq_plugin(table_id_suffix="timeout_reproduction")]
    
    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name="repro_timeout",
        plugins=plugins,
    )

    try:
        session = await session_service.create_session(
            user_id=f"test_user_{worker_id}",
            app_name="repro_timeout",
            state={}
        )
        
        print(f"[Worker {worker_id}] Sending test query. The BQ plugin will now hang and eventually throw TimeoutError...")
        
        # This will complete on the LLM side, but the BQ plugin's background task
        # will get completely stuck trying to write to BigQuery.
        async for event in runner.run_async(
            new_message=types.Content(role="user", parts=[types.Part(text="Hello, just say hi.")]),
            user_id=f"test_user_{worker_id}",
            session_id=session.id
        ):
             pass
            
        print(f"✅ [Worker {worker_id}] LLM finished. Shutting down, watch the BQ plugin fail...")
        return True
    except Exception as e:
        print(f"❌ [Worker {worker_id}] LLM Error: {e}")
        return False
    finally:
        # We wait to allow the 30-second `TimeoutError` in the BQ background task to fire and print to the console
        await asyncio.sleep(35) 

def run_worker_wrapper(worker_id: int):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run_single_session_async(worker_id))

def main():
    print(f"Parent process PID: {os.getpid()}")
    num_workers = 1 
    
    # 🚨 THE TRIGGER (Part 2):
    # Notice we are intentionally NOT using `mp_context=multiprocessing.get_context('spawn')`.
    # We are using the default Linux 'fork', which copies the poisoned parent memory space.
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(run_worker_wrapper, i): i for i in range(num_workers)}
        
        for future in concurrent.futures.as_completed(futures):
            worker_id = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"🔥 Process exception in worker {worker_id}: {e}")

if __name__ == "__main__":
    main()
