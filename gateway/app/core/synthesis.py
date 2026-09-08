"""
gateway/app/core/synthesis.py
Extensible, Pluggable Synthesis Engine for Institutional Options Market Microstructure.

Enforces:
1. Pluggable Architecture: Developers can register/unregister analytical points easily.
2. Initial Core Points:
   - Regime & Volatility: Spot vs Zero Flip and how volatility shifts when gamma flips.
   - Key Structural Walls: Call Wall as overhead resistance, Put Wall as downside support.
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
from app.core.flow_criteria import (
    extract_ticker_notable_flow,
    format_notable_flow_markdown,
    format_rank_suffix,
    format_dte_exp,
    format_currency
)

logger = logging.getLogger("quant.gateway.synthesis")


class SynthesisPoint(ABC):
    """Abstract base class for a Cockpit Synthesis analytical point."""

    def __init__(self, point_id: str, title: str):
        self.point_id = point_id
        self.title = title

    @abstractmethod
    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts and computes point-specific quantitative features from data payload."""
        pass

    @abstractmethod
    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        """Returns the specific prompt instruction and extracted metrics for the LLM."""
        pass

    @abstractmethod
    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        """Generates the bullet point deterministically for fallback / offline execution."""
        pass


class RegimeVolatilityPoint(SynthesisPoint):
    """
    Evaluates spot positioning relative to Zero Gamma Flip, detailing regime impact on volatility
    and the shift that occurs if gamma flips.
    """

    def __init__(self):
        super().__init__(
            point_id="regime_volatility",
            title="Regime & Volatility"
        )

    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        metrics = payload.get("metrics", {})
        gex = payload.get("gex", {})
        spot = float(metrics.get("spot_price") or gex.get("spot_price") or 0.0)
        zero_flip = float(metrics.get("zero_gamma_flip") or gex.get("zero_gex_level") or 0.0)

        is_long_gamma = spot >= zero_flip if zero_flip > 0 else True
        regime = "Positive Gamma (+GEX)" if is_long_gamma else "Negative Gamma (-GEX)"
        vol_impact = "compressed/mean-reverting" if is_long_gamma else "amplified/directional"

        if is_long_gamma:
            flip_shift = f"break below ${zero_flip:.2f} triggers heightened volatility."
        else:
            flip_shift = f"reclaim above ${zero_flip:.2f} restores volatility dampening."

        return {
            "spot": spot,
            "zero_flip": zero_flip,
            "is_long_gamma": is_long_gamma,
            "regime": regime,
            "vol_impact": vol_impact,
            "flip_shift": flip_shift,
        }

    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        spot = features["spot"]
        zero_flip = features["zero_flip"]
        regime = features["regime"]
        vol_impact = features["vol_impact"]
        flip_shift = features["flip_shift"]

        return (
            f"• **{self.title}**: Spot @ ${spot:.2f} {'above' if features['is_long_gamma'] else 'below'} "
            f"Zero Gamma Flip @ ${zero_flip:.2f} in {regime}. Volatility is {vol_impact}; flip {flip_shift} "
            f"TELEGRAPHIC, ZERO ADJECTIVES."
        )

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        spot = features["spot"]
        zero_flip = features["zero_flip"]
        regime = features["regime"]
        vol_impact = features["vol_impact"]
        flip_shift = features["flip_shift"]

        return (
            f"• **{self.title}**: Spot @ ${spot:.2f} {'above' if features['is_long_gamma'] else 'below'} "
            f"Zero Gamma Flip @ ${zero_flip:.2f} in {regime}. Volatility {vol_impact}; flip {flip_shift}"
        )


