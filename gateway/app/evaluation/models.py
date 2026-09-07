"""
Quant AI Agent Evaluation & Benchmarking Models (AGENT-01)
Pydantic v2 data models defining test cases, evaluation categories,
per-case test results, category scorecards, and comprehensive benchmark reports.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EvaluationCategory(str, Enum):
    ROUTING = "routing"
    TOOL_ACCURACY = "tool_accuracy"
    SAFETY_DIRECTIVES = "safety_directives"
    MULTI_TURN = "multi_turn"
    LATENCY_SLA = "latency_sla"


class EvaluationTestCase(BaseModel):
    id: str = Field(..., description="Unique deterministic test case ID (e.g. TC-ROUTING-01)")
    name: str = Field(..., description="Human-readable test case name")
    category: EvaluationCategory = Field(..., description="Evaluation dimension category")
    prompt: str = Field(..., description="User prompt under test")
    history: Optional[List[Dict[str, Any]]] = Field(default=None, description="Simulated prior conversation history")
    
    # Routing assertions
    expected_tier: Optional[str] = Field(default=None, description="Expected synthesis tier (FAST or STRATEGIC)")
    expected_thinking_budget: Optional[int] = Field(default=None, description="Expected thinking budget (0 or 512)")
    
    # Tool accuracy assertions
    expected_tools: Optional[List[str]] = Field(default=None, description="Expected tool names to be invoked")
    expected_tool_args: Optional[Dict[str, Any]] = Field(default=None, description="Expected parameter keys/values")
    
    # Directive & safety assertions
    forbidden_patterns: Optional[List[str]] = Field(default=None, description="Regex patterns that MUST NOT appear in agent output")
    required_patterns: Optional[List[str]] = Field(default=None, description="Regex patterns that MUST appear in agent output")
    expected_tickers: Optional[List[str]] = Field(default=None, description="Tickers that must be present in output")
    
    # Multi-turn sequence
    multi_turn_prompts: Optional[List[str]] = Field(default=None, description="Sequential follow-up turns for multi-turn testing")
    
    description: Optional[str] = Field(default=None, description="Rationale, risk assessment, or invariant details")


class TestResult(BaseModel):
    case_id: str = Field(..., description="ID of the executed test case")
    category: EvaluationCategory = Field(..., description="Category evaluated")
    name: str = Field(..., description="Human-readable test case name")
    passed: bool = Field(..., description="Overall pass/fail boolean")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    actual_tier: Optional[str] = Field(default=None, description="Actual tier resolved by classifier")
    actual_tools: Optional[List[str]] = Field(default=None, description="Actual tools invoked")
    violations: List[str] = Field(default_factory=list, description="List of invariant failure messages")
    details: Optional[str] = Field(default=None, description="Additional contextual details or trace info")
    tokens_used: Optional[int] = Field(default=0, description="Token consumption (0 in deterministic mode)")


class CategoryScore(BaseModel):
    category: EvaluationCategory = Field(..., description="Category name")
    total: int = Field(..., description="Total test cases evaluated")
    passed: int = Field(..., description="Number of passed cases")
    failed: int = Field(..., description="Number of failed cases")
    accuracy_pct: float = Field(..., description="Percentage of passed cases (0.0 to 100.0)")
    gate_passed: bool = Field(..., description="True if category satisfies minimum quality gate")
    threshold_pct: float = Field(..., description="Minimum passing accuracy threshold")


class BenchmarkReport(BaseModel):
    benchmark_id: str = Field(..., description="Unique benchmark execution identifier")
    timestamp: str = Field(..., description="ISO 8601 execution timestamp")
    mode: str = Field(..., description="Execution mode: 'deterministic' or 'live'")
    total_cases: int = Field(..., description="Total cases executed across all categories")
    passed_cases: int = Field(..., description="Total cases passed")
    failed_cases: int = Field(..., description="Total cases failed")
    overall_accuracy_pct: float = Field(..., description="Overall accuracy percentage")
    category_scores: Dict[str, CategoryScore] = Field(..., description="Per-category scorecard")
    results: List[TestResult] = Field(default_factory=list, description="Individual test case results")
    verdict: str = Field(..., description="Overall gate verdict: 'PASSED' or 'FAILED'")
    summary_markdown: Optional[str] = Field(default=None, description="Monospace terminal/markdown report string")
