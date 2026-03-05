import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
import time
import uuid

from dotenv import load_dotenv

# Setup path to import agents
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, ".."))
sys.path.append(os.path.join(dir_path, "../..")) # Add project root to path for imports

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.plugins import LoggingPlugin
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig, BigQueryAgentAnalyticsPlugin
from google.genai import types # Import types for Content
from agents.observability_agent.config import (
    PROJECT_ID, 
    DATASET_ID,
    AGENT_TABLE_ID,
    DEFAULT_KPIS
)
# Import the newly refactored root agent and config setter
from agents.observability_agent.agent import root_agent, set_playbook_config, create_augmentor_agent
from google.adk.agents import Agent

def _format_kpis_for_prompt(kpis: dict) -> str:
    lines = ["**STATIC KPIs (SLOs)**"]
    for k, v in kpis.items():
        if k == "per_agent":
            lines.append("- Custom per-agent KPIs:")
            for agent_name, agent_kpis in v.items():
                lines.append(f"  - `{agent_name}`:")
                for ak, av in agent_kpis.items():
                    if ak == "latency_target":
                       lines.append(f"    - Target: < {av}s")
                    elif ak == "percentile_target":
                       lines.append(f"    - Level: {av}%")
                    else:
                       lines.append(f"    - {ak}: {av}")
        else:
            lines.append(f"- {k.upper()} KPIs:")
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if sub_k == "latency_target":
                        lines.append(f"  - Target: < {sub_v}s")
                    elif sub_k == "percentile_target":
                        lines.append(f"  - Level: {sub_v}%")
                    else:
                        lines.append(f"  - {sub_k}: {sub_v}")
            else:
                 lines.append(f"  - {v}")
    return "\n".join(lines)

# Load Environment
load_dotenv(os.path.join(dir_path, "../.env"), override=True)

# Configure Logging
log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.ERROR))
logger = logging.getLogger(__name__)

def load_analyst_config() -> dict:
    """
    Loads configuration for the Observability Analyst.
    Priority (Lowest to Highest):
    1. Default: hardcoded fallback
    2. Local file: agents/observability_agent/config.json
    3. Try Env Var: LATENCY_ANALYSIS_CONFIG_FILE
    4. CLI Arguments
    """
    config = {
        "time_period": "7d",
        "kpis": DEFAULT_KPIS
    }

    # 2. Try Local config.json (relative to this file -> ../agents/observability_agent/config.json)
    # This is the canonical config location for the agent.
    agent_config_path = os.path.join(os.path.dirname(__file__), "../agents/observability_agent/config.json")
    if os.path.exists(agent_config_path):
        try:
            with open(agent_config_path, 'r') as f:
                logger.info(f"Loaded analyst config from {agent_config_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {agent_config_path}: {e}")

    env_path = os.getenv("LATENCY_ANALYSIS_CONFIG_FILE")
    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                logger.info(f"Loaded analyst config from {env_path}")
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            logger.error(f"Failed to load config from {env_path}: {e}")

    # 4. CLI Arguments
    parser = argparse.ArgumentParser(description="Observability Analyst CLI")
    parser.add_argument("--time_period", type=str, help="Time range for Current Reality")
    parser.add_argument("--baseline_period", type=str, help="Time range for Historical Baseline")
    parser.add_argument("--bucket_size", type=str, help="Bucket size for Playbook C")
    parser.add_argument("--playbook", type=str, choices=["overview", "health", "incident", "trend", "latest"], help="Force explicitly route to Playbook overview, health, incident, trend, or latest")
    
    # Parse known args so it doesn't crash if imported elsewhere
    args, _ = parser.parse_known_args(sys.argv[1:])
    
    if args.time_period: config["time_period"] = args.time_period
    if args.baseline_period: config["baseline_period"] = args.baseline_period
    if args.bucket_size: config["bucket_size"] = args.bucket_size
    if args.playbook: config["playbook"] = args.playbook

    return config