class KeyStructuralWallsPoint(SynthesisPoint):
    """
    Identifies overhead resistance (Call Wall) and downside support (Put Wall),
    and current spot positioning inside the structural corridor.
    """

    def __init__(self):
        super().__init__(
            point_id="key_structural_walls",
            title="Key Structural Walls"
        )

    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        metrics = payload.get("metrics", {})
        gex = payload.get("gex", {})
        spot = float(metrics.get("spot_price") or gex.get("spot_price") or 0.0)
        call_wall = float(metrics.get("call_wall") or gex.get("call_wall") or 0.0)
        put_wall = float(metrics.get("put_wall") or gex.get("put_wall") or 0.0)

        position_desc = "in corridor"
        if call_wall > 0 and spot >= call_wall:
            position_desc = "testing Call Wall resistance"
        elif put_wall > 0 and spot <= put_wall:
            position_desc = "testing Put Wall support"

        return {
            "spot": spot,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "position_desc": position_desc,
        }

    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        cw = features["call_wall"]
        pw = features["put_wall"]
        pos = features["position_desc"]

        return (
            f"• **{self.title}**: Call Wall @ ${cw:.2f} as overhead resistance, "
            f"Put Wall @ ${pw:.2f} as structural downside floor (spot @ ${features['spot']:.2f}, {pos}). "
            f"TELEGRAPHIC, ZERO ADJECTIVES."
        )

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        cw = features["call_wall"]
        pw = features["put_wall"]

        return (
            f"• **{self.title}**: Call Wall @ ${cw:.2f} as overhead resistance, "
            f"Put Wall @ ${pw:.2f} as structural downside floor."
        )


class InstitutionalFlowOutliersPoint(SynthesisPoint):
    """
    Standardized Notable Flow Point for Cockpit.
    Structures outliers into:
    • **Notable Flow**:
      • **TOP PREMIUM**:
        - TICKER $XX.XM PREMIUM (1st)
      • **NOTABLE OTM**:
        - TICKER XX% OTM exp 2 weeks
    With "- NONE FOUND" fallbacks.
    """

    def __init__(self):
        super().__init__(
            point_id="institutional_flow",
            title="Notable Flow"
        )

    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        metrics = payload.get("metrics", {})
        flow = payload.get("flow", {})
        records = flow.get("records", []) or []
        spot = float(metrics.get("spot_price") or 0.0)

        top_premium_prints, notable_otm_prints = extract_ticker_notable_flow(records, spot)

        return {
            "top_premium_prints": top_premium_prints,
            "notable_otm_prints": notable_otm_prints,
            "has_records": bool(records),
        }

    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        top_premium = features.get("top_premium_prints", [])
        notable_otm = features.get("notable_otm_prints", [])

        lines = [
            f"• **Notable Flow**:",
            f"  • **TOP PREMIUM**:"
        ]
        if top_premium:
            for p in top_premium:
                rank_str = format_rank_suffix(p.get("rank", 1))
                lines.append(f"    - {ticker} {p.get('formatted_premium')} PREMIUM ({rank_str})")
        else:
            lines.append("    - NONE FOUND")

        lines.append("  • **NOTABLE OTM**:")
        if notable_otm:
            for o in notable_otm:
                exp_str = format_dte_exp(o.get("dte", 0))
                lines.append(f"    - {ticker} {o.get('otm_pct', 0):.0f}% OTM {exp_str}")
        else:
            lines.append("    - NONE FOUND")

        lines.append("TELEGRAPHIC, ZERO ADJECTIVES.")
        return "\n".join(lines)

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        top_premium = features.get("top_premium_prints", [])
        notable_otm = features.get("notable_otm_prints", [])
        return format_notable_flow_markdown(top_premium, notable_otm)


