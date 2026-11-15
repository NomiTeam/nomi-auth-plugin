import asyncio
import ssl
from typing import Any

import httpx

from .config import Config
from .errors import BackendError
from .messages import ERROR_MESSAGES
from .queue import CommandQueue, QueueKey
from .tls import create_context, is_certificate_error

PATHS = {
    "登录": "/internal/v1/logins/verify",
    "注册": "/internal/v1/logins/register",
    "改名": "/internal/v1/profiles/rename",
}
STATUSES = {
    "登录": {"AWAITING_NAME", "VERIFIED"},
    "注册": {"REGISTERED"},
    "改名": {"RENAMED"},
}


class BackendUnavailable(Exception):
    pass


class AuthClient:
    """
    Submit authenticated group events with bounded waiting and safe retries.
    """

    def __init__(
        self, config: Config, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self.queue = CommandQueue()
        self.pending = 0
        self.http = httpx.AsyncClient(
            base_url=config.nomi_auth_base_url.rstrip("/"),
            headers={"Authorization": "Bearer " + config.nomi_bot_api_token},
            timeout=config.nomi_http_timeout,
            transport=transport,
            verify=create_context(config),
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def submit(
        self, operation: str, value: str, group: str, member: str, event_id: str
    ) -> dict[str, Any]:
        self._check_request(operation, group)
        payload = self._create_payload(operation, value, group, member, event_id)
        keys = self._queue_keys(operation, value, group, member)

        self.pending += 1
        try:
            # Include queue waiting and every HTTP retry in one overall deadline.
            return await asyncio.wait_for(
                self._send_ordered(operation, payload, keys),
                timeout=self.config.nomi_total_timeout,
            )
        except asyncio.TimeoutError:
            raise BackendError(
                "验证等待超时。请查看启动器状态，稍后使用同一码重试。"
            ) from None
        finally:
            self.pending -= 1

    def _check_request(self, operation: str, group: str) -> None:
        if not self.config.enabled or group != self.config.nomi_allowed_group_openid:
            raise BackendError("仅支持指定群。")
        if operation not in PATHS:
            raise BackendError("不支持的账号操作。")
        if self.pending >= 64:
            raise BackendError("当前验证请求较多，请稍后使用同一码重试。")

    def _create_payload(
        self, operation: str, value: str, group: str, member: str, event_id: str
    ) -> dict[str, str]:
        argument_field = "code" if operation == "登录" else "name"
        return {
            argument_field: value,
            "bot_app_id": self.config.nomi_bot_app_id,
            "group_openid": group,
            "member_openid": member,
            "event_id": event_id,
        }

    def _queue_keys(
        self, operation: str, value: str, group: str, member: str
    ) -> list[QueueKey]:
        keys: list[QueueKey] = [("member", group, member)]
        if operation == "登录":
            normalized_code = value.replace("-", "").strip().upper()
            keys.append(("code", normalized_code))
        return keys

    async def _send_ordered(
        self, operation: str, payload: dict[str, str], keys: list[QueueKey]
    ) -> dict[str, Any]:
        async with self.queue.wait(keys):
            return await self._send(operation, payload)

    async def _send(self, operation: str, payload: dict[str, str]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = await self.http.post(PATHS[operation], json=payload)
                if response.is_redirect:
                    raise BackendError("账号服务返回了重定向，请检查服务地址。")
                if response.status_code >= 500:
                    raise BackendUnavailable("Backend unavailable")

                return self._read_response(operation, response)
            except (
                httpx.TransportError,
                ssl.SSLError,
                BackendUnavailable,
                ValueError,
                TypeError,
            ) as error:
                if is_certificate_error(error):
                    raise BackendError(
                        "账号服务 TLS 验证失败，请联系管理员检查证书配置。"
                    ) from None
                if self.config.tls_configured and isinstance(
                    error, httpx.TransportError
                ):
                    raise BackendError(
                        "账号服务安全连接失败，请稍后重试或联系管理员。"
                    ) from None
                if attempt == 2:
                    raise BackendError(
                        "账号服务暂时不可用。请查看启动器状态，稍后使用同一码重试。"
                    ) from None
                await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError("Retry loop ended without a result")

    def _read_response(
        self, operation: str, response: httpx.Response
    ) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Invalid response shape")
        error_code = payload.get("code", "")
        if not isinstance(error_code, str):
            raise TypeError("Invalid response fields")

        if response.is_error or payload.get("status") == "FAILED":
            message = ERROR_MESSAGES.get(
                error_code, "验证失败，请检查配置或在启动器重试。"
            )
            raise BackendError(message)

        status = payload.get("status")
        if not isinstance(status, str) or status not in STATUSES[operation]:
            raise ValueError("Invalid response status")
        if status != "AWAITING_NAME":
            name = payload.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("Missing profile name")
        return payload