async def main():
    print("🤖 Initializing Observability Analyst Agent...")
    
    # Load dynamic config
    config = load_analyst_config()
    # Support wrapper objects (e.g. nested under "config" block or top-level)
    if "config" in config:
        config = config["config"]

    # Ensure defaults are visible in the log
    if "playbook" not in config: config["playbook"] = "overview"
    
    # Extract from nested blocks if available
    retrieval_cfg = config.get("data_retrieval", {})
    pres_cfg = config.get("data_presentation", {})
    
    config["num_slowest_queries"] = pres_cfg.get("num_slowest_queries", config.get("num_slowest_queries", 5))
    config["num_error_queries"] = pres_cfg.get("num_error_queries", config.get("num_error_queries", 5))
    config["num_queries_to_analyze_rca"] = retrieval_cfg.get("num_queries_to_analyze_rca", config.get("num_queries_to_analyze_rca", 1))

    # LOG THE FINAL CONFIG
    print(f"🔧 Loaded Analyst Config: {json.dumps(config, indent=2, default=str)}")

    time_period = config.get("time_period", "all")
    baseline_period = config.get("baseline_period", "7d")
    bucket_size = config.get("bucket_size", "1d")
    
    # Load KPIs and merge with defaults
    custom_kpis = config.get("kpis", {})
    kpis = DEFAULT_KPIS.copy()
    if isinstance(custom_kpis, dict):
        # Deep merge for per_agent
        if "per_agent" in custom_kpis and "per_agent" in kpis:
            kpis["per_agent"].update(custom_kpis.pop("per_agent"))
        kpis.update(custom_kpis)

    # Hydrate Prompt for the subagent
    set_playbook_config(
        time_period=time_period,
        baseline_period=baseline_period,
        bucket_size=bucket_size,
        kpis=kpis,
        num_slowest_queries=config.get("num_slowest_queries", 5),
        num_error_records=config.get("num_error_queries", 5),
        num_queries_to_analyze_rca=config.get("num_queries_to_analyze_rca", 5),
        config=config
    )
    
    playbook_name = config.get("playbook", "overview").capitalize()
    print(f"🚀 Starting Autonomous {playbook_name} Check...")
    
    # Create the augmentor agent
    augmentor_agent = create_augmentor_agent()
    
        # Run the Agent using Runner
    try:
        start_time = time.time()
        print("   (Reasoning in progress...)\n")
        response_text = ""
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        
        session_service = InMemorySessionService()
        await session_service.create_session(session_id=session_id, user_id=user_id, app_name="observability_analyst_app")
        
        def optimize_data_for_ai(raw_data: dict) -> str:
            import pandas as pd
            optimized = {}
            # Columns that consume massive amounts of tokens but don't help with high-level math/trends
            drop_cols = ['content_text_summary', 'error_message', 'User Message', 'Tool Args', 'Details (Trunk)']
            
            for key in ['df_roots', 'df_agents', 'df_tools', 'df_models']:
                df = raw_data.get(key)
                if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                    # Drop text columns if they exist
                    cols_to_drop = [c for c in drop_cols if c in df.columns]
                    df_opt = df.drop(columns=cols_to_drop)
                    
                    # Convert to dict, dropping NaNs
                    opt_dict = []
                    for _, row in df_opt.iterrows():
                        opt_dict.append({k: v for k, v in row.to_dict().items() if pd.notnull(v)})
                    optimized[key] = opt_dict
            
            return json.dumps(optimized, indent=2, default=str)
        # -1. SYNC VIEWS
        print("🔄 Syncing Observability Data Views...")
        from agents.observability_agent.utils.views import ensure_all_views
        try:
            ensure_all_views()
        except Exception as e:
            print(f"⚠️ Warning: Failed to sync views: {e}")

        # 0. FETCH DATA
        print("📥 Fetching Telemetry Data...")
        from tools.report_data import ReportDataManager
        data_manager = ReportDataManager(config)
        raw_data = await data_manager.fetch_all_data()

        # 0.5 INLINE RCA (Optional based on toggle)
        enable_ai = str(os.getenv("ENABLE_AI_AUGMENTATION", "true")).lower() in ("true", "1", "yes")
        
        if enable_ai:
            from tools.error_rca_analyzer import perform_inline_rca
            rca_limit = config.get("num_queries_to_analyze_rca", 1)
            raw_data = await perform_inline_rca(raw_data, limit=rca_limit)
        else:
            print("⏩ Skipping Inline RCA (ENABLE_AI_AUGMENTATION is false)")
        
        # DEBUG DUMP
        if 'root_bottlenecks' in raw_data and not raw_data['root_bottlenecks'].empty:
            raw_data['root_bottlenecks'].to_json('debug_root_bottlenecks.json', orient='records', indent=2)
        
        # 1. GENERATE DETERMINISTIC REPORT
        print("📊 Generating Deterministic Report (Data & Charts)...")
        from tools.generate_report import generate_report_content
        # Pass the fully merged config (which includes kpis) so it doesn't reload and lose defaults
        base_report_markdown = await generate_report_content(save_file=False, config=config, data=raw_data)
        print(f"   ✅ Base Report Generated ({len(base_report_markdown)} chars)")

        # 2. AUGMENT WITH AGENT (Executive Summary & Recommendations)
        if not enable_ai:
            print("⏩ Skipping heavy JSON AI Augmentation (fallback to simple text augmentation)")
            from agents.observability_agent.prompts import LEGACY_REPORT_AGENT_INSTRUCTION
            
            augmentor_agent.instruction = LEGACY_REPORT_AGENT_INSTRUCTION.format(
                time_period=time_period,
                project_id=PROJECT_ID
            )
            
            report_runner = Runner(
                agent=augmentor_agent,
                session_service=session_service,
                app_name="observability_analyst_app"
            )
            
            report_msg = types.Content(role="user", parts=[types.Part(text=f"Please read the following report and provide an executive summary and recommendations:\n{base_report_markdown}")])
            
            print("🤖 Appending concise AI insights...")
            response_text = ""
            async for event in report_runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=report_msg
            ):
                if event.content:
                    text_chunk = ""
                    if hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if part.text: text_chunk += part.text
                    elif isinstance(event.content, str):
                        text_chunk = event.content
                    if text_chunk:
                        print(text_chunk, end="", flush=True)
                        response_text += text_chunk
            
            # Legacy path just appends to the bottom
            final_report = f"{base_report_markdown}\n\n{response_text}"
            
        else:
            print("🤖 Augmenting Report with deep JSON Agent Insights...")
            
            from agents.observability_agent.prompts import AUGMENTATION_PROMPT
            
            # Optimize raw data for AI context (strip heavy text columns)
            raw_data_json = optimize_data_for_ai(raw_data)
            
            # Hydrate the prompt with Context + Data
            kpis_string = _format_kpis_for_prompt(kpis)
            
            augmentor_agent.instruction = AUGMENTATION_PROMPT.format(
                time_period=time_period,
                kpis_string=kpis_string,
                project_id=PROJECT_ID,
                base_report_markdown=base_report_markdown,
                raw_data_json=raw_data_json
            )
        
            # Run the Agent using Runner
            augmentor_runner = Runner(
                agent=augmentor_agent,
                session_service=session_service,
                app_name="observability_analyst_app"
            )
            
            user_msg = types.Content(role="user", parts=[types.Part(text="Please analyze the report and generate the required JSON output containing all summaries, bottlenecks, insights, and recommendations as specified in your instructions. Your response MUST be valid JSON.")])
            
            
            event_count = 0
            async for event in augmentor_runner.run_async(
                user_id=user_id, 
                session_id=session_id, 
                new_message=user_msg
            ):
                 event_count += 1
                 if event.content:
                    text_chunk = ""
                    if hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if part.text: text_chunk += part.text
                    elif isinstance(event.content, str):
                         text_chunk = event.content
                    
                    if text_chunk:
                        print(text_chunk, end="", flush=True)
                        response_text += text_chunk
            
            
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"\n\n✅ **Analysis & Augmentation Complete** (Execution Time: {execution_time:.2f} seconds)")
        
            # Parse output and inject into base report
            final_report = base_report_markdown
            import re
            
            # Find JSON in response
            # Try to extract from a markdown json block first
            json_match = re.search(r"```(?:json)?(.*?)```", response_text, re.DOTALL)
            json_str = json_match.group(1).strip() if json_match else response_text

            # If not, try to find the first { and the last }
            json_match = re.search(r"(\{.*\})", json_str, re.DOTALL)
            
            if json_match:
                try:
                    # Use strict=False to allow unescaped control characters in strings
                    insights = json.loads(json_match.group(1), strict=False)
                    exec_summary = insights.get("executive_summary", "No summary generated.")
                    performance_summary = insights.get("performance_summary", "No summary generated.")
                    end_to_end_summary = insights.get("end_to_end_summary", "No summary generated.")
                    agent_level_summary = insights.get("agent_level_summary", "No summary generated.")
                    tool_level_summary = insights.get("tool_level_summary", "No summary generated.")
                    model_level_summary = insights.get("model_level_summary", "No summary generated.")
                    agent_composition_summary = insights.get("agent_composition_summary", "No summary generated.")
                    model_composition_summary = insights.get("model_composition_summary", "No summary generated.")
                    bottlenecks_summary = insights.get("bottlenecks_summary", "No summary generated.")
                    error_analysis_summary = insights.get("error_analysis_summary", "No summary generated.")
                    
                    root_cause_insights = insights.get("root_cause_insights", "No insights generated.") or "No insights generated."
                    recommendations = insights.get("recommendations", "No recommendations generated.") or "No recommendations generated."
                    
                    # Ensure all summaries are strings
                    exec_summary = exec_summary or ""
                    performance_summary = performance_summary or ""
                    end_to_end_summary = end_to_end_summary or ""
                    agent_level_summary = agent_level_summary or ""
                    tool_level_summary = tool_level_summary or ""
                    model_level_summary = model_level_summary or ""
                    agent_composition_summary = agent_composition_summary or ""
                    model_composition_summary = model_composition_summary or ""
                    bottlenecks_summary = bottlenecks_summary or ""
                    error_analysis_summary = error_analysis_summary or ""
                    
                    # Sanitize: Remove leading headers if Agent included them (prevent duplication)
                    def clean_section(text):
                        lines = text.split('\n')
                        cleaned = []
                        for line in lines:
                            if line.lstrip().startswith('#'): continue
                            cleaned.append(line)
                        return '\n'.join(cleaned).strip()

                    exec_summary = clean_section(exec_summary)
                    root_cause_insights = clean_section(root_cause_insights)
                    recommendations = clean_section(recommendations)

                    # INJECT into Report
                    final_report = base_report_markdown.replace(
                        "(Executive Summary will be generated by AI Agent)", 
                        exec_summary
                    ).replace(
                        "(AI_SUMMARY: Performance)",
                        performance_summary
                    ).replace(
                        "(AI_SUMMARY: End to End)",
                        end_to_end_summary
                    ).replace(
                        "(AI_SUMMARY: Agent Level)",
                        agent_level_summary
                    ).replace(
                        "(AI_SUMMARY: Tool Level)",
                        tool_level_summary
                    ).replace(
                        "(AI_SUMMARY: Model Level)",
                        model_level_summary
                    ).replace(
                        "(AI_SUMMARY: Agent Composition)",
                        agent_composition_summary
                    ).replace(
                        "(AI_SUMMARY: Model Composition)",
                        model_composition_summary
                    ).replace(
                        "(AI_SUMMARY: System Bottlenecks & Impact)",
                        bottlenecks_summary
                    ).replace(
                        "(AI_SUMMARY: Error Analysis)",
                        error_analysis_summary
                    ).replace(
                        "(Root Cause Insights will be generated by AI Agent)", 
                        root_cause_insights
                    ).replace(
                        "(Recommendations will be generated by AI Agent)", 
                        recommendations
                    )
                    print("   ✨ Successfully injected AI insights into report.")
                except json.JSONDecodeError:
                    logger.error("Failed to parse Agent JSON response.")
                    print("   ⚠️ Failed to parse Agent JSON response. Using base report.")
            else:
                logger.warning("No JSON found in agent response.")
                print("   ⚠️ No JSON found in agent response. Using base report.")

        # 3. HOLISTIC CROSS-SECTION ANALYSIS
        if not enable_ai:
            print("⏩ Skipping Holistic Cross-Section Analysis (ENABLE_AI_AUGMENTATION is false)")
            holistic_response = ""
        else:
            print("\n🧠 Generating Holistic Cross-Section Analysis (This may take a minute depending on tool usage)...")
            from agents.whole_report_agent.agent import create_holistic_agent
            
            holistic_agent = create_holistic_agent()
            # Hydrate prompt with context
            holistic_agent.instruction = holistic_agent.instruction.format(
                time_period=time_period,
                project_id=PROJECT_ID,
                base_report_markdown=final_report,
                raw_data_json=raw_data_json
            )
            
            holistic_runner = Runner(
                agent=holistic_agent,
                session_service=session_service,
                app_name="observability_analyst_app"
            )
            
            # Trigger the agent
            holistic_msg = types.Content(role="user", parts=[types.Part(text="Please generate the '## Holistic Cross-Section Analysis' section using the context provided in your system instructions. Call your BigQuery tools to investigate deeper ONLY if you spot anomalies in the raw data or Report. Output purely the markdown text.")])
            
            holistic_response = ""
            async for event in holistic_runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=holistic_msg
            ):
                if event.content:
                    text_chunk = ""
                    if hasattr(event.content, "parts"):
                        for part in event.content.parts:
                            if part.text: text_chunk += part.text
                    elif isinstance(event.content, str):
                        text_chunk = event.content
                        
                    if text_chunk:
                        print(text_chunk, end="", flush=True)
                        holistic_response += text_chunk
                        
            print("\n\n✅ **Holistic Analysis Complete**")
            
        # Append before the Appendix
        if holistic_response.strip():
            if "## Appendix" in final_report:
                final_report = final_report.replace("## Appendix", f"{holistic_response.strip()}\n\n## Appendix")
            else:
                final_report += f"\n\n{holistic_response.strip()}\n"

        # Save Report
        if final_report.strip():
            # Use timestamp from config or now
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            playbook_name = config.get("playbook", "overview")
            base_dir = os.path.dirname(os.path.abspath(__file__))
            report_path = os.path.join(base_dir, f"../reports/observability_{playbook_name}_report_{timestamp}.md")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            
            with open(report_path, "w") as f:
                f.write(final_report)
            
            rel_report_path = os.path.normpath(os.path.relpath(report_path))
            abs_report_path = os.path.abspath(report_path)
            print(f"\n📄 Report saved to: {rel_report_path}")
            print(f"   (Absolute Path: {abs_report_path})")
        else:
            print("\n⚠️ No report content generated.")
        
        total_end_time = time.time()
        print(f"\n⏱️ Total script execution wall time: {total_end_time - start_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=3000)

if __name__ == "__main__":
    asyncio.run(main())
