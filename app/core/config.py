from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./config_table.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT (must share the same SECRET_KEY as Service_Login so tokens are portable)
    secret_key: str = "change-this-secret-key-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Config Service (Key/Value ID validation)
    config_service_url: str = "http://config-service:8000"

    # Version Control Service (append-only key history)
    version_control_service_url: str = "http://version-control-service:18003"

    # App
    app_name: str = "Config Table Service"
    app_host_port: int = 18001
    debug: bool = False
    log_level: str = "INFO"

    # Security (reserved for future rate-limiting / lockout integration with Service_Login)
    max_login_attempts: int = 5
    lockout_duration_seconds: int = 900
    session_expire_seconds: int = 86400

    class Config:
        env_file = ".env"


settings = Settings()
