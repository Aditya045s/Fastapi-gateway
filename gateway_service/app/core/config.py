from pydantic.v1 import BaseSettings


class Settings(BaseSettings):
    processing_base_url: str
    processing_timeout_seconds: float = 5.0
    processing_service_token: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"

    class Config:
        env_file = ".env"


settings = Settings()