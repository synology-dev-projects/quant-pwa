import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Security & Passcode
    APP_PASSCODE: str = os.getenv("APP_PASSCODE", "quant-secret-2026")
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_GEMINI_MODEL: str = os.getenv("DEFAULT_GEMINI_MODEL", "gemini-3.7-flash")
    
    # Synology Microservices Configuration
    GEXDEX_API_URL: str = os.getenv("GEXDEX_API_URL", "http://gexdex-api:8000")
    GEXDEX_API_KEY: str = os.getenv("GEXDEX_API_KEY", "YOUR_SECRET_API_KEY_HERE")
    
    # Public Cloudflare / Ingress Base URL (for client-accessible images)
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")
    
    # Context & Memory
    MAX_SLIDING_WINDOW_MESSAGES: int = int(os.getenv("MAX_SLIDING_WINDOW_MESSAGES", "12"))
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["*"]

settings = Settings()
