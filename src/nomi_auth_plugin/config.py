from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Config(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, hide_input_in_errors=True)
    nomi_auth_base_url: str = "http://127.0.0.1:8000"
    nomi_bot_api_token: str = ""
    nomi_allowed_group_openid: str = ""
    nomi_bot_app_id: str = ""
    nomi_discovery: bool = False
    nomi_total_timeout: float = Field(default=15, gt=0, le=60)
    nomi_http_timeout: float = Field(default=8, gt=0, le=30)

    nomi_tls_ca_cert: str = ""

    @model_validator(mode="after")
    def validate_connection(self) -> "Config":
        try:
            address = urlsplit(self.nomi_auth_base_url)
            _ = address.port
        except ValueError:
            raise ValueError("Invalid authentication service URL") from None
        if (
            address.scheme.lower() not in {"http", "https"}
            or not address.hostname
            or address.username is not None
            or address.password is not None
            or "?" in self.nomi_auth_base_url
            or "#" in self.nomi_auth_base_url
            or self.nomi_auth_base_url.strip() != self.nomi_auth_base_url
        ):
            raise ValueError(
                "Authentication service URL must use HTTP or HTTPS without credentials, query or fragment"
            )
        if self.nomi_bot_api_token and not all(
            33 <= ord(character) <= 126 for character in self.nomi_bot_api_token
        ):
            raise ValueError("Bot credentials must contain visible ASCII characters")
        if self.nomi_tls_ca_cert and address.scheme.lower() != "https":
            raise ValueError("TLS certificate configuration requires an HTTPS URL")
        return self

    @property
    def enabled(self) -> bool:
        return len(self.nomi_bot_api_token) >= 32 and bool(
            self.nomi_allowed_group_openid and self.nomi_bot_app_id
        )
