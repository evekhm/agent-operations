import os
import sys
import logging


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

logging.basicConfig(level=logging.INFO)

from agents.observability_agent.utils.views import ensure_all_views

print("Updating Views...")
ensure_all_views()
print("Views Updated.")
