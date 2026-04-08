import asyncio
import os
import sys
from pathlib import Path

# Add project root to path to import agents
_root_dir = Path(__file__).resolve().parent.parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from agents.knowledge_supervisor.agent import root_agent, app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def main():
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="knowledge_supervisor",
        plugins=app.plugins,
    )

    session = await session_service.create_session(
        user_id="test_user_local",
        app_name="knowledge_supervisor"
    )

    queries = [
        "How many PTO days do I have left?",
        "List candidates for Software Engineer Hiring",
        "Who are you and what can you do?"
    ]

    for q in queries:
        print(f"\n=== User: {q} ===")
        try:
            async for event in runner.run_async(
                new_message=types.Content(role="user", parts=[types.Part(text=q)]),
                user_id="test_user_local",
                session_id=session.id
            ):
                print(f"Event: {event}")
        except Exception as e:
            print(f"Error running query '{q}': {e}")
        print("====================================")

if __name__ == "__main__":
    asyncio.run(main())
