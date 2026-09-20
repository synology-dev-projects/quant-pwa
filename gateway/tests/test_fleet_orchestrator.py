#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gateway/tests/test_fleet_orchestrator.py - Unit tests for Multi-Repo Push & Verify Fleet Orchestrator
"""
import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import push_fleet
import verify_fleet


class TestPushFleetOrchestrator:
    """Tests for push_fleet.py topological sequencing and circuit breaker."""

    def test_topological_tiers_structure(self):
        """Verifies that all Quant System repositories are mapped into the correct tiers."""
        assert "common-lib" in push_fleet.TIER_1_REPOS
        assert len(push_fleet.TIER_1_REPOS) == 1, "Tier 1 must strictly isolate common-lib"

        for pipe in ["quant-level-pipeline", "unusual-option-flow-pipeline", "ibkr-historical-data-pipeline"]:
            assert pipe in push_fleet.TIER_2_REPOS

        assert "quant-pwa" in push_fleet.TIER_3_REPOS
        assert len(push_fleet.TIER_3_REPOS) == 1, "Tier 3 must isolate user application"

    @patch("subprocess.run")
    def test_check_unpushed_commits_detected(self, mock_run):
        """Verifies that unpushed commits are correctly identified via git diff."""
        # 1. git rev-parse --abbrev-ref HEAD
        mock_head = MagicMock(returncode=0, stdout="develop2\n")
        # 2. git rev-parse --verify origin/develop2
        mock_verify = MagicMock(returncode=0, stdout="abc1234\n")
        # 3. git log origin/develop2..develop2 --oneline
        mock_log = MagicMock(returncode=0, stdout="feat(levels): commit 1\nfix(math): commit 2\n")

        mock_run.side_effect = [mock_head, mock_verify, mock_log]

        has_unpushed, detail = push_fleet.check_unpushed_commits(Path("/mock/repo"), "develop2")
        assert has_unpushed is True
        assert "2 unpushed commit(s)" in detail

    @patch("subprocess.run")
    def test_check_unpushed_commits_up_to_date(self, mock_run):
        """Verifies clean status when local branch is identical to origin."""
        mock_head = MagicMock(returncode=0, stdout="develop2\n")
        mock_verify = MagicMock(returncode=0, stdout="abc1234\n")
        mock_log = MagicMock(returncode=0, stdout="")

        mock_run.side_effect = [mock_head, mock_verify, mock_log]

        has_unpushed, detail = push_fleet.check_unpushed_commits(Path("/mock/repo"), "develop2")
        assert has_unpushed is False
        assert "Up to date" in detail

    @patch("push_fleet.get_latest_run_for_repo")
    @patch("time.sleep")
    def test_circuit_breaker_halts_on_failure(self, mock_sleep, mock_get_run):
        """Proves that a failure in an active tier immediately halts downstream execution."""
        mock_get_run.return_value = {
            "databaseId": 12345,
            "status": "completed",
            "conclusion": "failure",
            "name": "Branch-Based Deployment Pipeline"
        }

        # Attempt to wait for Tier 1 containing common-lib
        passed = push_fleet.wait_for_tier_ci(["common-lib"], "develop2", timeout=30)
        assert passed is False, "Circuit breaker must return False on CI failure"

    @patch("push_fleet.get_latest_run_for_repo")
    @patch("time.sleep")
    def test_tier_ci_passes_when_all_green(self, mock_sleep, mock_get_run):
        """Verifies that wait_for_tier_ci returns True when all runs succeed."""
        mock_get_run.return_value = {
            "databaseId": 54321,
            "status": "completed",
            "conclusion": "success",
            "name": "Branch-Based Deployment Pipeline"
        }

        passed = push_fleet.wait_for_tier_ci(["common-lib"], "develop2", timeout=30)
        assert passed is True


class TestVerifyFleetGate:
    """Tests for verify_fleet.py status dashboard and gate evaluation."""

    @patch("verify_fleet.fetch_fleet_statuses")
    def test_verify_fleet_returns_zero_on_all_green(self, mock_statuses):
        """Asserts that exit code 0 is emitted when all CI-active repositories pass."""
        mock_statuses.return_value = {
            "common-lib": {"status": "completed", "conclusion": "success", "sha": "abc", "id": "1"},
            "quant-pwa": {"status": "completed", "conclusion": "success", "sha": "def", "id": "2"},
            "market-confluence-pipeline": {"status": "NO_RUN", "conclusion": "none", "sha": "-", "id": "-"}
        }

        exit_code = verify_fleet.verify_fleet(branch="develop2", wait=False)
        assert exit_code == 0

    @patch("verify_fleet.fetch_fleet_statuses")
    def test_verify_fleet_returns_one_on_failure(self, mock_statuses):
        """Asserts that exit code 1 is emitted when any CI-active repository fails."""
        mock_statuses.return_value = {
            "common-lib": {"status": "completed", "conclusion": "success", "sha": "abc", "id": "1"},
            "quant-pwa": {"status": "completed", "conclusion": "failure", "sha": "def", "id": "2"}
        }

        exit_code = verify_fleet.verify_fleet(branch="develop2", wait=False)
        assert exit_code == 1

    @patch("verify_fleet.fetch_fleet_statuses")
    def test_verify_fleet_returns_two_on_pending(self, mock_statuses):
        """Asserts that exit code 2 is emitted when builds are in-progress without wait."""
        mock_statuses.return_value = {
            "common-lib": {"status": "completed", "conclusion": "success", "sha": "abc", "id": "1"},
            "quant-pwa": {"status": "in_progress", "conclusion": "in_progress", "sha": "def", "id": "2"}
        }

        exit_code = verify_fleet.verify_fleet(branch="develop2", wait=False)
        assert exit_code == 2
