"""
gateway/app/core/synthesis.py
Extensible, Pluggable Synthesis Engine for Quant Cockpit Analysis.

Enforces:
1. Pluggable Architecture: Developers can register/unregister analytical points easily.
2. 3 Core Initial Points:
   - Regime & Volatility (Zero Gamma Flip level, current vol impact, and vol shift on flip)
   - Key Structural Walls (Call Wall overhead resistance & Put Wall downside support)
   - Institutional Flow Outliers (Top 3 all-time premiums on record, Deep OTM >=15% with DTE <=30)
3. Strict Constraints: ADHD-Brevity (1-2 punchy sentences per point), bold levels, zero trade advice.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("quant.gateway.synthesis")


class SynthesisPoint(ABC):
    """Abstract base class for a Cockpit Synergized Synthesis analytical point."""

    def __init__(self, point_id: str, title: str):
        self.point_id = point_id
        self.title = title

    @abstractmethod
    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts and computes point-specific quantitative features from the cockpit payload."""
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
    Analyzes dealer gamma regime, current volatility impact, the exact Zero Gamma Flip level,
    and how volatility dynamics shift when crossing the flip boundary.
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
        zero_flip = float(metrics.get("zero_gamma_flip") or gex.get("zero_gex_level") or gex.get("zero_gamma_flip") or spot)
        net_gex = float(metrics.get("net_gex") or gex.get("net_gex") or 0.0)
        regime = str(metrics.get("gamma_regime") or gex.get("gamma_regime") or "Neutral / Undefined")

        is_long_gamma = (spot >= zero_flip) if zero_flip > 0 else (net_gex >= 0)
        vol_impact = "dampened and suppressed" if is_long_gamma else "amplified and elevated"
        hedging_behavior = "buying dips and selling rips" if is_long_gamma else "selling declines and buying rallies"

        if is_long_gamma:
            flip_shift = f"A break below Zero Flip (${zero_flip:.2f}) flips dealers into Short Gamma, triggering volatility acceleration and wider trading ranges."
        else:
            flip_shift = f"Reclaiming above Zero Flip (${zero_flip:.2f}) flips dealers back into Long Gamma, immediately dampening volatility and restoring mean-reversion."

        return {
            "spot": spot,
            "zero_flip": zero_flip,
            "net_gex": net_gex,
            "regime": regime,
            "is_long_gamma": is_long_gamma,
            "vol_impact": vol_impact,
            "hedging_behavior": hedging_behavior,
            "flip_shift": flip_shift,
        }

    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        spot = features["spot"]
        zero_flip = features["zero_flip"]
        regime = features["regime"]
        vol_impact = features["vol_impact"]
        flip_shift = features["flip_shift"]

        return (
            f"• **{self.title}**: State that Spot (${spot:.2f}) is trading {'above' if features['is_long_gamma'] else 'below'} "
            f"the **Zero Gamma Flip level (${zero_flip:.2f})** in **{regime}**, explaining that realized volatility is **{vol_impact}**. "
            f"Explicitly note how volatility changes if gamma is flipped: {flip_shift} Keep to 1-2 punchy sentences."
        )

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        spot = features["spot"]
        zero_flip = features["zero_flip"]
        regime = features["regime"]
        vol_impact = features["vol_impact"]
        flip_shift = features["flip_shift"]

        return (
            f"• **{self.title}**: Spot (**${spot:.2f}**) trades {'above' if features['is_long_gamma'] else 'below'} "
            f"Zero Gamma Flip (**${zero_flip:.2f}**) in **{regime}**, keeping realized volatility **{vol_impact}**. {flip_shift}"
        )


