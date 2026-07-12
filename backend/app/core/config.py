from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Theater Cast Scheduling"
    database_url: str = "mysql+pymysql://root:password@localhost:3306/theater_cast_scheduling"
    jwt_secret: str = "local-dev-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480


settings = Settings()
