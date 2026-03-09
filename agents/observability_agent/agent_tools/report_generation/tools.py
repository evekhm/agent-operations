import datetime
import json
import logging
import os
import time

from .generate_report import generate_report_content
from .report_data import ReportDataManager

logger = logging.getLogger(__name__)

from google.adk.tools import ToolContext
from ...config import PROJECT_ID

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

async def generate_base_report(tool_context: ToolContext, time_period: str = "7d", bucket_size: str = "1d", baseline_period: str = "7d", playbook: str = "overview") -> str:
    """
    Fetches observability telemetry data and generates a base deterministic Markdown report with charts.
    Use this tool to compile raw data into a baseline report before appending AI insights.
    
    Args:
        time_period: The time range to analyze (e.g. '7d', '24h').
        bucket_size: Bucket size for trends.
        baseline_period: Baseline period for trends.
        playbook: The playbook type ('overview', etc.).
        
    Returns:
        str: The raw Markdown string AND charts summary to be analyzed by the LLM.
    """
    if "report_start_time" not in tool_context.session.state:
        tool_context.session.state["report_start_time"] = time.time()
        
    logger.info(f"[TOOL CALL-generate_base_report] time_period={time_period}")
    try:
        config = {
            "time_period": time_period,
            "baseline_period": baseline_period,
            "bucket_size": bucket_size,
            "playbook": playbook,
            "kpis": {},
            "data_retrieval": {},
            "data_presentation": {}
        }
        
        # Load any local config if present
        agent_config_path = os.path.join(os.path.dirname(__file__), "../../config.json")
        if os.path.exists(agent_config_path):
            with open(agent_config_path, 'r') as f:
                loaded = json.load(f)
                if "config" in loaded:
                    loaded = loaded["config"]
                config.update(loaded)
        
        # Override with tool argument
        config["time_period"] = time_period
        config["report_timestamp"] = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if "data_retrieval" not in config:
            config["data_retrieval"] = {}
        config["data_retrieval"]["time_period"] = time_period
                
        # Sync views
        # (Removed redundant view syncing, handled reliably by data fetcher if data is None)
        
        # Fetch data
        data_manager = ReportDataManager(config)
        raw_data = await data_manager.fetch_all_data()
        
        print(f"\n   ✅ Base Report Generated", flush=True)
        print("\n🤖 Augmenting Report with deep JSON Agent Insights...", flush=True)
        
        # Generate base report
        base_report_markdown = await generate_report_content(save_file=False, config=config, data=raw_data)
        

        raw_data_json = json.dumps(raw_data.get("chart_summaries", {}), indent=2)
        
        # Save to context state for the LLM prompts to hydrate correctly
        tool_context.session.state["time_period"] = time_period
        tool_context.session.state["report_timestamp"] = config["report_timestamp"]
        tool_context.session.state["project_id"] = PROJECT_ID
        tool_context.session.state["kpis_string"] = _format_kpis_for_prompt(config["kpis"])
        tool_context.session.state["base_report_markdown"] = base_report_markdown
        tool_context.session.state["raw_data_json"] = raw_data_json
        
        return "Base report and telemetry generated successfully. Please proceed with augmentation summary generation."
    except Exception as e:
        logger.error(f"Error generating base report: {e}")
        return f"Error generating base report: {str(e)}"

async def save_report(report_content: str, playbook_name: str = "overview", timestamp: str = None) -> str:
    """
    Saves the finalized Markdown report content to the filesystem.
    """
    try:
        from ...config import AGENT_VERSION
        formatted_version = AGENT_VERSION.replace('.', '')
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, f"../../../../reports/observability_{playbook_name}_report_{timestamp}_v{formatted_version}.md")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        
        with open(report_path, "w") as f:
            f.write(report_content)
        
        pdf_path = report_path.replace(".md", ".pdf")
        pdf_status = ""
        try:
            from pathlib import Path
            from md2pdf.core import md2pdf
            md_p = Path(report_path).absolute()
            pdf_p = Path(pdf_path).absolute()
            css_p = Path(base_dir) / "pdf_style.css"
            
            md2pdf(pdf=pdf_p, md=md_p, css=css_p, base_url=md_p.parent)
            
            rel_pdf_path = os.path.normpath(os.path.relpath(pdf_path))
            abs_pdf_path = os.path.abspath(pdf_path)
            pdf_status = f"\nPDF visually generated and saved to: `{rel_pdf_path}`\n   (Absolute Path: {abs_pdf_path})"
        except Exception as pdf_e:
            pdf_status = f"\nFailed to generate PDF report: {str(pdf_e)}"
            logger.error(f"Failed to generate PDF report: {pdf_e}")
        
        rel_report_path = os.path.normpath(os.path.relpath(report_path))
        abs_report_path = os.path.abspath(report_path)
        
        # Create a ZIP archive for easier sharing
        import zipfile
        zip_path = report_path.replace(".md", ".zip")
        assets_dir = os.path.join(os.path.dirname(report_path), f"report_assets_{timestamp}")
        zip_status = ""
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add the Markdown report
                zipf.write(report_path, arcname=os.path.basename(report_path))
                
                # Add the PDF if it exists, since some users still want it in the bundle
                if os.path.exists(pdf_path):
                    zipf.write(pdf_path, arcname=os.path.basename(pdf_path))
                    
                # Add the assets folder contents
                if os.path.exists(assets_dir):
                    for root_dir, _, files in os.walk(assets_dir):
                        for file in files:
                            file_path = os.path.join(root_dir, file)
                            # Keep the report_assets directory structure intact within the zip
                            arcname = os.path.relpath(file_path, os.path.dirname(assets_dir))
                            zipf.write(file_path, arcname=arcname)
                            
            rel_zip_path = os.path.normpath(os.path.relpath(zip_path))
            abs_zip_path = os.path.abspath(zip_path)
            zip_status = f"\n**Zipped Archive:**\n*   Relative Path: `{rel_zip_path}`\n*   Absolute Path: `{abs_zip_path}`\n"
        except Exception as zip_e:
            zip_status = f"\nFailed to generate ZIP archive: {str(zip_e)}"
            logger.error(f"Failed to generate ZIP archive: {zip_e}")

        # Explicitly print the paths to standard out to bypass non-deterministic AI generation
        print("\n\nReport successfully generated.\n", flush=True)
        if zip_status:
            print(zip_status, flush=True)
        print("**Markdown Report:**", flush=True)
        print(f"*   Relative Path: `{rel_report_path}`\n*   Absolute Path: `{abs_report_path}`\n", flush=True)

        return "Success: The report has been generated and saved. The file paths have been printed directly to the terminal for the user."
    except Exception as e:
        return f"Failed to save report: {str(e)}"

