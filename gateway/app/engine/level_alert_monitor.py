import os
import asyncio
import collections
import logging
import math
import time
from datetime import datetime, date, time as dt_time
from typing import Dict, List, Any, Optional
from zoneinfo import ZoneInfo
import pandas as pd

logger = logging.getLogger("quant.gateway.level_alert_monitor")
NY_TZ = ZoneInfo("America/New_York")


class LevelAlertMonitor:
    """
    Real-time SPX Quant Buy/Sell Level Proximity Alert Engine.
    Monitors live SPX spot price against active Buy/Sell levels from PostgreSQL quant_lvl_data_te.
    Fires high-priority push notifications via NTFY and records recent alerts when spot is within
    +/- 1.50 points of a level, enforcing a 15-minute anti-spam cooldown per level.
    """

    def __init__(self):
        self.recent_alerts = collections.deque(maxlen=100)
        self.cooldown_map: Dict[float, float] = {}
        self.level_type_map: Dict[float, str] = {}
        self.active: bool = False
        self.last_check_time: Optional[datetime] = None
        self.last_spot_price: Optional[float] = None
        self.monitored_levels_count: int = 0

    def start(self) -> None:
        self.active = True
        logger.info("SPX Level Alert Monitor started (ACTIVE).")

    def stop(self) -> None:
        self.active = False
        logger.info("SPX Level Alert Monitor stopped (INACTIVE).")

    def is_market_hours(self, dt: Optional[datetime] = None) -> bool:
        """
        Checks Eastern Time regular trading hours: Monday (0) to Friday (4), 09:30 to 16:15 ET.
        """
        if dt is None:
            dt = datetime.now(NY_TZ)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=NY_TZ)
        else:
            dt = dt.astimezone(NY_TZ)

        # 0 = Monday, ..., 4 = Friday, 5 = Saturday, 6 = Sunday
        if dt.weekday() > 4:
            return False

        t = dt.time()
        return dt_time(9, 30) <= t <= dt_time(16, 15)

    def dispatch_ntfy_alert(self, alert: Dict[str, Any]) -> bool:
        """
        Dispatches high-urgency push notification via NTFY.
        Endpoint: https://richntfynotifier.synology.me
        Topic: spx_alerts
        Priority: 4 (High urgency, vibrate + sound)
        Tags: 'chart_with_upwards_trend,bell'
        """
        endpoint = os.getenv("NTFY_ENDPOINT", "https://richntfynotifier.synology.me")
        raw_topics = os.getenv("SPX_ALERT_NTFY_TOPICS", "quant_alerts,spx_alerts")
        topics = [t.strip() for t in raw_topics.split(",") if t.strip()]
        if not topics:
            topics = ["quant_alerts", "spx_alerts"]
        priority = int(os.getenv("SPX_ALERT_NTFY_PRIORITY", "5"))
        tags = "chart_with_upwards_trend,bell"

        lvl_type = alert.get("level_type", "LEVEL")
        lvl_price = alert.get("level_price", 0.0)
        lvl_range = alert.get("level_price_range")
        touched = alert.get("touched_boundary")
        spot = alert.get("current_spot", 0.0)
        dist = alert.get("distance_pts", 0.0)
        comments = alert.get("comments") or "N/A"
        timestamp = alert.get("timestamp", "")

        if lvl_range and touched is not None:
            title = f"SPX Level Hit: {lvl_type} @ {lvl_range} (Touched {touched:.2f})"
            message = (
                f"SPX Spot: {spot:.2f} ({dist:+.2f} pts away)\n"
                f"Type: {lvl_type} Range ({lvl_range})\n"
                f"Boundary: Touched {touched:.2f}\n"
                f"Time: {timestamp}\n"
                f"Comment: {comments}"
            )
        else:
            title = f"SPX Level Hit: {lvl_type} @ {lvl_price:.2f}"
            message = (
                f"SPX Spot: {spot:.2f} ({dist:+.2f} pts away)\n"
                f"Type: {lvl_type} Level ({lvl_price:.2f})\n"
                f"Time: {timestamp}\n"
                f"Comment: {comments}"
            )

        try:
            from common_lib.connectors.nfty import send_ntfy_notification
            success = False
            for t in topics:
                try:
                    send_ntfy_notification(
                        endpoint=endpoint,
                        topic=t,
                        title=title,
                        message=message,
                        priority=priority,
                        tags=tags,
                        timeout=5
                    )
                    logger.info(f"Dispatched NTFY push alert for SPX level {title} to topic '{t}'.")
                    success = True
                except Exception as sub_ex:
                    logger.warning(f"Failed dispatching to NTFY topic '{t}': {sub_ex}")
            return success
        except Exception as ex:
            logger.warning(f"Failed to dispatch NTFY alert for SPX level {lvl_price:.2f}: {ex}")
            return False

    async def check_proximity(self, spot: float, levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Evaluates spot price against active levels.
        Proximity condition: |spot - level_price| <= 1.50 points.
        Supports range levels: (start_lvl_price - 1.50) <= spot <= (end_lvl_price + 1.50).
        Enforces 15-minute (900s) cooldown per level price.
        Returns newly triggered alerts.
        """
        triggered_alerts: List[Dict[str, Any]] = []
        now_epoch = time.time()
        now_ny = datetime.now(NY_TZ)

        for lvl in levels:
            try:
                raw_start = lvl.get("start_lvl_price") if "start_lvl_price" in lvl else lvl.get("START_LVL_PRICE")
                if raw_start is None or (isinstance(raw_start, float) and math.isnan(raw_start)):
                    continue

                start_price = float(raw_start)
                if start_price < 2500.0:
                    continue

                lvl_price = round(start_price, 2)
                raw_end = lvl.get("end_lvl_price") if "end_lvl_price" in lvl else lvl.get("END_LVL_PRICE")
                
                has_range = False
                end_price = None
                if raw_end is not None and not (isinstance(raw_end, float) and math.isnan(raw_end)):
                    try:
                        end_val = float(raw_end)
                        if end_val > 0 and end_val != start_price:
                            has_range = True
                            end_price = end_val
                    except (ValueError, TypeError):
                        has_range = False

                if has_range and end_price is not None:
                    lower = min(start_price, end_price)
                    upper = max(start_price, end_price)
                    is_hit = (lower - 1.50) <= spot <= (upper + 1.50)
                    if spot < lower:
                        dist = round(spot - lower, 2)
                    elif spot > upper:
                        dist = round(spot - upper, 2)
                    else:
                        dist = 0.0

                    # Determine which boundary was touched / entered
                    if abs(spot - upper) <= abs(spot - lower):
                        touched_boundary = round(upper, 2)
                    else:
                        touched_boundary = round(lower, 2)
                    cooldown_key = touched_boundary
                    level_price_range = f"{lower:.2f} - {upper:.2f}"
                else:
                    dist = round(spot - lvl_price, 2)
                    is_hit = abs(dist) <= 1.50
                    touched_boundary = lvl_price
                    cooldown_key = lvl_price
                    level_price_range = None

                if not is_hit:
                    continue

                # Check 15-minute cooldown (900 seconds) on the specific boundary touched
                last_alert_ts = self.cooldown_map.get(cooldown_key, 0.0)
                if now_epoch - last_alert_ts < 900.0:
                    continue

                # Level hit and cooldown expired!
                raw_type = lvl.get("buy_sell_ind") or lvl.get("BUY_SELL_IND") or lvl.get("level_type") or "BUY"
                level_type = str(raw_type).strip().upper()
                if level_type not in ("BUY", "SELL"):
                    level_type = "BUY"

                raw_comments = lvl.get("comments") if "comments" in lvl else lvl.get("COMMENTS")
                comments = str(raw_comments).strip() if raw_comments is not None and not pd.isna(raw_comments) and str(raw_comments).lower() not in ("none", "nan") else None

                session_date = lvl.get("session_date") or lvl.get("SESSION_DATE")
                if not session_date and lvl.get("datetime"):
                    session_date = str(lvl["datetime"]).split()[0]
                if not session_date:
                    session_date = now_ny.strftime("%Y-%m-%d")

                alert_id = f"alt-spx-{int(cooldown_key)}-{int(now_epoch)}"
                alert = {
                    "id": alert_id,
                    "ticker": "SPX",
                    "level_price": lvl_price,
                    "level_type": level_type,
                    "current_spot": round(float(spot), 2),
                    "distance_pts": dist,
                    "comments": comments,
                    "timestamp": now_ny.isoformat(),
                    "session_date": session_date,
                    "level_price_range": level_price_range,
                    "touched_boundary": touched_boundary,
                }

                # Update cooldown and tracking
                self.cooldown_map[cooldown_key] = now_epoch
                self.level_type_map[cooldown_key] = level_type
                self.recent_alerts.append(alert)
                self.dispatch_ntfy_alert(alert)
                triggered_alerts.append(alert)

            except Exception as ex:
                logger.warning(f"Error evaluating level proximity for level {lvl}: {ex}")
                continue

        return triggered_alerts

    def fetch_active_spx_levels(self) -> List[Dict[str, Any]]:
        """
        Fetches active SPX levels from PostgreSQL quant_lvl_data_te for the latest session.
        Filters for buy_sell_ind IN ('BUY', 'SELL') and start_lvl_price >= 2500.0.
        """
        try:
            from common_lib.config.main_config import load_config
            from common_lib.connectors import postgres
            config = load_config()
            query = """
                SELECT datetime, ticker, start_lvl_price, end_lvl_price, comments, buy_sell_ind, web_link
                FROM quant_lvl_data_te
                WHERE ticker = 'SPX'
                  AND UPPER(buy_sell_ind) IN ('BUY', 'SELL')
                  AND start_lvl_price >= 2500.0
                  AND datetime::date = (
                      SELECT MAX(datetime::date)
                      FROM quant_lvl_data_te
                      WHERE ticker = 'SPX' AND start_lvl_price >= 2500.0
                  )
                ORDER BY start_lvl_price ASC;
            """
            df = postgres.sql(config, query)
            if df is None or df.empty:
                return []

            records = []
            for _, row in df.iterrows():
                item = {str(k).lower(): v for k, v in row.items()}
                start_price = float(item["start_lvl_price"]) if item.get("start_lvl_price") is not None else None
                if start_price is None:
                    continue
                end_price = float(item["end_lvl_price"]) if item.get("end_lvl_price") is not None and not pd.isna(item["end_lvl_price"]) else None
                raw_c = item.get("comments")
                comments = str(raw_c).strip() if raw_c is not None and not pd.isna(raw_c) and str(raw_c).lower() not in ("none", "nan") else None
                buy_sell = str(item.get("buy_sell_ind", "")).strip().upper()
                dt_val = item.get("datetime")
                session_d = str(dt_val).split()[0] if dt_val is not None else None
                records.append({
                    "ticker": "SPX",
                    "start_lvl_price": start_price,
                    "end_lvl_price": end_price,
                    "buy_sell_ind": buy_sell,
                    "comments": comments,
                    "session_date": session_d,
                    "datetime": dt_val,
                })
            return records
        except Exception as ex:
            logger.warning(f"Error fetching active SPX levels from PostgreSQL: {ex}")
            return []

    async def get_spx_spot_price(self) -> Optional[float]:
        """
        Resolves live SPX spot price using quote_feed with cache and timeout.
        """
        try:
            from app.core.quote_feed import get_batch_quotes
            quotes = await get_batch_quotes(["^GSPC", "SPX"])
            for sym in ["^GSPC", "SPX"]:
                if sym in quotes and quotes[sym].get("price"):
                    return float(quotes[sym]["price"])
        except Exception as ex:
            logger.warning(f"Error fetching SPX spot price: {ex}")
        return None

    async def run_loop(self) -> None:
        """
        Core async background monitoring loop.
        Runs while self.active is True:
          - 20s interval during ET market hours, 60s outside.
          - Evaluates proximity, evicts 24h+ stale cooldowns.
        """
        logger.info("Starting SPX Level Alert Monitor background loop...")
        while self.active:
            interval = 60
            try:
                in_market = self.is_market_hours()
                interval = 20 if in_market else 60

                spot = await self.get_spx_spot_price()
                levels = self.fetch_active_spx_levels()

                if spot is not None:
                    self.last_spot_price = spot
                    self.monitored_levels_count = len(levels)
                    self.last_check_time = datetime.now(NY_TZ)
                    if levels:
                        await self.check_proximity(spot, levels)

                # Evict cooldowns older than 24 hours (86400s)
                now_epoch = time.time()
                expired = [k for k, ts in self.cooldown_map.items() if now_epoch - ts >= 86400]
                for k in expired:
                    self.cooldown_map.pop(k, None)
                    self.level_type_map.pop(k, None)

            except asyncio.CancelledError:
                logger.info("SPX Level Alert Monitor loop cancelled.")
                break
            except Exception as ex:
                logger.error(f"Unexpected error in SPX Level Alert Monitor loop: {ex}", exc_info=True)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("SPX Level Alert Monitor loop cancelled during sleep.")
                break

    def get_status(self) -> Dict[str, Any]:
        """
        Returns monitor diagnostics, market session, pending cooldowns.
        """
        now_ny = datetime.now(NY_TZ)
        in_market = self.is_market_hours(now_ny)
        now_epoch = time.time()

        pending_cooldowns = []
        for lvl_price, ts in list(self.cooldown_map.items()):
            elapsed = now_epoch - ts
            remaining = int(900 - elapsed)
            if remaining > 0:
                dt_triggered = datetime.fromtimestamp(ts, tz=NY_TZ)
                pending_cooldowns.append({
                    "level_price": lvl_price,
                    "level_type": self.level_type_map.get(lvl_price, "ALERT"),
                    "cooldown_remaining_sec": remaining,
                    "triggered_at": dt_triggered.isoformat()
                })

        pending_cooldowns.sort(key=lambda x: x["cooldown_remaining_sec"], reverse=True)

        return {
            "active": self.active,
            "is_market_hours": in_market,
            "market_session": "REGULAR_HOURS" if in_market else "CLOSED",
            "last_check_timestamp": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_spot_price": self.last_spot_price,
            "monitored_levels_count": self.monitored_levels_count,
            "active_cooldowns_count": len(pending_cooldowns),
            "pending_cooldowns": pending_cooldowns,
        }

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns recent alerts newest first.
        """
        alerts_list = list(self.recent_alerts)
        alerts_list.reverse()
        return alerts_list[:limit]

    def trigger_test_alert(
        self,
        test_spot: float = 6020.85,
        test_level: float = 6020.00,
        level_type: str = "BUY",
        comments: str = "Synthetic test alert triggered via REST API",
        level_price_range: Optional[str] = None,
        touched_boundary: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generates and dispatches a synthetic alert for testing & verification.
        """
        now_ny = datetime.now(NY_TZ)
        now_epoch = time.time()
        lvl_price = round(float(test_level), 2)
        spot = round(float(test_spot), 2)
        dist = round(spot - lvl_price, 2)
        clean_type = level_type.strip().upper() if level_type else "BUY"
        cooldown_key = touched_boundary if touched_boundary is not None else lvl_price

        alert = {
            "id": f"alt-spx-{int(cooldown_key)}-{int(now_epoch)}",
            "ticker": "SPX",
            "level_price": lvl_price,
            "level_type": clean_type,
            "current_spot": spot,
            "distance_pts": dist,
            "comments": comments or "Synthetic test alert triggered via REST API",
            "timestamp": now_ny.isoformat(),
            "session_date": now_ny.strftime("%Y-%m-%d"),
            "level_price_range": level_price_range,
            "touched_boundary": touched_boundary if touched_boundary is not None else lvl_price,
        }

        self.recent_alerts.append(alert)
        self.cooldown_map[cooldown_key] = now_epoch
        self.level_type_map[cooldown_key] = clean_type
        self.dispatch_ntfy_alert(alert)
        return alert


# Global singleton
level_alert_monitor = LevelAlertMonitor()
