"""Single-group, passwordless Nomi login, registration and profile naming."""

from nonebot import get_driver, get_plugin_config, logger, on_command, on_message
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupMessageCreateEvent
from nonebot.adapters.qq.message import Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from .client import AuthClient, BackendError
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Nomi 账号验证",
    description="群验证码登录，未注册成员在群内选择账号 ID",
    usage="登录 <验证码>；按提示注册 <id>；改名 <新id>",
    config=Config,
    supported_adapters={"~qq"},
)
config = get_plugin_config(Config)
backend = AuthClient(config)
get_driver().on_shutdown(backend.close)


async def allowed(bot: Bot, event: GroupMessageCreateEvent) -> bool:
    return (
        config.enabled
        and event.group_openid == config.nomi_allowed_group_openid
        and bot.self_id == config.nomi_bot_app_id
    )


login = on_command("登录", rule=allowed, priority=10, block=True)
register = on_command("注册", rule=allowed, priority=10, block=True)
rename = on_command("改名", rule=allowed, priority=10, block=True)


async def discovery_enabled(event: GroupMessageCreateEvent) -> bool:
    return (
        config.nomi_discovery
        and event.get_message().extract_plain_text().strip().lstrip("/") == "Nomi群信息"
    )


discovery = on_message(rule=discovery_enabled, priority=11, block=False)


@discovery.handle()
async def handle_discovery(bot: Bot, event: GroupMessageCreateEvent):
    logger.info(
        "Nomi discovery: bot_app_id={} group_openid={}", bot.self_id, event.group_openid
    )


async def process(operation, matcher, bot, event, argument):
    if not await allowed(bot, event):
        return
    value = argument.extract_plain_text().strip()
    if operation == "登录" and (
        not value or len(value) > 64 or len(value.split()) != 1
    ):
        await matcher.finish("用法：登录 <启动器显示的验证码>")
    if operation != "登录" and len(value) > 64:
        # Send a short invalid value to end a pending registration atomically.
        value = "!"
    try:
        result = await backend.submit(
            operation, value, event.group_openid, event.author.member_openid, event.id
        )
    except BackendError as error:
        await matcher.finish(str(error))
    if result["status"] == "AWAITING_NAME":
        await matcher.finish(
            "你还没有账号，请在验证码到期前发送：注册 <id>。"
            + "ID 为 3 至 16 位字母、数字或下划线；名称冲突会结束本次申请。"
        )
    verb = {"VERIFIED": "登录", "REGISTERED": "注册", "RENAMED": "改名"}[
        result["status"]
    ]
    suffix = "请重新登录启动器。" if operation == "改名" else "请查看启动器。"
    await matcher.finish(f"{verb}成功，账号 ID：{result['name']}。{suffix}")


@login.handle()
async def handle_login(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
):
    await process("登录", login, bot, event, argument)


@register.handle()
async def handle_register(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
):
    await process("注册", register, bot, event, argument)


@rename.handle()
async def handle_rename(
    bot: Bot, event: GroupMessageCreateEvent, argument: Message = CommandArg()
):
    await process("改名", rename, bot, event, argument)