import re
async def inject_and_save_report(tool_context: ToolContext, insights_json_str: str, holistic_analysis: str = "", playbook_name: str = "overview") -> str:
    """
    Injects AI-generated JSON insights into the base deterministic report placeholders and saves it.
    """
    try:
        final_report = tool_context.session.state.get("base_report_markdown", "")
        if not final_report:
            return "Error: base_report_markdown not found in session state. Did you call generate_base_report first?"
            
        if not holistic_analysis:
            holistic_analysis = tool_context.session.state.get("holistic_analysis", "")
            
        json_match = re.search(r"```(?:json)?(.*?)```", insights_json_str, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else insights_json_str
        
        json_match = re.search(r"(\{.*\})", json_str, re.DOTALL)
        if json_match:
            insights = json.loads(json_match.group(1), strict=False)
            
            def clean_section(text):
                if isinstance(text, list):
                    text = "\n".join(str(item) for item in text)
                lines = (text or "").split('\n')
                cleaned = [line for line in lines if not line.lstrip().startswith('#')]
                return '\n'.join(cleaned).strip()

            final_report = final_report.replace("(Executive Summary will be generated by AI Agent)", clean_section(insights.get("executive_summary", "")))
            final_report = final_report.replace("(AI_SUMMARY: Performance)", insights.get("performance_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: End to End)", insights.get("end_to_end_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Agent Level)", insights.get("agent_level_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Tool Level)", insights.get("tool_level_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Model Level)", insights.get("model_level_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Agent Composition)", insights.get("agent_composition_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Model Composition)", insights.get("model_composition_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Agent Token Statistics)", insights.get("agent_token_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Model Token Statistics)", insights.get("model_token_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: System Bottlenecks & Impact)", insights.get("bottlenecks_summary", ""))
            final_report = final_report.replace("(AI_SUMMARY: Error Analysis)", insights.get("error_analysis_summary", ""))
            final_report = final_report.replace("(Root Cause Insights will be generated by AI Agent)", clean_section(insights.get("root_cause_insights", "")))
            final_report = final_report.replace("(Recommendations will be generated by AI Agent)", clean_section(insights.get("recommendations", "")))

            # Catch orphaned insights that didn't match placeholders
            used_keys = {
                "executive_summary", "performance_summary", "end_to_end_summary", "agent_level_summary",
                "tool_level_summary", "model_level_summary", "agent_composition_summary",
                "model_composition_summary", "agent_token_summary", "model_token_summary",
                "bottlenecks_summary", "error_analysis_summary", "root_cause_insights", "recommendations"
            }
            orphaned_keys = set(insights.keys()) - used_keys
            expected_empty_keys = {k for k, v in insights.items() if not v and k in orphaned_keys}
            orphaned_keys = orphaned_keys - expected_empty_keys
            
            if orphaned_keys:
                orphaned_content = "\n\n---\n\n## Additional AI Insights\n\n"
                for key in orphaned_keys:
                    val = insights[key]
                    if val and isinstance(val, str) and val.strip():
                        friendly_name = key.replace("_", " ").title()
                        orphaned_content += f"### {friendly_name}\n{val.strip()}\n\n"
                
                final_report += orphaned_content
            
        if holistic_analysis.strip():
            if "# Appendix" in final_report:
                final_report = final_report.replace("# Appendix", f"{holistic_analysis.strip()}\n\n# Appendix")
            else:
                final_report += f"\n\n{holistic_analysis.strip()}\n"
                
        if "report_start_time" in tool_context.session.state:
            elapsed = time.time() - tool_context.session.state["report_start_time"]
            final_report += f"\n\n---\n**Report Generation Time:** {elapsed:.2f} seconds\n"
                
        report_timestamp = tool_context.session.state.get("report_timestamp")
        return await save_report(final_report, playbook_name, timestamp=report_timestamp)
    except Exception as e:
        logger.error(f"Failed to inject insights: {e}")
        return f"Failed to inject and save report: {str(e)}"
