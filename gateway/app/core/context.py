from typing import List, Dict, Any
from app.config import settings

def apply_sliding_window(messages: List[Dict[str, Any]], max_messages: int = None) -> List[Dict[str, Any]]:
    """
    Trims the conversation history to the most recent N messages, ensuring the context
    stays lean, ultra-fast (<300ms latency), and well within token limits.
    """
    limit = max_messages or settings.MAX_SLIDING_WINDOW_MESSAGES
    if not messages:
        return []
    
    if len(messages) <= limit:
        return messages
    
    # Always keep the most recent `limit` messages
    return messages[-limit:]
