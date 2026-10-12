import importlib

import httpx
import nonebot
import pytest

nonebot.init(
    nomi_bot_api_token="x" * 32,
    nomi_allowed_group_openid="group",
    nomi_bot_app_id="app",
)
client_module = importlib.import_module("nomi_auth_plugin.client")
Config = importlib.import_module("nomi_auth_plugin.config").Config


@pytest.mark.asyncio
async def test_retry_preserves_event_and_payload():
    payloads = []

    def handler(request):
        payloads.append(request.content)
        return httpx.Response(
            503 if len(payloads) == 1 else 200, json={"status": "COMPLETED"}
        )

    client = client_module.AuthClient(
        Config(
            nomi_bot_api_token="x" * 32,
            nomi_allowed_group_openid="group",
            nomi_bot_app_id="app",
        ),
        httpx.MockTransport(handler),
    )
    try:
        result = await client.submit("注册", "ABCD", "group", "member", "event")
        assert result["status"] == "COMPLETED"
        assert len(payloads) == 2 and payloads[0] == payloads[1]
        with pytest.raises(client_module.BackendError):
            await client.submit("注册", "ABCD", "other", "member", "event")
        assert len(payloads) == 2
    finally:
        await client.close()
