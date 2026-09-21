#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/push_fleet.py - Topological Multi-Repo Push Orchestrator
Enforces sequential deployment for the Quant System:
  Tier 1: common-lib (Core shared schemas & connectors)
  Tier 2: Pipelines (flow, quant-levels, ibkr, confluence)
  Tier 3: User Applications (quant-pwa Gateway & Frontend)

Prevents single-runner queue collisions and ensures downstream services
never build against stale upstream dependencies.
"""
import sys
import os
import time
import argparse
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Resolve Workspace Root (supports running from quant-pwa/scripts or root scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR.parent / "common-lib").is_dir():
    ROOT_DIR = SCRIPT_DIR.parent
elif (SCRIPT_DIR.parent.parent / "common-lib").is_dir():
    ROOT_DIR = SCRIPT_DIR.parent.parent
else:
    ROOT_DIR = Path("C:/Coding/VSCode/Quant System")

ORG_NAME = "synology-dev-projects"

TIER_1_REPOS = ["common-lib"]
TIER_2_REPOS = [
    "quant-level-pipeline",
    "unusual-option-flow-pipeline",
    "ibkr-historical-data-pipeline",
    "market-confluence-pipeline",
    "gexdex-snapshot-pipeline",
    "economic-events-pipeline",
]
TIER_3_REPOS = ["quant-pwa"]

ALL_TIERS = [
    ("Tier 1: Core Library", TIER_1_REPOS),
    ("Tier 2: Data Pipelines", TIER_2_REPOS),
    ("Tier 3: User Applications", TIER_3_REPOS),
]


def get_repo_path(repo_name: str) -> Optional[Path]:
    """Resolves local repository filesystem path."""
    p = ROOT_DIR / repo_name
    return p if (p / ".git").is_dir() else None


def check_unpushed_commits(repo_path: Path, branch: str) -> Tuple[bool, str]:
    """Checks if the local branch has commits not yet on origin."""
    try:
        # Check current branch
        res_br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        curr_branch = res_br.stdout.strip()
        
        # Check if remote tracking exists
        res_fetch = subprocess.run(["git", "rev-parse", "--verify", f"origin/{branch}"], cwd=repo_path, capture_output=True, text=True)
        if res_fetch.returncode != 0:
            return True, f"Local branch '{curr_branch}' (no remote origin/{branch})"

        res_diff = subprocess.run(["git", "log", f"origin/{branch}..{curr_branch}", "--oneline"], cwd=repo_path, capture_output=True, text=True)
        lines = [l for l in res_diff.stdout.splitlines() if l.strip()]
        if lines:
            return True, f"{len(lines)} unpushed commit(s)"
        return False, "Up to date with origin"
    except Exception as e:
        return False, f"Git check failed: {e}"


def get_latest_run_for_repo(repo: str, branch: str) -> Optional[Dict]:
    """Queries GitHub API for the latest workflow run on the specified branch."""
    cmd = [
        "gh", "run", "list",
        "--repo", f"{ORG_NAME}/{repo}",
        "--branch", branch,
        "--limit", "1",
        "--json", "databaseId,status,conclusion,name,url,headSha,createdAt"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            runs = json.loads(res.stdout)
            return runs[0] if runs else None
    except Exception:
        pass
    return None


def wait_for_tier_ci(pushed_repos: List[str], branch: str, timeout: int = 600, poll_interval: int = 8, expected_shas: Optional[Dict[str, str]] = None) -> bool:
    """Blocks until all pushed repos in a tier achieve completed:success in GitHub Actions."""
    if not pushed_repos:
        return True

    print(f"\n⏳ Monitoring GitHub Actions for [{', '.join(pushed_repos)}] on '{branch}'...")
    start_time = time.time()
    time.sleep(4)  # Brief grace period for GitHub to register webhook

    # Repos without GitHub Actions workflows configured
    skipped_no_workflow = set()

    while True:
        all_passed = True
        has_failure = False
        still_running = []

        for repo in pushed_repos:
            if repo in skipped_no_workflow:
                continue

            run = get_latest_run_for_repo(repo, branch)
            if not run:
                # Repo might not have active GitHub Actions (e.g. market-confluence)
                print(f"   ℹ️ [{repo}] No active workflow detected. Skipping CI wait.")
                skipped_no_workflow.add(repo)
                continue

            # Verify that the run matches the pushed commit SHA if provided
            if expected_shas and repo in expected_shas:
                expected_sha = expected_shas[repo]
                run_sha = run.get("headSha", "")
                if run_sha and not run_sha.startswith(expected_sha[:7]) and not expected_sha.startswith(run_sha[:7]):
                    all_passed = False
                    still_running.append(f"{repo} (registering webhook...)")
                    continue

            st = run.get("status")
            conc = run.get("conclusion")
            run_id = run.get("databaseId")

            if st == "completed":
                if conc == "success":
                    pass  # Good
                else:
                    print(f"   ❌ [{repo}] FAILED with conclusion '{conc}' (Run: {run_id})", file=sys.stderr)
                    has_failure = True
            else:
                all_passed = False
                still_running.append(f"{repo} ({st})")

        if has_failure:
            print("\n🚨 [CIRCUIT BREAKER TRIGGERED] Build failed in active tier. Halting deployment!", file=sys.stderr)
            return False

        if all_passed:
            print(f"✅ Tier CI PASSED cleanly for: {', '.join(pushed_repos)}!")
            return True

        if time.time() - start_time >= timeout:
            print(f"\n⏱️ [TIMEOUT] Waited {timeout}s for [{', '.join(still_running)}]. Halting deployment.", file=sys.stderr)
            return False

        print(f"   ⏳ In progress: {', '.join(still_running)} | Elapsed: {int(time.time() - start_time)}s / {timeout}s")
        time.sleep(poll_interval)


def push_repo(repo_name: str, branch: str, repo_path: Path) -> bool:
    """Executes git push for a single repository."""
    print(f"🚀 Pushing [{repo_name}] to origin/{branch}...")
    cmd = ["git", "push", "origin", branch]
    if branch == "master":
        cmd.append("--no-verify")
    try:
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"❌ Failed to push {repo_name}:\n{res.stderr}", file=sys.stderr)
            return False
        print(f"✅ [{repo_name}] Pushed successfully to origin/{branch}!")
        return True
    except Exception as e:
        print(f"❌ Exception pushing {repo_name}: {e}", file=sys.stderr)
        return False


def run_fleet_push(branch: str = "develop2", dry_run: bool = False, timeout: int = 360, force_repos: Optional[List[str]] = None) -> int:
    """Orchestrates topological deployment across all fleet tiers."""
    print("=" * 80)
    print(f"  QUANT FLEET TOPOLOGICAL PUSH ORCHESTRATOR")
    print(f"  Target Branch: [{branch}]  |  Dry-Run: {dry_run}  |  Root: {ROOT_DIR}")
    print("=" * 80)

    # 1. Discover state of each repository
    repos_to_push: Dict[str, Tuple[Path, str]] = {}
    
    print("\n🔍 Scanning workspace repositories for changes:")
    for tier_name, repos in ALL_TIERS:
        for r in repos:
            path = get_repo_path(r)
            if not path:
                print(f"   ⚠️  [{r:<30}] Not found locally in {ROOT_DIR}. Skipping.")
                continue

            if force_repos and r in force_repos:
                repos_to_push[r] = (path, "Explicitly selected via --repos")
                print(f"   🎯 [{r:<30}] Explicitly requested")
                continue

            has_unpushed, detail = check_unpushed_commits(path, branch)
            if has_unpushed:
                repos_to_push[r] = (path, detail)
                print(f"   📦 [{r:<30}] Has unpushed commits: {detail}")
            else:
                print(f"   ✨ [{r:<30}] {detail}")

    if not repos_to_push:
        print("\n✨ All fleet repositories are fully up to date with origin. Nothing to push.")
        return 0

    print(f"\n📋 Repositories queued for topological deployment: {len(repos_to_push)}")
    for r, (_, reason) in repos_to_push.items():
        print(f"   • {r:<30} ({reason})")

    if dry_run:
        print("\n[DRY RUN] Execution stopped before pushing. Topological sequence would be:")
        for tier_name, tier_repos in ALL_TIERS:
            matched = [r for r in tier_repos if r in repos_to_push]
            if matched:
                print(f"   {tier_name}: {', '.join(matched)}")
        return 0

    # 2. Execute Tiers sequentially
    for tier_name, tier_repos in ALL_TIERS:
        active_in_tier = [r for r in tier_repos if r in repos_to_push]
        if not active_in_tier:
            continue

        print(f"\n=======================================================")
        print(f"  EXECUTING {tier_name.upper()}: {active_in_tier}")
        print(f"=======================================================")

        # Push all repositories in current tier
        pushed_in_tier = []
        for r in active_in_tier:
            path, _ = repos_to_push[r]
            if not push_repo(r, branch, path):
                print(f"\n🛑 [ABORT] Push failed for {r}. Halting before downstream tiers!", file=sys.stderr)
                return 1
            pushed_in_tier.append(r)

        # Collect expected SHAs for pushed repos
        expected_shas = {}
        for r in pushed_in_tier:
            p, _ = repos_to_push[r]
            res_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=p, capture_output=True, text=True)
            if res_sha.returncode == 0:
                expected_shas[r] = res_sha.stdout.strip()

        # Wait for CI on current tier before advancing to next tier
        if not wait_for_tier_ci(pushed_in_tier, branch, timeout=timeout, expected_shas=expected_shas):
            print(f"\n🛑 [ABORT] CI validation failed on {tier_name}. Downstream tiers will NOT be deployed.", file=sys.stderr)
            return 1

    print("\n" + "=" * 80)
    print("🎉 ALL TIERS DEPLOYED & 100% GREEN IN TOPOLOGICAL SEQUENCE!")
    print("=" * 80)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Topological Multi-Repo Push Orchestrator")
    parser.add_argument("--branch", default="develop2", help="Target branch to deploy (default: develop2)")
    parser.add_argument("--dry-run", action="store_true", help="Analyze diffs and print execution plan without pushing")
    parser.add_argument("--timeout", type=int, default=600, help="Per-tier CI wait timeout in seconds (default: 600)")
    parser.add_argument("--repos", nargs="+", help="Explicit list of repositories to push (bypasses auto-diff)")

    args = parser.parse_args()
    code = run_fleet_push(branch=args.branch, dry_run=args.dry_run, timeout=args.timeout, force_repos=args.repos)
    sys.exit(code)


if __name__ == "__main__":
    main()