class SynthesisRegistry:
    """
    Registry managing Cockpit Synergized Synthesis points.
    Enables adding/removing analytical points modularly without modifying router code.
    """

    def __init__(self, points: Optional[List[SynthesisPoint]] = None):
        self._points: List[SynthesisPoint] = points or [
            RegimeVolatilityPoint(),
            KeyStructuralWallsPoint(),
            InstitutionalFlowOutliersPoint(),
        ]

    @property
    def points(self) -> List[SynthesisPoint]:
        return list(self._points)

    def register(self, point: SynthesisPoint) -> None:
        """Register a new synthesis point."""
        self.unregister(point.point_id)
        self._points.append(point)
        logger.info(f"Registered new synthesis point: {point.point_id} ('{point.title}')")

    def unregister(self, point_id: str) -> bool:
        """Unregister a synthesis point by ID."""
        initial_len = len(self._points)
        self._points = [p for p in self._points if p.point_id != point_id]
        return len(self._points) < initial_len

    def build_synthesis_prompt(self, ticker: str, payload: Dict[str, Any]) -> str:
        """Constructs prompt for Gemini across all registered synthesis points."""
        metrics = payload.get("metrics", {})
        gex = payload.get("gex", {})
        flow = payload.get("flow", {})
        records = flow.get("records", []) or []

        # High conviction prints block
        top_prints = []
        if records:
            sorted_records = sorted(records, key=lambda r: float(r.get("PREMIUM") or 0.0), reverse=True)[:5]
            for r in sorted_records:
                t_date = str(r.get("TRADE_DATE", ""))[:10]
                prem = float(r.get("PREMIUM") or 0.0)
                order_type = str(r.get("ORDER_TYPE", "")).replace("_", " ")
                strike = r.get("STRIKE_PRICE", "N/A")
                exp = str(r.get("EXPIRATION_DATE", ""))[:10]
                oi = r.get("OPEN_INTEREST", 0)
                unusual = " ⚠️" if r.get("IS_UNUSUAL_OI") in (1, True, "1") else ""
                top_prints.append(f"  • {t_date}: ${prem:,.0f} {order_type} | Strike: ${strike} | Exp: {exp} | OI: {oi}{unusual}")

        prints_block = "\n".join(top_prints) if top_prints else "  • No major institutional whale prints recorded."

        # Collect instructions from each registered point
        point_instructions = []
        for point in self._points:
            features = point.extract_features(ticker, payload)
            point_instructions.append(point.get_prompt_instruction(ticker, features))

        instructions_block = "\n".join(point_instructions)

        return f"""You are Quant AI's Quantitative Market Microstructure Analyst.
Provide an ultra-short, highly digestible analysis of the following options microstructure and flow data for {ticker}:

[OPTIONS MICROSTRUCTURE (GEX/DEX)]
• Spot Price: ${metrics.get('spot_price', 0.0):.2f}
• Zero Gamma Flip: ${metrics.get('zero_gamma_flip', 0.0):.2f}
• Call Wall (Resistance): ${metrics.get('call_wall', 0.0):.2f}
• Put Wall (Support): ${metrics.get('put_wall', 0.0):.2f}
• Net GEX: ${metrics.get('net_gex', 0.0):,.2f}
• Net DEX: ${metrics.get('net_dex', 0.0):,.2f}
• Gamma Regime: {metrics.get('gamma_regime', 'N/A')}

[HIGH-CONVICTION PRINTS]
{prints_block}

STRICT CONSTRAINTS:
1. NEVER GIVE TRADE ADVICE: Absolutely NEVER recommend trades, buy/sell actions, entry/exit targets, or financial advice. Provide purely objective quantitative data analysis.
2. TELEGRAPHIC / ZERO ADJECTIVES: Never use descriptive or subjective adjectives (no 'heavy', 'primary', 'massive', 'aggressive', 'significant', 'strong', 'critical'). Write in concise telegraphic bullet-form, strictly stating levels, prices, and functional roles (e.g. 'Call Wall @ $210 as overhead resistance, Put Wall @ $200 as structural downside floor').
3. ADHD-FRIENDLY BREVITY: Output EXACTLY {len(self._points)} points under the heading below. Zero fluff.
4. PRESERVE NOTABLE FLOW SUB-BULLETS: For '• **Notable Flow**:', you MUST strictly keep the sub-headings '• **TOP PREMIUM**:' and '• **NOTABLE OTM**:' with indented hyphens ('    - '). Never collapse or rewrite them into prose.

### Microstructure Snapshot
{instructions_block}
"""

    def generate_deterministic_synthesis(self, ticker: str, payload: Dict[str, Any]) -> str:
        """Fallback deterministic synthesis generator when Gemini API is offline or unconfigured."""
        lines = ["### Microstructure Snapshot"]
        for point in self._points:
            features = point.extract_features(ticker, payload)
            lines.append(point.generate_deterministic(ticker, features))
        return "\n".join(lines) + "\n"


# Global singleton registry instance
synthesis_registry = SynthesisRegistry()
