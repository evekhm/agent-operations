import asyncio
import sys
import os

# Add parent directory to path to import agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import root_agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def test_local():
    print("Testing pto_agent locally (direct runner)...")
    
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="test_local"
    )
    
    session = session_service.create_session_sync(user_id="test_user", app_name="test_local")
    
    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Hi how many PTO days are left")]
    )
    
    print("Sending query: 'Hi how many PTO days are left'")
    result = runner.run(new_message=message, user_id="test_user", session_id=session.id)
    print("\n--- Response ---")
    for chunk in result:
        if hasattr(chunk, 'text'):
            print(chunk.text, end="")
        else:
            print(chunk, end="")
    print()

if __name__ == "__main__":
    asyncio.run(test_local())
