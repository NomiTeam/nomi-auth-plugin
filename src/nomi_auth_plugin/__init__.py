"""Nomi QQ official-adapter plugin. Secrets are configured on the host instance."""

from nonebot import get_driver, get_plugin_config, logger, on_command, on_message
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
from nonebot.adapters.qq.message import Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .client import AuthClient, BackendError
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Nomi 账号验证",
    description="指定 QQ 群内的一次验证码注册与找回",
    usage="@机器人 注册 <码> 或 找回 <码>",
    config=Config,
    supported_adapters={"~qq"},
)

config = get_plugin_config(Config)
backend = AuthClient(config)
get_driver().on_shutdown(backend.close)


async def allowed(bot: Bot, event: GroupAtMessageCreateEvent) -> bool:
    return (
        config.enabled
        and event.group_openid == config.nomi_allowed_group_openid
        and bot.self_id == config.nomi_bot_app_id
    )


register = on_command("注册", rule=allowed, priority=10, block=True)
recover = on_command("找回", rule=allowed, priority=10, block=True)
help_command = on_command("账号帮助", rule=allowed, priority=10, block=True)


async def discovery_enabled(event: GroupAtMessageCreateEvent) -> bool:
    return (
        config.nomi_discovery
        and event.get_message().extract_plain_text().strip().lstrip("/") == "Nomi群信息"
    )


discovery = on_message(rule=discovery_enabled, priority=11, block=False)


@discovery.handle()
async def handle_discovery(bot: Bot, event: GroupAtMessageCreateEvent):
    # Explicit opt-in discovery writes only app/group identifiers to the local log.
    logger.info(
        "Nomi discovery: bot_app_id={} group_openid={}", bot.self_id, event.group_openid
    )


async def process(operation, matcher, bot, event, argument):
    if (
        event.group_openid != config.nomi_allowed_group_openid
        or bot.self_id != config.nomi_bot_app_id
    ):
        return
    code = argument.extract_plain_text().strip()
    if not code or len(code) > 64 or len(code.split()) != 1:
        await matcher.finish(f"用法：@机器人 {operation} <启动器显示的验证码>")
    try:
        await backend.submit(
            operation, code, event.group_openid, event.author.member_openid, event.id
        )
    except BackendError as error:
        await matcher.finish(str(error))
    await matcher.finish(
        "注册成功，请查看启动器。"
        if operation == "注册"
        else "身份已验证，请在启动器设置新密码。"
    )


@register.handle()
async def handle_register(
    bot: Bot, event: GroupAtMessageCreateEvent, argument: Message = CommandArg()
):
    await process("注册", register, bot, event, argument)


@recover.handle()
async def handle_recover(
    bot: Bot, event: GroupAtMessageCreateEvent, argument: Message = CommandArg()
):
    await process("找回", recover, bot, event, argument)


@help_command.handle()
async def handle_help(event: GroupAtMessageCreateEvent):
    if event.group_openid == config.nomi_allowed_group_openid:
        await help_command.finish(
            "在 Nomi 启动器申请后，@机器人 注册 <码>。已有账号可在启动器找回，再发送 找回 <码>。"
        )
