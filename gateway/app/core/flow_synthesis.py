"""
gateway/app/core/flow_synthesis.py
Extensible, Pluggable Synthesis Engine for Institutional Options Flow Analysis.

Enforces:
1. Pluggable Architecture: Developers can register/unregister analytical points easily.
2. Initial Core Point:
   - Notable Flow: Standardized structured hierarchy:
     • **Notable Flow**:
       • **TOP PREMIUM**:
         - TICKER $XX.XM PREMIUM (1st)
       • **NOTABLE OTM**:
         - TICKER XX% OTM exp 2 weeks
     (or "- NONE FOUND" if empty).
3. Strict Constraints: Zero trade advice, TELEGRAPHIC / ZERO ADJECTIVES, ADHD-friendly brevity.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import sqlalchemy as sa
from app.core.flow_criteria import (
    extract_session_notable_flow_db,
    format_notable_flow_markdown,
    format_rank_suffix,
    format_dte_exp,
    format_currency
)

logger = logging.getLogger("quant.gateway.flow_synthesis")


class FlowSynthesisPoint(ABC):
    """Abstract base class for a Flow Synthesis analytical point."""

    def __init__(self, point_id: str, title: str):
        self.point_id = point_id
        self.title = title

    @abstractmethod
    def extract_features(self, conn: sa.Connection, latest_date: str) -> Dict[str, Any]:
        """Extracts and computes point-specific quantitative features from the database."""
        pass

    @abstractmethod
    def get_prompt_instruction(self, features: Dict[str, Any]) -> str:
        """Returns the specific prompt instruction and extracted metrics for the LLM."""
        pass

    @abstractmethod
    def generate_deterministic(self, features: Dict[str, Any]) -> str:
        """Generates the bullet point deterministically for fallback / offline execution."""
        pass


class NotableFlowPoint(FlowSynthesisPoint):
    """
    Standardized Notable Flow Point for Flow Tab.
    Structures outliers across all tickers for latest_date into:
    • **Notable Flow**:
      • **TOP PREMIUM**:
        - TICKER $XX.XM PREMIUM (1st)
      • **NOTABLE OTM**:
        - TICKER XX% OTM exp 2 weeks
    With "- NONE FOUND" fallbacks.
    """

    def __init__(self):
        super().__init__(
            point_id="notable_flow",
            title="Notable Flow"
        )

    def extract_features(self, conn: sa.Connection, latest_date: str) -> Dict[str, Any]:
        top_premium_prints, notable_otm_prints = extract_session_notable_flow_db(conn, latest_date)
        return {
            "latest_date": latest_date,
            "top_premium_prints": top_premium_prints,
            "top_all_time_prints": top_premium_prints,
            "notable_otm_prints": notable_otm_prints,
            "deep_otm_prints": notable_otm_prints
        }

    def get_prompt_instruction(self, features: Dict[str, Any]) -> str:
        top_premium = (features.get("top_premium_prints") or features.get("top_all_time_prints") or [])[:3]
        notable_otm = (features.get("notable_otm_prints") or features.get("deep_otm_prints") or [])[:3]

        lines = [
            f"• **Notable Flow**:",
            f"  • **TOP PREMIUM**:"
        ]
        if top_premium:
            for p in top_premium:
                rank_str = format_rank_suffix(p.get("rank", 1))
                sym = str(p.get("symbol", "")).upper()
                prem = p.get("formatted_premium") or format_currency(p.get("premium"))
                lines.append(f"    - {sym} {prem} PREMIUM ({rank_str})")
        else:
            lines.append("    - NONE FOUND")

        lines.append("  • **NOTABLE OTM**:")
        if notable_otm:
            for o in notable_otm:
                sym = str(o.get("symbol", "")).upper()
                otm_pct = abs(float(o.get("otm_pct", 0.0)))
                exp_str = format_dte_exp(int(o.get("dte", 0)))
                lines.append(f"    - {sym} {otm_pct:.0f}% OTM {exp_str}")
        else:
            lines.append("    - NONE FOUND")

        return "\n".join(lines)

    def generate_deterministic(self, features: Dict[str, Any]) -> str:
        top_premium = features.get("top_premium_prints") or features.get("top_all_time_prints") or []
        notable_otm = features.get("notable_otm_prints") or features.get("deep_otm_prints") or []
        return format_notable_flow_markdown(top_premium, notable_otm)


class FlowSynthesisRegistry:
    """
    Pluggable registry for Flow Tab Synthesis analysis points.
    Allows registering additional points in the future with zero boilerplate.
    """

    def __init__(self):
        self._points: List[FlowSynthesisPoint] = []
        # Register default initial point
        self.register(NotableFlowPoint())

    def register(self, point: FlowSynthesisPoint):
        """Registers an analytical point."""
        self._points = [p for p in self._points if p.point_id != point.point_id]
        self._points.append(point)
        logger.info(f"Registered FlowSynthesisPoint: '{point.point_id}' ({point.title})")

    def unregister(self, point_id: str):
        """Unregisters an analytical point."""
        self._points = [p for p in self._points if p.point_id != point_id]
        logger.info(f"Unregistered FlowSynthesisPoint: '{point_id}'")

    def get_points(self) -> List[FlowSynthesisPoint]:
        """Returns the list of currently registered points."""
        return list(self._points)

    def extract_all_features(self, conn: sa.Connection, latest_date: str) -> Dict[str, Dict[str, Any]]:
        """Extracts features for all registered points."""
        features_by_point = {}
        for point in self._points:
            try:
                features_by_point[point.point_id] = point.extract_features(conn, latest_date)
            except Exception as e:
                logger.error(f"Error extracting features for flow point '{point.point_id}': {e}", exc_info=True)
                features_by_point[point.point_id] = {}
        return features_by_point

    def build_synthesis_prompt(self, latest_date: str, all_features: Dict[str, Dict[str, Any]]) -> str:
        """Constructs the LLM prompt using all registered points."""
        point_instructions = []
        for point in self._points:
            features = all_features.get(point.point_id, {})
            point_instructions.append(point.get_prompt_instruction(features))

        instructions_block = "\n".join(point_instructions)

        return f"""You are Quant AI's Institutional Options Flow Quantitative Analyst.
