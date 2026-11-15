from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Config(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    nomi_auth_base_url: str = "http://127.0.0.1:8000"
    nomi_bot_api_token: str = ""
    nomi_allowed_group_openid: str = ""
    nomi_bot_app_id: str = ""
    nomi_discovery: bool = False
    nomi_total_timeout: float = Field(default=15, gt=0, le=60)
    nomi_http_timeout: float = Field(default=8, gt=0, le=30)

    nomi_tls_client_cert: str = ""
    nomi_tls_client_key: str = ""
    nomi_tls_ca_cert: str = ""

    @model_validator(mode="after")
    def validate_tls(self) -> "Config":
        if bool(self.nomi_tls_client_cert) != bool(self.nomi_tls_client_key):
            raise ValueError(
                "TLS client certificate and key must be configured together"
            )
        if (
            any(
                (
                    self.nomi_tls_client_cert,
                    self.nomi_tls_client_key,
                    self.nomi_tls_ca_cert,
                )
            )
            and urlsplit(self.nomi_auth_base_url).scheme.lower() != "https"
        ):
            raise ValueError("TLS certificate configuration requires an HTTPS URL")
        return self

    @property
    def tls_configured(self) -> bool:
        return bool(self.nomi_tls_client_cert or self.nomi_tls_ca_cert)

    @property
    def enabled(self) -> bool:
        return len(self.nomi_bot_api_token) >= 32 and bool(
            self.nomi_allowed_group_openid and self.nomi_bot_app_id
        )
