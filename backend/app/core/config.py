from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(protected_namespaces=("model_",))
    app_name: str = "Theater Cast Scheduling"
    database_url: str = "mysql+pymysql://root:password@localhost:3306/theater_cast_scheduling"
    jwt_secret: str = "local-dev-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    settings_encryption_key: str | None = None
    settings_previous_encryption_keys: str = ""
    ai_provider_allowed_hosts: str = "api.openai.com"


settings = Settings()
