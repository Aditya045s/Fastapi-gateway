from pydantic.v1 import BaseSettings


class Settings(BaseSettings):

    processing_service_token: str

    database_url: str
    REDIS_URL: str

    class Config:
        env_file = ".env"


settings = Settings()