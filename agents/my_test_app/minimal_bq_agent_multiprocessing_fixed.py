#!/usr/bin/env python3
"""
Self-contained script demonstrating the FIX for the 'TimeoutError()' issue.

THE FIX:
We import `multiprocessing` and explicitly set `mp_context=multiprocessing.get_context('spawn')`
for the `ProcessPoolExecutor`. This forces Linux to start a brand-new Python interpreter
for each worker instead of `fork`ing. The new worker process cleanly initializes its own 
gRPC connections inside the `run_single_session_async` function, completely avoiding 
the corrupted state from the parent. 
"""

import asyncio
import concurrent.futures
import os
import sys
import logging
import multiprocessing

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

# We still import the agent at the top level, which initializes gRPC/Cloud objects in the parent.
# But because we use `spawn` below, this parent memory space is NOT copied to the children!
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
        
    plugins = [create_bq_plugin(table_id_suffix="timeout_resolved")]
    
    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name="repro_timeout_fixed",
        plugins=plugins,
    )

    try:
        session = await session_service.create_session(
            user_id=f"test_user_{worker_id}",
            app_name="repro_timeout_fixed",
            state={}
        )
        
        print(f"[Worker {worker_id}] Sending test query. The BQ plugin will easily process this because 'spawn' fixed the gRPC channel...")
        
        async for event in runner.run_async(
            new_message=types.Content(role="user", parts=[types.Part(text="Hello, just say hi.")]),
            user_id=f"test_user_{worker_id}",
            session_id=session.id
        ):
             pass
            
        print(f"✅ [Worker {worker_id}] LLM finished. Shutting down, the BQ plugin will exit cleanly without a TimeoutError!")
        return True
    except Exception as e:
        print(f"❌ [Worker {worker_id}] LLM Error: {e}")
        return False
    finally:
        # Give it a tiny bit of time to flush
        await asyncio.sleep(2) 

def run_worker_wrapper(worker_id: int):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run_single_session_async(worker_id))

def main():
    print(f"Parent process PID: {os.getpid()}")
    num_workers = 1 
    
    # ✅ THE FIX:
    # Use mp_context=multiprocessing.get_context('spawn')
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
