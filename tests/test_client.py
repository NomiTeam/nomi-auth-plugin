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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,path,key",
    [
        ("登录", "/internal/v1/logins/verify", "code"),
        ("注册", "/internal/v1/logins/register", "name"),
        ("改名", "/internal/v1/profiles/rename", "name"),
    ],
)
async def test_operation_routing(operation, path, key):
    import json

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "VERIFIED", "name": "Alice"})

    config = Config(
        nomi_bot_api_token="x" * 32,
        nomi_allowed_group_openid="group",
        nomi_bot_app_id="app",
    )
    client = client_module.AuthClient(config, httpx.MockTransport(handler))
    try:
        await client.submit(operation, "value", "group", "member", "event")
        assert seen[0].url.path == path
        payload = json.loads(seen[0].content)
        assert payload[key] == "value" and payload["member_openid"] == "member"
        assert ("code" in payload) == (operation == "登录")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_conflict_closes_and_does_not_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "FAILED", "code": "NAME_TAKEN"})

    client = client_module.AuthClient(
        Config(
            nomi_bot_api_token="x" * 32,
            nomi_allowed_group_openid="group",
            nomi_bot_app_id="app",
        ),
        httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(client_module.BackendError, match="请求已关闭"):
            await client.submit("注册", "Alice", "group", "member", "event")
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,status,reply",
    [
        ("登录", "AWAITING_NAME", "注册 <id>"),
        ("登录", "VERIFIED", "登录成功，账号 ID：Alice"),
        ("注册", "REGISTERED", "注册成功，账号 ID：Alice"),
        ("改名", "RENAMED", "改名成功，账号 ID：Alice"),
    ],
)
async def test_plain_group_replies_include_account_id(
    monkeypatch, operation, status, reply
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from nonebot.adapters.qq.message import Message

    plugin = importlib.import_module("nomi_auth_plugin")
    monkeypatch.setattr(
        plugin.backend,
        "submit",
        AsyncMock(return_value={"status": status, "name": "Alice"}),
    )
    replies = []

    class Finished(Exception):
        pass

    class Matcher:
        async def finish(self, message):
            replies.append(str(message))
            raise Finished()

    event = SimpleNamespace(
        group_openid="group", author=SimpleNamespace(member_openid="member"), id="event"
    )
    with pytest.raises(Finished):
        await plugin.process(
            operation,
            Matcher(),
            SimpleNamespace(self_id="app"),
            event,
            Message("value"),
        )
    assert reply in replies[0] and "<@" not in replies[0]
