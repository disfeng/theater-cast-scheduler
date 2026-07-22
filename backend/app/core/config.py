from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        protected_namespaces=("model_",), env_file=".env", extra="ignore"
    )
    app_name: str = "Theater Cast Scheduling"
    app_env: str = "development"
    database_url: str = "mysql+pymysql://root:password@localhost:3306/theater_cast_scheduling"
    jwt_secret: str = "local-dev-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    settings_encryption_key: str | None = None
    settings_previous_encryption_keys: str = ""
    ai_provider_allowed_hosts: str = "api.openai.com"
    actor_portal_url: str = "http://localhost:7003/actor"
    cors_allowed_origins: str = "http://localhost:7003,http://127.0.0.1:7003"
    allow_demo_admin: bool = True
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    slow_query_threshold_ms: int = 500

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def validate_runtime_safety(self) -> None:
        if self.app_env.lower() != "production":
            return
        problems: list[str] = []
        if (
            self.jwt_secret == "local-dev-secret-change-before-production"
            or len(self.jwt_secret) < 32
        ):
            problems.append("JWT_SECRET must be a non-default secret of at least 32 characters")
        lowered_database = self.database_url.lower()
        if "root:password@" in lowered_database:
            problems.append("DATABASE_URL must not use example credentials")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("CORS_ALLOWED_ORIGINS must contain explicit origins")
        if self.allow_demo_admin:
            problems.append("ALLOW_DEMO_ADMIN must be false")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))


settings = Settings()
settings.validate_runtime_safety()
