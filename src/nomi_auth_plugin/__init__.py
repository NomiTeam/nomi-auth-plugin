"""
Register the QQ commands and connect their shared backend client.
"""

from nonebot import get_driver, get_plugin_config, logger, on_command, on_message
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.adapters.qq.message import Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .client import AuthClient
from .commands import Commands
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Nomi 账号验证",
    description="群验证码登录，未注册成员在群内选择账号 ID",
    usage="登录 验证码；按提示注册 ID；改名 新ID",
    config=Config,
    supported_adapters={"~qq"},
)
config = get_plugin_config(Config)
backend = AuthClient(config)
get_driver().on_shutdown(backend.close)
commands = Commands(config, backend)


login = on_command("登录", rule=commands.allowed, priority=10, block=True)
register = on_command("注册", rule=commands.allowed, priority=10, block=True)
rename = on_command("改名", rule=commands.allowed, priority=10, block=True)


async def discovery_enabled(event: GroupMessageCreateEvent) -> bool:
    return (
        config.nomi_discovery
        and event.get_message().extract_plain_text().strip().lstrip("/") == "Nomi群信息"
    )


discovery = on_message(rule=discovery_enabled, priority=11, block=False)


@discovery.handle()
async def handle_discovery(bot: Bot, event: GroupMessageCreateEvent) -> None:
    logger.info(
        "Nomi discovery: bot_app_id={} group_openid={}", bot.self_id, event.group_openid
    )


@login.handle()
async def handle_login(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
) -> None:
    await commands.process("登录", login, bot, event, argument)


@register.handle()
async def handle_register(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
) -> None:
    await commands.process("注册", register, bot, event, argument)


@rename.handle()
async def handle_rename(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
) -> None:
    await commands.process("改名", rename, bot, event, argument)
