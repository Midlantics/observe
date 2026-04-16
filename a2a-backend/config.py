import os
from functools import lru_cache


class Settings:
    database_url: str
    supabase_jwt_secret: str
    allowed_origins: str
    nats_url: str

    def __init__(self) -> None:
        self.database_url = os.environ["DATABASE_URL"]
        self.supabase_jwt_secret = os.environ["SUPABASE_JWT_SECRET"]
        self.allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.vpc_mode = os.getenv("VPC_MODE", "false").lower() == "true"
        # Email / approval links
        self.approval_link_secret = os.getenv("APPROVAL_LINK_SECRET", "change-me-in-production")
        self.app_url = os.getenv("APP_URL", "https://a2a.midlantics.com")
        self.api_url = os.getenv("API_URL", "https://a2a-api.midlantics.com")
        # Supabase admin (to look up user emails for notifications)
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
