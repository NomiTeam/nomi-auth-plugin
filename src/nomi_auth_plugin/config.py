from pydantic import BaseModel, Field


class Config(BaseModel):
    nomi_auth_base_url: str = "http://127.0.0.1:8000"
    nomi_bot_api_token: str = Field(min_length=32)
    nomi_allowed_group_openid: str = Field(min_length=1)
    nomi_bot_app_id: str = Field(min_length=1)
    nomi_http_timeout: float = Field(default=8, gt=0, le=30)
