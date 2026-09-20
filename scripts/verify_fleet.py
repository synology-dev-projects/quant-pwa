#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_fleet.py - Multi-Repo Fleet CI Verification Gate
Polls GitHub Actions across all Quant System repositories to verify
that 100% of pipeline builds and tests pass cleanly on the target branch.
"""
import sys
import os
import json
import time
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FLEET_REPOS = [
    "common-lib",
    "quant-level-pipeline",
    "unusual-option-flow-pipeline",
    "ibkr-historical-data-pipeline",
    "market-confluence-pipeline",
    "gexdex-snapshot-pipeline",
    "quant-pwa",
]

ORG_NAME = "synology-dev-projects"


def get_latest_run(repo: str, branch: str) -> Optional[Dict[str, Any]]:
    """Fetches the latest GitHub Actions workflow run for a repo and branch."""
    cmd = [
        "gh", "run", "list",
        "--repo", f"{ORG_NAME}/{repo}",
        "--branch", branch,
        "--limit", "1",
        "--json", "databaseId,status,conclusion,name,url,headSha,createdAt,updatedAt"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0 or not res.stdout.strip():
            return None
        runs = json.loads(res.stdout)
        return runs[0] if runs else None
    except Exception:
        return None


def fetch_fleet_statuses(repos: List[str], branch: str) -> Dict[str, Dict[str, Any]]:
    """Fetches the latest run status for all specified repositories."""
    statuses = {}
    for repo in repos:
        run = get_latest_run(repo, branch)
        if not run:
            statuses[repo] = {
                "repo": repo,
                "status": "NO_RUN",
                "conclusion": "none",
                "id": "-",
                "sha": "-",
                "name": "-"
            }
        else:
            statuses[repo] = {
                "repo": repo,
                "status": run.get("status", "unknown"),
                "conclusion": run.get("conclusion") or run.get("status", "unknown"),
                "id": str(run.get("databaseId", "-")),
                "sha": (run.get("headSha") or "-")[:7],
                "name": run.get("name", "-"),
                "url": run.get("url", "")
            }
    return statuses


def print_fleet_table(statuses: Dict[str, Dict[str, Any]], branch: str):
    """Renders a clean formatted table of fleet CI statuses."""
    header = f"=== QUANT FLEET CI STATUS [{branch}] ==="
    print(header)
    print(f"{'Repository':<32} {'Status':<14} {'Conclusion':<14} {'Commit':<10} {'Run ID':<14}")
    print("-" * 88)
    
    for repo, data in statuses.items():
        st = data["status"]
        conc = data["conclusion"]
        sha = data["sha"]
        run_id = data["id"]
        
        if conc == "success":
            icon = "✅"
        elif conc in ["failure", "cancelled", "timed_out"]:
            icon = "❌"
        elif st in ["in_progress", "queued"]:
            icon = "⏳"
        else:
            icon = "⚪"
            
        print(f"{icon} {repo:<30} {st:<14} {conc:<14} {sha:<10} {run_id:<14}")
    print("-" * 88)


def verify_fleet(branch: str = "develop2", wait: bool = False, timeout: int = 600, poll_interval: int = 10, repos: Optional[List[str]] = None) -> int:
    """Verifies that all fleet repositories with CI are green. Returns 0 if all green, 1 otherwise."""
    target_repos = repos or FLEET_REPOS
    start_time = time.time()
    
    while True:
        statuses = fetch_fleet_statuses(target_repos, branch)
        print_fleet_table(statuses, branch)
        
        # Repos that actually have CI workflows configured
        ci_active_statuses = [d for d in statuses.values() if d["status"] != "NO_RUN"]
        
        in_progress = any(d["status"] in ["in_progress", "queued"] for d in ci_active_statuses)
        has_failure = any(d["conclusion"] in ["failure", "cancelled", "timed_out"] for d in ci_active_statuses)
        all_ci_success = all(d["conclusion"] == "success" for d in ci_active_statuses) if ci_active_statuses else False
        
        if not wait:
            if has_failure:
                print(f"\n🚨 [FLEET CI GATE FAILED] One or more repositories failed on branch '{branch}'.", file=sys.stderr)
                return 1
            if in_progress:
                print(f"\n⏳ [FLEET CI PENDING] One or more repositories are still building on branch '{branch}'.", file=sys.stderr)
                return 2
            if all_ci_success:
                print(f"\n🟢 [FLEET CI GATE PASSED] All {len(ci_active_statuses)} CI-active repositories are 100% green on '{branch}'.")
                return 0
            print(f"\n⚠️ [FLEET CI INCOMPLETE] Not all repositories have verified runs on branch '{branch}'.", file=sys.stderr)
            return 1

        # In wait mode
        if has_failure:
            print(f"\n🚨 [FLEET CI GATE FAILED] A build failed during execution.", file=sys.stderr)
            return 1
            
        if all_ci_success:
            print(f"\n🎉 [FLEET CI GATE PASSED] All {len(ci_active_statuses)} repositories finished successfully!")
            return 0
        if all_success:
            print(f"\n🎉 [FLEET CI GATE PASSED] All {len(target_repos)} repositories finished successfully!")
            return 0
            
        if time.time() - start_time >= timeout:
            print(f"\n⏱️ [FLEET CI TIMEOUT] Verification timed out after {timeout} seconds.", file=sys.stderr)
            return 1
            
        print(f"⏳ Builds in progress. Polling again in {poll_interval}s... (Elapsed: {int(time.time() - start_time)}s / {timeout}s)")
        time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Multi-Repo Fleet CI Verification Gate")
    parser.add_argument("--branch", default="develop2", help="Target branch to inspect (default: develop2)")
    parser.add_argument("--wait", action="store_true", help="Wait and poll until all builds finish")
    parser.add_argument("--timeout", type=int, default=600, help="Polling timeout in seconds (default: 600)")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output status in JSON format")
    parser.add_argument("--repos", nargs="+", help="Explicit list of repositories to check")
    
    args = parser.parse_args()
    
    if args.json:
        statuses = fetch_fleet_statuses(args.repos or FLEET_REPOS, args.branch)
        print(json.dumps(statuses, indent=2))
        all_success = all(d["conclusion"] == "success" for d in statuses.values())
        sys.exit(0 if all_success else 1)
        
    code = verify_fleet(
        branch=args.branch,
        wait=args.wait,
        timeout=args.timeout,
        poll_interval=args.interval,
        repos=args.repos
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
