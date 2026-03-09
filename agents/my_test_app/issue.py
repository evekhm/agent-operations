#!/usr/bin/env python3
"""
A strictly simplified version of `generate_data.py`.
No files are read, no arguments are parsed; it just runs your `agent.py`
in parallel using the required 'spawn' context to prevent gRPC freezes.
"""

import asyncio
import concurrent.futures
import multiprocessing
import os
import sys

# Ensure Python can find the user's agent directory
sys.path.insert(0, "/usr/local/google/home/evekhm/projects/adk/agent-operations/agents/my_test_app")

from dotenv import load_dotenv
load_dotenv()

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
    BigQueryLoggerConfig
)
from google.genai import types

# Import YOUR agent so we don't hit authentication errors
from agent import root_agent

def create_bq_plugin(table_id_suffix: str):
    """Creates a fresh BQ plugin instance inside the worker process."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        import google.auth
        _, project_id = google.auth.default()

    config = BigQueryLoggerConfig(
        enabled=True,
        table_id=f"agent_events_{table_id_suffix}",
        batch_size=1, # Important: force flush quickly for quick runs
        shutdown_timeout=10.0
    )

    return BigQueryAgentAnalyticsPlugin(
        project_id=project_id,
        dataset_id=os.environ.get("BIG_QUERY_DATASET_ID", "logging"),
        config=config,
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "US")
    )

async def run_single_session_async(worker_id: int):
    session_service = InMemorySessionService()

    # 1. Resolve your agent
    agent = root_agent
    if hasattr(root_agent, "root_agent"):
        agent = root_agent.root_agent

    # 2. Instantiate the plugin in this thread/process
    plugins = [create_bq_plugin(table_id_suffix=f"worker_{worker_id}")]

    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name="minimal_test",
        plugins=plugins,
    )

    try:
        session = await session_service.create_session(
            user_id=f"test_user_{worker_id}",
            app_name="minimal_test",
            state={}
        )

        print(f"[Worker {worker_id}] Sending test query...")
        async for event in runner.run_async(
                new_message=types.Content(role="user", parts=[types.Part(text="Hi, this is a test!")]),
                user_id=f"test_user_{worker_id}",
                session_id=session.id
        ):
            pass # Just consume the stream

        print(f"✅ [Worker {worker_id}] Finished query.")
        return True
    except Exception as e:
        print(f"❌ [Worker {worker_id}] Error: {e}")
        return False
    finally:
        # Give BQ time to flush the event before this worker shuts down
        await asyncio.sleep(1)

def run_worker_wrapper(worker_id: int):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run_single_session_async(worker_id))

def main():
    print(f"Parent process PID: {os.getpid()}")
    num_workers = 3

    # CRITICAL: Use 'spawn' to bypass Linux gRPC fork deadlocks
    mp_context = multiprocessing.get_context('spawn')

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers, mp_context=mp_context) as executor:
        futures = {executor.submit(run_worker_wrapper, i): i for i in range(num_workers)}

        for future in concurrent.futures.as_completed(futures):
            worker_id = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"🔥 Process exception in worker {worker_id}: {e}")

if __name__ == "__main__":
    main()