class KeyStructuralWallsPoint(SynthesisPoint):
    """
    Identifies primary overhead resistance (Call Wall) and downside support (Put Wall),
    and evaluates current spot positioning inside the structural corridor.
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

        position_desc = "within the structural corridor"
        if call_wall > 0 and spot >= call_wall:
            position_desc = "testing upper Call Wall resistance"
        elif put_wall > 0 and spot <= put_wall:
            position_desc = "testing lower Put Wall support"

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
            f"• **{self.title}**: Detail the **Call Wall at ${cw:.2f}** as major overhead resistance/dealer supply ceiling "
            f"and the **Put Wall at ${pw:.2f}** as major structural downside support/floor. Note that spot is currently {pos}. "
            f"Strictly 1 sentence."
        )

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        cw = features["call_wall"]
        pw = features["put_wall"]
        pos = features["position_desc"]

        return (
            f"• **{self.title}**: **Call Wall at ${cw:.2f}** serves as primary overhead resistance, while "
            f"**Put Wall at ${pw:.2f}** anchors structural downside support with spot currently {pos}."
        )


class InstitutionalFlowOutliersPoint(SynthesisPoint):
    """
    Detects and surfaces extraordinary institutional options flow outliers:
    1. Prints entering the top 3 biggest premiums on record for this ticker.
    2. Deep OTM flows (>= 15% OTM) with short expiries (<= 30 DTE).
    3. Dominant whale print summary if no extreme tail anomaly is active.
    """

    def __init__(self):
        super().__init__(
            point_id="institutional_flow",
            title="Institutional Flow"
        )

    def extract_features(self, ticker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        metrics = payload.get("metrics", {})
        flow = payload.get("flow", {})
        records = flow.get("records", []) or []
        spot = float(metrics.get("spot_price") or 0.0)

        call_pct = float(metrics.get("call_pct", 0.0))
        put_pct = float(metrics.get("put_pct", 0.0))
        whale_count = int(metrics.get("whale_count", 0))
        confluence_bias = str(metrics.get("confluence_bias", "NEUTRAL PIN"))

        top_3_outliers = []
        deep_otm_outliers = []

        if records and spot > 0:
            # 1. Rank all entries for this ticker by premium descending
            sorted_by_premium = sorted(
                records,
                key=lambda r: float(r.get("PREMIUM") or 0.0),
                reverse=True
            )
            top_3_records = sorted_by_premium[:3]

            # Identify the most recent trade date in the records
            trade_dates = [str(r.get("TRADE_DATE", ""))[:10] for r in records if r.get("TRADE_DATE")]
            latest_date = max(trade_dates) if trade_dates else None

            # Scan for recent records that entered top 3 all-time
            for rank, r in enumerate(top_3_records, start=1):
                r_date = str(r.get("TRADE_DATE", ""))[:10]
                if r_date == latest_date:
                    prem = float(r.get("PREMIUM") or 0.0)
                    order_type = str(r.get("ORDER_TYPE", "")).replace("_", " ")
                    strike = r.get("STRIKE_PRICE", "N/A")
                    exp = str(r.get("EXPIRATION_DATE", ""))[:10]
                    top_3_outliers.append({
                        "rank": rank,
                        "date": r_date,
                        "premium": prem,
                        "order_type": order_type,
                        "strike": strike,
                        "expiry": exp,
                    })

            # 2. Scan for Deep OTM (>= 15%) with Short Expiry (<= 30 DTE)
            for r in records:
                try:
                    strike = float(r.get("STRIKE_PRICE") or 0.0)
                    if strike <= 0:
                        continue
                    order_type = str(r.get("ORDER_TYPE", "")).upper()
                    t_date_str = str(r.get("TRADE_DATE", ""))[:10]
                    exp_date_str = str(r.get("EXPIRATION_DATE", ""))[:10]
                    prem = float(r.get("PREMIUM") or 0.0)

                    if t_date_str and exp_date_str:
                        t_dt = datetime.strptime(t_date_str, "%Y-%m-%d")
                        exp_dt = datetime.strptime(exp_date_str, "%Y-%m-%d")
                        dte = (exp_dt - t_dt).days
                    else:
                        dte = 999

                    # Check DTE threshold <= 30
                    if 0 <= dte <= 30:
                        otm_pct = 0.0
                        if "CALL" in order_type and strike > spot:
                            otm_pct = ((strike - spot) / spot) * 100.0
                        elif "PUT" in order_type and strike < spot:
                            otm_pct = ((spot - strike) / spot) * 100.0

                        if otm_pct >= 15.0:
                            deep_otm_outliers.append({
                                "date": t_date_str,
                                "order_type": order_type.replace("_", " "),
                                "strike": strike,
                                "otm_pct": round(otm_pct, 1),
                                "dte": dte,
                                "expiry": exp_date_str,
                                "premium": prem,
                            })
                except Exception:
                    continue

        return {
            "call_pct": call_pct,
            "put_pct": put_pct,
            "whale_count": whale_count,
            "confluence_bias": confluence_bias,
            "top_3_outliers": top_3_outliers,
            "deep_otm_outliers": deep_otm_outliers,
            "has_records": bool(records),
        }

    def get_prompt_instruction(self, ticker: str, features: Dict[str, Any]) -> str:
        top_3 = features.get("top_3_outliers", [])
        deep_otm = features.get("deep_otm_outliers", [])
        call_pct = features.get("call_pct", 0.0)
        put_pct = features.get("put_pct", 0.0)
        whales = features.get("whale_count", 0)

        outlier_hints = []
        if top_3:
            t = top_3[0]
            outlier_hints.append(
                f"Recent print entered the #{t['rank']} all-time highest premium on record: "
                f"${t['premium']:,.0f} {t['order_type']} Strike ${t['strike']} Exp {t['expiry']}."
            )
        if deep_otm:
            d = sorted(deep_otm, key=lambda x: x["premium"], reverse=True)[0]
            outlier_hints.append(
                f"Extraordinary tail-risk outlier detected: Deep OTM {d['order_type']} Strike ${d['strike']} "
                f"(+{d['otm_pct']}% OTM) expiring in {d['dte']} days (${d['premium']:,.0f} premium)."
            )

        if outlier_hints:
            extraordinary_str = " Highlight these extraordinary outliers: " + " ".join(outlier_hints)
        else:
            extraordinary_str = (
                f" Highlight the 30-day directional flow split ({call_pct:.0f}% Calls vs {put_pct:.0f}% Puts) "
                f"and total whale activity ({whales} prints > $1M)."
            )

        return (
            f"• **{self.title}**: Point out recent extraordinary outliers in options flow.{extraordinary_str} "
            f"Keep to 1-2 punchy sentences."
        )

    def generate_deterministic(self, ticker: str, features: Dict[str, Any]) -> str:
        top_3 = features.get("top_3_outliers", [])
        deep_otm = features.get("deep_otm_outliers", [])
        call_pct = features.get("call_pct", 0.0)
        whales = features.get("whale_count", 0)

        if top_3:
            t = top_3[0]
            return (
                f"• **{self.title}**: Recent flow recorded an all-time outlier entering the **#{t['rank']} largest premium** "
                f"on record (**${t['premium']:,.0f} {t['order_type']}** at **${t['strike']}** strike exp {t['expiry']})."
            )
        elif deep_otm:
            d = sorted(deep_otm, key=lambda x: x["premium"], reverse=True)[0]
            return (
                f"• **{self.title}**: High-conviction asymmetric outlier detected: Deep OTM **${d['strike']} {d['order_type']}** "
                f"(**+{d['otm_pct']}% OTM**) expiring in **{d['dte']} days** with **${d['premium']:,.0f}** premium."
            )
        else:
            return (
                f"• **{self.title}**: Institutional flow exhibits **{call_pct:.0f}% Call volume** with "
                f"**{whales} whale prints** (> $1M), confirming steady order flow without anomalous tail-risk skew."
            )


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
• Call Wall (Major Resistance): ${metrics.get('call_wall', 0.0):.2f}
• Put Wall (Major Support): ${metrics.get('put_wall', 0.0):.2f}
• Net GEX: ${metrics.get('net_gex', 0.0):,.2f}
• Net DEX: ${metrics.get('net_dex', 0.0):,.2f}
• Gamma Regime: {metrics.get('gamma_regime', 'N/A')}
• Expected 1-Week Range: ${gex.get('expected_range_low', 'N/A')} to ${gex.get('expected_range_high', 'N/A')} (Expected Move: ${gex.get('expected_move_dollars', 'N/A')})

[30-DAY INSTITUTIONAL OPTIONS FLOW]
• Total Flow Volume: ${metrics.get('total_30d_flow_volume', 0.0):,.2f}
• Call Flow: ${metrics.get('call_flow', 0.0):,.2f} ({metrics.get('call_pct', 0.0):.1f}%) | Put Flow: ${metrics.get('put_flow', 0.0):,.2f} ({metrics.get('put_pct', 0.0):.1f}%)
• Whale Sweeps (> $1M): {metrics.get('whale_count', 0)} prints
• Unusual OI Alerts: {metrics.get('unusual_oi_count', 0)}
• Calculated Confluence Bias: {metrics.get('confluence_bias', 'NEUTRAL PIN')}

[HIGH-CONVICTION PRINTS]
{prints_block}

STRICT CONSTRAINTS:
1. NEVER GIVE TRADE ADVICE: Absolutely NEVER recommend trades, buy/sell actions, entry/exit targets, or financial advice. Provide purely objective quantitative data analysis.
2. ADHD-FRIENDLY BREVITY: Output EXACTLY {len(self._points)} short, punchy bullet points under the heading below. Maximum 1-2 concise sentences per bullet. Bold key numbers and levels. Zero fluff.

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
