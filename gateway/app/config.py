import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Security & Passcode / Session Auth
    APP_PASSCODE: str = os.getenv("APP_PASSCODE", "RichQuantDemo")
    SESSION_EXPIRY_HOURS: int = int(os.getenv("SESSION_EXPIRY_HOURS", "6"))
    SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", os.getenv("APP_PASSCODE", "RichQuantDemo"))
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_GEMINI_MODEL: str = os.getenv("DEFAULT_GEMINI_MODEL", "gemini-3.6-flash")
    
    # Model Candidate Hierarchy & Available Models
    AVAILABLE_MODELS: List[dict] = [
        {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash", "badge": "⚡ Low Latency (Default)"},
        {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "badge": "🚀 Instant"},
        {"id": "gemini-flash-latest", "name": "Gemini Flash Latest", "badge": "🛡️ Fallback"},
        {"id": "gemini-3.7-flash", "name": "Gemini 3.7 Flash", "badge": "✨ Preview"}
    ]
    
    # Synology Microservices Configuration
    GEXDEX_API_URL: str = os.getenv("GEXDEX_API_URL", "http://gexdex-api-prod:8000")
    GEXDEX_API_KEY: str = os.getenv("GEXDEX_API_KEY", "YOUR_SECRET_API_KEY_HERE")
    
    # Public Cloudflare / Ingress Base URL (for client-accessible images)
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")
    
    # Context & Memory
    MAX_SLIDING_WINDOW_MESSAGES: int = int(os.getenv("MAX_SLIDING_WINDOW_MESSAGES", "12"))
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["*"]

settings = Settings()
