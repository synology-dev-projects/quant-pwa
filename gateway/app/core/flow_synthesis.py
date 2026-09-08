"""
gateway/app/core/flow_synthesis.py
Extensible, Pluggable Synthesis Engine for Institutional Options Flow Analysis.

Enforces:
1. Pluggable Architecture: Developers can register/unregister analytical points easily.
2. Initial Core Point:
   - Notable Flow: Analyzes the latest completed market session across all tickers.
     Identifies flow records that rank in the top 3 highest premiums to date for that specific ticker,
     plus deep OTM short-expiry tail-risk speculation (>= 15% OTM, <= 30 DTE).
3. Strict Constraints: ADHD-Brevity (1-2 punchy sentences per point), bold tickers/numbers, zero trade advice.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import sqlalchemy as sa
import pandas as pd

logger = logging.getLogger("quant.gateway.flow_synthesis")


def _format_currency(val: Optional[float]) -> str:
    if val is None:
        return "$0"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    elif abs_val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


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
    Analyzes all tickers from the latest market session date.
    Identifies:
    1. Any flow print that ranks in the top 3 highest premiums EVER recorded for that specific ticker.
    2. Deep OTM tail-risk speculative flow (>= 15% OTM and <= 30 DTE).
    3. Fallback to session's dominant whale flow print if no extreme outliers exist.
    """

    def __init__(self):
        super().__init__(
            point_id="notable_flow",
            title="Notable Flow"
        )

    def extract_features(self, conn: sa.Connection, latest_date: str) -> Dict[str, Any]:
        if not latest_date:
            return {
                "latest_date": None,
                "top_all_time_prints": [],
                "deep_otm_prints": [],
                "top_whale_print": None
            }

        # 1. Query prints from latest_date evaluated against all historical records for each ticker
        query_all_time = sa.text("""
            WITH ranked_flow AS (
                SELECT 
                    flow_id,
                    trade_date,
                    symbol,
                    order_type,
                    strike_price,
                    strike_otm_pct,
                    expiration_date,
                    premium,
                    open_interest,
                    is_unusual_oi,
                    DENSE_RANK() OVER (PARTITION BY symbol ORDER BY premium DESC) as all_time_rank
                FROM unusual_option_flow_te
                WHERE strike_price > 0
            )
            SELECT *
            FROM ranked_flow
            WHERE trade_date = :latest_date
              AND all_time_rank <= 3
            ORDER BY premium DESC
            LIMIT 5
        """)

        try:
            rows_all_time = conn.execute(query_all_time, {"latest_date": latest_date}).mappings().all()
        except Exception as e:
            logger.warning(f"Failed to query all_time_rank flow: {e}")
            rows_all_time = []

        top_all_time_prints = []
        for r in rows_all_time:
            top_all_time_prints.append({
                "symbol": str(r["symbol"]).upper(),
                "order_type": str(r["order_type"]),
                "strike": float(r["strike_price"]),
                "premium": float(r["premium"]),
                "formatted_premium": _format_currency(float(r["premium"])),
                "rank": int(r["all_time_rank"]),
                "expiration_date": str(r["expiration_date"])
            })

        # 2. Query deep OTM short-expiry speculative prints (>= 15% OTM, <= 30 DTE)
        query_deep_otm = sa.text("""
            SELECT 
                symbol,
                order_type,
                strike_price,
                strike_otm_pct,
                expiration_date,
                trade_date,
                premium,
                (expiration_date - trade_date) as dte
            FROM unusual_option_flow_te
            WHERE trade_date = :latest_date
              AND strike_price > 0
              AND ABS(strike_otm_pct) >= 15.0
              AND (expiration_date - trade_date) <= 30
            ORDER BY premium DESC
            LIMIT 5
        """)

        try:
            rows_deep_otm = conn.execute(query_deep_otm, {"latest_date": latest_date}).mappings().all()
        except Exception as e:
            logger.warning(f"Failed to query deep_otm flow: {e}")
            rows_deep_otm = []

        deep_otm_prints = []
        for r in rows_deep_otm:
            deep_otm_prints.append({
                "symbol": str(r["symbol"]).upper(),
                "order_type": str(r["order_type"]),
                "strike": float(r["strike_price"]),
                "otm_pct": float(r["strike_otm_pct"]),
                "dte": int(r["dte"]) if r["dte"] is not None else 0,
                "premium": float(r["premium"]),
                "formatted_premium": _format_currency(float(r["premium"]))
            })

        # 3. Dominant whale print fallback for the session
        query_top_whale = sa.text("""
            SELECT 
                symbol,
                order_type,
                strike_price,
                expiration_date,
                premium
            FROM unusual_option_flow_te
            WHERE trade_date = :latest_date
              AND strike_price > 0
            ORDER BY premium DESC
            LIMIT 1
        """)
        try:
            row_whale = conn.execute(query_top_whale, {"latest_date": latest_date}).mappings().first()
            top_whale = dict(row_whale) if row_whale else None
            if top_whale:
                top_whale["formatted_premium"] = _format_currency(float(top_whale["premium"]))
        except Exception as e:
            logger.warning(f"Failed to query top whale flow: {e}")
            top_whale = None

        return {
            "latest_date": latest_date,
            "top_all_time_prints": top_all_time_prints,
            "deep_otm_prints": deep_otm_prints,
            "top_whale_print": top_whale
        }

    def get_prompt_instruction(self, features: Dict[str, Any]) -> str:
        all_time_prints = features.get("top_all_time_prints", [])
        deep_otm = features.get("deep_otm_prints", [])
        top_whale = features.get("top_whale_print")
        latest_date = features.get("latest_date", "recent session")

        bullets = []
        if all_time_prints:
            p_desc = []
            for p in all_time_prints[:3]:
                rank_suffix = {1: "1st", 2: "2nd", 3: "3rd"}.get(p["rank"], f"{p['rank']}th")
                p_desc.append(
                    f"{p['symbol']} {p['order_type']} ({p['formatted_premium']} at strike ${p['strike']:.2f}) "
                    f"ranking as the {rank_suffix} highest premium on record to date for {p['symbol']}"
                )
            bullets.append(f"Session All-Time Outliers: {'; '.join(p_desc)}.")
        
        if deep_otm:
            o_desc = []
            for o in deep_otm[:2]:
                o_desc.append(
                    f"{o['symbol']} strike ${o['strike']:.2f} ({o['otm_pct']:+.1f}% OTM, {o['dte']} DTE, {o['formatted_premium']})"
                )
            bullets.append(f"Deep OTM Tail Risk: {'; '.join(o_desc)}.")

        if not all_time_prints and not deep_otm and top_whale:
            bullets.append(
                f"Session Dominant Print: {top_whale['symbol']} {top_whale['order_type']} (${top_whale['formatted_premium']} at strike ${top_whale['strike_price']:.2f})."
            )

        context_str = "\n".join(bullets) if bullets else "No extraordinary outlier prints detected for the session."

        return f"""• **Notable Flow**:
Context:
{context_str}
Instructions:
- Call out any session print that ranks in the top 3 highest premiums ever recorded for that specific ticker (e.g. "**NVDA** $15.5M BUY_CALL recorded the 2nd highest premium to date for NVDA").
- Mention any aggressive deep OTM short-expiry tail-risk positioning (>=15% OTM, <=30 DTE).
- If no record-setting prints occurred, summarize the dominant institutional whale positioning.
- Tone: Punchy, quantitative, objective. Maximum 1-2 concise sentences. Bold all tickers, dollar premiums, and ranks."""

    def generate_deterministic(self, features: Dict[str, Any]) -> str:
        all_time_prints = features.get("top_all_time_prints", [])
        deep_otm = features.get("deep_otm_prints", [])
        top_whale = features.get("top_whale_print")

        parts = []
        if all_time_prints:
            p = all_time_prints[0]
            rank_suffix = {1: "1st", 2: "2nd", 3: "3rd"}.get(p["rank"], f"{p['rank']}th")
            parts.append(
                f"**{p['symbol']}** {p['order_type']} (**{p['formatted_premium']}**) ranked as the **{rank_suffix} highest premium to date** for {p['symbol']}"
            )
            if len(all_time_prints) > 1:
                p2 = all_time_prints[1]
                rank2_suffix = {1: "1st", 2: "2nd", 3: "3rd"}.get(p2["rank"], f"{p2['rank']}th")
                parts.append(f"while **{p2['symbol']}** logged its **{rank2_suffix}** largest print (**{p2['formatted_premium']}**)")
        
        if deep_otm:
            o = deep_otm[0]
            parts.append(
                f"with aggressive tail speculation in **{o['symbol']}** (**{o['otm_pct']:+.1f}% OTM**, **{o['dte']} DTE**, **{o['formatted_premium']}**)"
            )

        if not parts:
            if top_whale:
                parts.append(
                    f"Session volume was led by **{top_whale['symbol']}** {top_whale['order_type']} with **{top_whale['formatted_premium']}** at the **${top_whale['strike_price']:.2f}** strike"
                )
            else:
                parts.append("No extraordinary institutional flow outliers were detected in the latest session")

        statement = ", ".join(parts) + "."
        return f"• **Notable Flow**: {statement}"


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
Provide an ultra-short, highly digestible executive summary of institutional options flow from the latest completed market session ({latest_date}):

STRICT CONSTRAINTS:
1. NEVER GIVE TRADE ADVICE: Absolutely NEVER recommend trades, buy/sell actions, entry/exit targets, or financial advice. Provide purely objective quantitative flow analysis.
2. ADHD-FRIENDLY BREVITY: Output EXACTLY {len(self._points)} short, punchy bullet points under the heading below. Maximum 1-2 concise sentences per bullet. Bold key tickers, dollar amounts, and ranks. Zero fluff.

### Market Flow Snapshot
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
