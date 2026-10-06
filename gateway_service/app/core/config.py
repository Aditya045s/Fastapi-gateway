# Source - https://stackoverflow.com/a/76753429
# Posted by Hasan Ramezani
# Retrieved 2026-10-05, License - CC BY-SA 4.0

from pydantic.v1 import BaseSettings



class Settings(BaseSettings):
    processing_base_url:str
    processing_timeout_seconds:float=5.0
    processing_service_token: str

    class Config:
        env_file=".env"

settings=Settings()