Output an ultra-short, highly digestible institutional options flow analysis from the latest completed market session ({latest_date}).

CRITICAL FORMAT REQUIREMENT:
You MUST format your output EXACTLY as shown in the template below.
Do NOT combine or summarize nested bullets into prose, paragraphs, or single sentences.
Do NOT omit the sub-headings "• **TOP PREMIUM**:" or "• **NOTABLE OTM**:".
Each item under sub-headings must be an indented bullet starting with "    - ".

TEMPLATE:
### Market Flow Snapshot
• **Notable Flow**:
  • **TOP PREMIUM**:
    - TICKER $XX.XM PREMIUM (rank)
  • **NOTABLE OTM**:
    - TICKER XX% OTM exp X weeks
(If a subcategory has no items, output "    - NONE FOUND").

STRICT CONSTRAINTS:
1. NEVER GIVE TRADE ADVICE: Absolutely NEVER recommend trades, buy/sell actions, entry/exit targets, or financial advice. Purely objective quantitative data.
2. TELEGRAPHIC / ZERO ADJECTIVES: Never use descriptive or subjective adjectives (no 'heavy', 'primary', 'massive', 'aggressive', 'significant', 'strong', 'critical'). Strictly state symbols, figures, and ranks.
3. PRESERVE EXACT SUB-BULLETS: Follow the exact indentation, bullet markers, and hierarchy.

DATA TO FORMAT:
{instructions_block}
"""

    def generate_deterministic_synthesis(self, all_features: Dict[str, Dict[str, Any]]) -> str:
        """Fallback deterministic synthesis generator when Gemini API is offline or unconfigured."""
        lines = ["### Market Flow Snapshot"]
        for point in self._points:
            features = all_features.get(point.point_id, {})
            lines.append(point.generate_deterministic(features))
        return "\n".join(lines) + "\n"


# Global singleton registry instance
flow_synthesis_registry = FlowSynthesisRegistry()
