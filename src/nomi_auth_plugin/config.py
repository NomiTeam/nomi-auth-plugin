from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    nomi_auth_base_url: str = "http://127.0.0.1:8000"
    nomi_bot_api_token: str = ""
    nomi_allowed_group_openid: str = ""
    nomi_bot_app_id: str = ""
    nomi_discovery: bool = False
    nomi_http_timeout: float = Field(default=8, gt=0, le=30)

    @property
    def enabled(self) -> bool:
        return len(self.nomi_bot_api_token) >= 32 and bool(
            self.nomi_allowed_group_openid and self.nomi_bot_app_id
        )
