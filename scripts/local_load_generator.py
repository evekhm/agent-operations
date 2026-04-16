"""
Local load generator that sends questions to a locally-running ADK API server
instead of the deployed Reasoning Engine.

Usage:
    python scripts/local_load_generator.py --supervisor-url http://localhost:8000 --app-name knowledge_supervisor
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import time
import uuid
import logging

import google.auth
from google.genai import Client
from google.genai import types
from pydantic import BaseModel

# Reuse the question generation logic from the load test agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.load_test_agent.load_generator import (
    generate_questions,
    TOPIC_CAPABILITIES,
    QuestionList,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("local_load_generator")

shutdown_requested = False

def handle_signal(signum, frame):
    global shutdown_requested
    logger.info("Received signal — finishing current batch and shutting down...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


async def send_query_to_local_server(
    session, supervisor_url: str, app_name: str, query: str, query_num: int
):
    """Send a single query to the local ADK API server via /run endpoint."""
    import aiohttp

    user_id = f"load_test_user_{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())

    url = f"{supervisor_url}/run"
    payload = {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": query}],
        },
        "streaming": False,
    }

    start_time = time.time()
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            latency = time.time() - start_time
            if resp.status == 200:
                data = await resp.json()
                # Extract the agent's final text response
                answer = ""
                if isinstance(data, list):
                    for event in data:
                        content = event.get("content", {})
                        parts = content.get("parts", [])
                        for part in parts:
                            if "text" in part and event.get("author") != "user":
                                answer = part["text"]
                elif isinstance(data, dict):
                    content = data.get("content", {})
                    parts = content.get("parts", [])
                    for part in parts:
                        if "text" in part:
                            answer = part["text"]

                answer_preview = (answer[:150] + "...") if len(answer) > 150 else answer
                logger.info(f"[Query {query_num}] {latency:.1f}s | {answer_preview}")
            else:
                text = await resp.text()
                logger.warning(f"[Query {query_num}] {latency:.1f}s | HTTP {resp.status}: {text[:200]}")
    except asyncio.TimeoutError:
        latency = time.time() - start_time
        logger.warning(f"[Query {query_num}] {latency:.1f}s | TIMEOUT")
    except Exception as e:
        latency = time.time() - start_time
        logger.error(f"[Query {query_num}] {latency:.1f}s | ERROR: {e}")


async def main():
    global shutdown_requested

    parser = argparse.ArgumentParser()
    parser.add_argument("--supervisor-url", default="http://localhost:8000")
    parser.add_argument("--app-name", default="knowledge_supervisor")
    args = parser.parse_args()

    topics_config_str = os.getenv("TOPICS_CONFIG",
        "pto and sick leave balances:3,vacation planning and working days:2,"
        "company policies and HR procedures:2,general knowledge and technology:2"
    )
    concurrency = int(os.getenv("CONCURRENCY", "3"))
    duration_minutes = float(os.getenv("DURATION_MINUTES", "5"))

    logger.info("=== Local Load Test ===")
    logger.info(f"Target:     {args.supervisor_url}")
    logger.info(f"App:        {args.app_name}")
    logger.info(f"Topics:     {topics_config_str}")
    logger.info(f"Concurrency: {concurrency}")
    logger.info(f"Duration:   {duration_minutes} min")
    logger.info("=======================")

    # Parse topics
    topics_config = {}
    for item in topics_config_str.split(","):
        if ":" in item:
            topic, count = item.rsplit(":", 1)
            topics_config[topic.strip()] = int(count.strip())

    # Generate questions
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.getenv("REGION", "us-central1"))
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

    genai_client = Client(project=project_id, location=os.getenv("REGION", "us-central1"))

    all_questions = []
    for topic, count in topics_config.items():
        questions = await generate_questions(genai_client, topic, count)
        all_questions.extend(questions)

    logger.info(f"\nGenerated {len(all_questions)} questions:")
    for i, q in enumerate(all_questions, 1):
        logger.info(f"  {i}. {q}")
    logger.info("")

    # Run load test
    import aiohttp
    sem = asyncio.Semaphore(concurrency)
    start_time = time.time()
    max_duration = duration_minutes * 60
    query_count = 0
    batch_num = 0

    async with aiohttp.ClientSession() as session:
        while time.time() - start_time < max_duration and not shutdown_requested:
            batch_num += 1
            logger.info(f"--- Batch {batch_num} ({len(all_questions)} queries) ---")

            async def run_query(q):
                nonlocal query_count
                async with sem:
                    query_count += 1
                    await send_query_to_local_server(
                        session, args.supervisor_url, args.app_name, q, query_count
                    )

            tasks = [run_query(q) for q in all_questions]
            await asyncio.gather(*tasks)

            if shutdown_requested or time.time() - start_time >= max_duration:
                break

    elapsed = time.time() - start_time
    logger.info(f"\nDone. {query_count} queries in {elapsed/60:.1f} min")


if __name__ == "__main__":
    asyncio.run(main())
