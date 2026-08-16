from datetime import datetime, time
import pytz

NY_TZ = pytz.timezone("America/New_York")

def get_market_status(dt: datetime = None) -> dict:
    """
    Computes current US stock market state in America/New_York timezone.
    
    States:
      - REGULAR_HOURS: Mon-Fri 09:30 - 16:00 EDT
      - PRE_MARKET: Mon-Fri 04:00 - 09:30 EDT
      - AFTER_HOURS: Mon-Fri 16:00 - 20:00 EDT
      - WEEKEND_CLOSED: Friday 20:00 through Sunday 23:59 EDT
      - OVERNIGHT_CLOSED: Mon-Thu 20:00 - 04:00 EDT
    """
    if dt is None:
        dt = datetime.now(NY_TZ)
    elif dt.tzinfo is None:
        dt = NY_TZ.localize(dt)
    else:
        dt = dt.astimezone(NY_TZ)

    weekday = dt.weekday()  # 0 = Mon, 4 = Fri, 5 = Sat, 6 = Sun
    curr_time = dt.time()

    is_weekend = weekday in (5, 6) or (weekday == 4 and curr_time >= time(20, 0))

    if is_weekend:
        status_label = "WEEKEND_CLOSED"
        description = "Market is CLOSED for the weekend. Next open: Monday 9:30 AM EDT."
        is_live_trading = False
    elif time(9, 30) <= curr_time < time(16, 0):
        status_label = "REGULAR_HOURS"
        description = "US Markets are actively OPEN for regular session trading."
        is_live_trading = True
    elif time(4, 0) <= curr_time < time(9, 30):
        status_label = "PRE_MARKET"
        description = "US Pre-Market session active. Regular session opens at 9:30 AM EDT."
        is_live_trading = False
    elif time(16, 0) <= curr_time < time(20, 0):
        status_label = "AFTER_HOURS"
        description = "US Post-Market / After-Hours session active."
        is_live_trading = False
    else:
        status_label = "OVERNIGHT_CLOSED"
        description = "US Markets are CLOSED overnight. Pre-market starts at 4:00 AM EDT."
        is_live_trading = False

    formatted_time = dt.strftime("%A, %b %d, %Y - %I:%M %p %Z")
    
    return {
        "status": status_label,
        "is_live_trading": is_live_trading,
        "description": description,
        "current_time_ny": formatted_time,
        "iso_timestamp": dt.isoformat()
    }


def generate_temporal_system_prompt() -> str:
    """
    Generates a clear markdown block of temporal context for the LLM system instructions.
    """
    meta = get_market_status()
    return (
        f"[TEMPORAL & MARKET STATE CONTEXT]\n"
        f"Current Time (New York): {meta['current_time_ny']}\n"
        f"Market Session Status: {meta['status']} ({meta['description']})\n"
        f"Is Live Regular Trading: {'YES' if meta['is_live_trading'] else 'NO'}\n"
        f"Instruction: If market is closed, explicitly reference that options data reflects the most recent close snapshot.\n"
    )
