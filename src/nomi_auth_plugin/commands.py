from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.adapters.qq.message import Message
from nonebot.matcher import Matcher

from .client import AuthClient
from .config import Config
from .errors import BackendError
from .messages import LOGIN_USAGE, REGISTRATION_PROMPT, success_reply


class Commands:
    """
    Validate group commands and delegate account operations to the backend client.
    """

    def __init__(self, config: Config, client: AuthClient) -> None:
        self.config = config
        self.client = client

    async def allowed(self, bot: Bot, event: GroupMessageCreateEvent) -> bool:
        return (
            self.config.enabled
            and event.group_openid == self.config.nomi_allowed_group_openid
            and bot.self_id == self.config.nomi_bot_app_id
        )

    async def process(
        self,
        operation: str,
        matcher: type[Matcher],
        bot: Bot,
        event: GroupMessageCreateEvent,
        argument: Message,
    ) -> None:
        if not await self.allowed(bot, event):
            return

        value = argument.extract_plain_text().strip()
        if operation == "登录" and not self._valid_code_argument(value):
            await matcher.finish(LOGIN_USAGE)
        if operation != "登录" and len(value) > 64:
            # Let the backend end an invalid registration in the same transaction.
            value = "!"

        try:
            result = await self.client.submit(
                operation,
                value,
                event.group_openid,
                event.author.member_openid,
                event.id,
            )
        except BackendError as error:
            await matcher.finish(str(error))

        if result["status"] == "AWAITING_NAME":
            await matcher.finish(REGISTRATION_PROMPT)

        reply = success_reply(operation, result["status"], result["name"])
        await matcher.finish(reply)

    def _valid_code_argument(self, value: str) -> bool:
        return bool(value) and len(value) <= 64 and len(value.split()) == 1
