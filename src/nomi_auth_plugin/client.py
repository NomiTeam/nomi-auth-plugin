import asyncio

import httpx

from .config import Config


class BackendError(Exception):
    """Safe error for a group reply; never contains credentials or response bodies."""


MESSAGES = {
    "NO_PENDING_REGISTRATION": "没有待注册申请，请先发送启动器的登录码。",
    "REQUEST_IN_PROGRESS": "你已有待注册申请，请先完成或关闭启动器窗口。",
    "INVALID_NAME": "ID 须为 3 至 16 位字母、数字或下划线，本次请求已关闭。",
    "INVALID_REQUEST": "请求格式无效，请重新申请。",
    "RENAME_COOLDOWN": "尚在 7 天改名冷却期，本次请求已关闭。",
    "ACCOUNT_NOT_FOUND": "你在这个群内还没有账号，请先发送启动器的登录码。",
    "ACCOUNT_UNAVAILABLE": "该账号已停用，请联系管理员。",
    "IDENTITY_ALREADY_BOUND": "你在这个群内已有账号，请通过群验证码登录。",
    "INVALID_CODE": "验证码无效，请检查后重试。",
    "CODE_USED": "验证码已使用或申请已结束。",
    "REQUEST_EXPIRED": "验证码已过期，请在启动器重新申请。",
    "NAME_TAKEN": "ID 已被占用，本次请求已关闭，请重新申请。",
    "IDENTITY_MISMATCH": "必须使用该账号绑定的群成员身份登录。",
    "WRONG_GROUP": "当前群或机器人不在后端允许范围。",
    "RATE_LIMITED": "请求过于频繁，请稍后重试。",
}


class AuthClient:
    def __init__(self, config: Config, transport=None):
        self.config = config
        self.lock = asyncio.Lock()
        self.http = httpx.AsyncClient(
            base_url=config.nomi_auth_base_url.rstrip("/"),
            headers={"Authorization": "Bearer " + config.nomi_bot_api_token},
            timeout=config.nomi_http_timeout,
            transport=transport,
        )

    async def close(self):
        await self.http.aclose()

    async def submit(
        self, operation: str, code: str, group: str, member: str, event_id: str
    ):
        if not self.config.enabled or group != self.config.nomi_allowed_group_openid:
            raise BackendError("仅支持指定群。")
        payload = {
            ("code" if operation == "登录" else "name"): code,
            "bot_app_id": self.config.nomi_bot_app_id,
            "group_openid": group,
            "member_openid": member,
            "event_id": event_id,
        }
        path = {
            "登录": "/internal/v1/logins/verify",
            "注册": "/internal/v1/logins/register",
            "改名": "/internal/v1/profiles/rename",
        }[operation]
        # A single FIFO lock keeps submissions ordered, including retries.
        async with self.lock:
            for attempt in range(3):
                try:
                    response = await self.http.post(path, json=payload)
                    if response.status_code >= 500:
                        raise httpx.TransportError("backend unavailable")
                    data = response.json()
                    if response.is_error or data.get("status") == "FAILED":
                        raise BackendError(
                            MESSAGES.get(
                                data.get("code"), "验证失败，请检查配置或在启动器重试。"
                            )
                        )
                    return data
                except (httpx.TransportError, ValueError):
                    if attempt == 2:
                        raise BackendError(
                            "账号服务暂时不可用。请查看启动器状态，稍后使用同一码重试。"
                        )
                    await asyncio.sleep(0.5 * (attempt + 1))
