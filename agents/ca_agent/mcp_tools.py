import json

import requests
from google.adk.tools import ToolContext

# Import from local config
from config import DEVELOPER_KNOWLEDGE_API_KEY

# Remove module-level API_KEY read
MCP_URL = "https://developerknowledge.googleapis.com/mcp"

def search_developer_knowledge(query: str, tool_context: ToolContext = None) -> str:
    """Search Google Developer Knowledge. Returns snippets and document names.

    Args:
        query: The search query.
    """

    if not DEVELOPER_KNOWLEDGE_API_KEY:
        return "Error: DEVELOPER_KNOWLEDGE_API_KEY not found in environment."

    headers = {
        "X-Goog-Api-Key": DEVELOPER_KNOWLEDGE_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_documents",
            "arguments": {
                "query": query
            }
        }
    }

    try:
        response = requests.post(MCP_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if "result" in data and "content" in data["result"]:
            content = data["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                first_block = content[0]
                if isinstance(first_block, dict) and "text" in first_block:
                    text = first_block["text"]
                    if text.startswith("```json"):
                        text = text.strip("```json").strip("```")
                    
                    try:
                        inner_data = json.loads(text)
                        if isinstance(inner_data, dict) and "results" in inner_data:
                            results = inner_data["results"]
                            formatted_results = []
                            for r in results:
                                formatted_results.append(f"Parent: {r.get('parent')}\nContent: {r.get('content')}\n---")
                            return "\n".join(formatted_results)
                    except json.JSONDecodeError:
                        return text
            
        return f"Unexpected response format: {data}"
    except Exception as e:
        return f"Error calling Developer Knowledge MCP: {e}"

def get_developer_knowledge_document(names: list[str] | str, tool_context: ToolContext = None) -> str:
    """Retrieve full content for specific Developer Knowledge documents.

    Args:
        names: A single document name or a list of document names.
               Format: `documents/{uri_without_scheme}` 
               Example: `documents/docs.cloud.google.com/storage/docs/creating-buckets`
    """
    if not DEVELOPER_KNOWLEDGE_API_KEY:
        return "Error: DEVELOPER_KNOWLEDGE_API_KEY not found in environment."

    if isinstance(names, str):
        names = [names]

    headers = {
        "X-Goog-Api-Key": DEVELOPER_KNOWLEDGE_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_documents",
            "arguments": {
                "names": names
            }
        }
    }

    try:
        response = requests.post(MCP_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if "result" in data and "content" in data["result"]:
            content = data["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                first_block = content[0]
                if isinstance(first_block, dict) and "text" in first_block:
                    text = first_block["text"]
                    if text.startswith("```json"):
                        text = text.strip("```json").strip("```")
                    
                    try:
                        inner_data = json.loads(text)
                        if isinstance(inner_data, dict) and "documents" in inner_data:
                            documents = inner_data["documents"]
                            formatted_docs = []
                            for doc in documents:
                                formatted_docs.append(f"Title: {doc.get('title')}\nURI: {doc.get('uri')}\nContent: {doc.get('content')}\n---")
                            return "\n".join(formatted_docs)
                    except json.JSONDecodeError:
                        return text
                        
        return f"Unexpected response format: {data}"
    except Exception as e:
        return f"Error calling Developer Knowledge MCP: {e}"
