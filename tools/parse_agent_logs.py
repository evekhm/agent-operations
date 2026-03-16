#!/usr/bin/env python3
import os
import sys
import re
import argparse
import glob
from datetime import datetime

def parse_logs(log_dir, num_files=10):
    """
    Parses the most recent observability agent logs and extracts key performance 
    milestones: Total running time, RCA phase time, Build phase time, and LLM call duration.
    """
    log_files = sorted(glob.glob(os.path.join(log_dir, "report_*.log")))[-num_files:]

    if not log_files:
        print(f"No report_*.log files found in {log_dir}")
        return

    time_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - .*? - (INFO|WARNING|ERROR) - (.*)")

    print(f"{'Log File':<30} | {'Total':<8} | {'RCA Time':<8} | {'Bld Time':<8} | {'LLM Time (Count)':<20}")
    print("-" * 80)

    for filepath in log_files:
        filename = os.path.basename(filepath)
        
        first_t = None
        last_t = None
        rca_start = None
        rca_end = None
        build_start = None
        build_end = None
        llm_durations = []
        current_llm_start = None
        
        with open(filepath, 'r') as f:
            for line in f:
                m = time_pattern.match(line)
                if m:
                    t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
                    msg = m.group(3)
                    
                    if first_t is None:
                        first_t = t
                    last_t = t
                    
                    # Track RCA Phase
                    if "Starting Inline Root Cause Analysis" in msg:
                        rca_start = t
                    elif "Inline RCA analysis complete" in msg:
                        rca_end = t
                    
                    # Track Report Build Phase
                    elif "[BUILD] Starting build_report..." in msg:
                        build_start = t
                    elif build_start is not None and build_end is None and ("Sending out request" in msg or "Response received" in msg):
                        build_end = t
                    
                    # Track LLM Requests within the report
                    if "Sending out request" in msg:
                        current_llm_start = t
                    elif "Response received" in msg and current_llm_start is not None:
                        llm_durations.append((t - current_llm_start).total_seconds())
                        current_llm_start = None
                        
        total_time = (last_t - first_t).total_seconds() if (last_t and first_t) else 0.0
        rca_time = (rca_end - rca_start).total_seconds() if (rca_end and rca_start) else 0.0
        bld_time = (build_end - build_start).total_seconds() if (build_end and build_start) else 0.0
        llm_total = sum(llm_durations)
        llm_cnt = len(llm_durations)
        
        print(f"{filename:<30} | {total_time:<7.1f}s | {rca_time:<7.1f}s | {bld_time:<7.1f}s | {llm_total:5.1f}s ({llm_cnt} calls)")

def main():
    parser = argparse.ArgumentParser(description="Parse Observability Agent Logs for phase performance timings.")
    parser.add_argument("--dir", type=str, default="/usr/local/google/home/evekhm/projects/adk/agent-operations-aa/logs",
                        help="Directory containing the log files.")
    parser.add_argument("-n", "--num", type=int, default=10, help="Number of recent logs to parse.")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.dir):
        print(f"Error: Directory '{args.dir}' does not exist.")
        sys.exit(1)
        
    parse_logs(args.dir, args.num)

if __name__ == "__main__":
    main()
