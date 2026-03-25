import os
import sys
import google.auth
from dotenv import load_dotenv

# Add project root and agents/ca_agent to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Load .env
load_dotenv(override=True)

# Import the agent
from agents.ca_agent.agent import ca_agent, ca_conversation, data_chat_client, geminidataanalytics, PROJECT_ID, CA_LOCATION

print("CA Agent initialized.")

def ask_question(question):
    print(f"\nAsking: {question}")
    u_msg = geminidataanalytics.UserMessage(text=question)
    m = geminidataanalytics.Message(user_message=u_msg)

    request = geminidataanalytics.ChatRequest(
        parent=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}",
        conversation_reference=geminidataanalytics.ConversationReference(
            conversation=ca_conversation.name,
            data_agent_context=geminidataanalytics.DataAgentContext(
                data_agent=ca_agent.name
            )
        ),
        messages=[m],
    )

    try:
        resp = data_chat_client.chat(request=request)
        print("\n--- Response ---")
        for r in resp:
            if hasattr(r, 'system_message') and r.system_message:
                m = r.system_message
                if hasattr(m, 'text') and m.text:
                    if hasattr(m.text, 'parts'):
                         print("\n".join(m.text.parts))
                    else:
                         print(m.text)
                elif hasattr(m, 'data') and m.data:
                    # Print generated SQL or results if available
                    if hasattr(m.data, 'generated_sql') and m.data.generated_sql:
                        print(f"Generated SQL: {m.data.generated_sql}")
                    elif hasattr(m.data, 'result') and m.data.result:
                        print(f"Result: {m.data.result}")
                    else:
                        print(f"Data: {m.data}")
                else:
                    print(r)
    except Exception as e:
        print(f"Error: {e}")

# Run questions
ask_question("What is the total number of sessions?")
ask_question("What is the average latency for the knowledge_qa_supervisor agent?")
ask_question("Show me the error rate for each agent.")
ask_question("Show me the slowest tool executions.")
