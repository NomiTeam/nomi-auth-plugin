import os

import httpx
import nonebot
import pytest

# Install the sibling auth project explicitly when running cross-project tests.
auth_app = pytest.importorskip("nomi_auth.app")

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()

from nomi_auth.config import Settings
from nomi_auth.transfer import TABLES

from nomi_auth_plugin.client import AuthClient, BackendError
from nomi_auth_plugin.config import Config


@pytest.fixture(params=["sqlite", "mysql"])
def service(request, tmp_path):
    settings = Settings(
        data_dir=tmp_path, bot_token="x" * 32, bot_app_id="app", group_openid="group"
    )
    if request.param == "mysql":
        database_name = os.environ.get("NOMI_TEST_MYSQL_DATABASE", "")
        if not database_name:
            pytest.skip("A separate MariaDB test database was not configured")
        if not database_name.startswith("nomi_auth_test_"):
            pytest.fail("Refusing to clear a database outside the test namespace")
        settings = settings.model_copy(
            update={
                "database_backend": "mysql",
                "mysql_database": database_name,
                "mysql_user": os.environ["NOMI_TEST_MYSQL_USER"],
                "mysql_port": int(os.environ.get("NOMI_TEST_MYSQL_PORT", "3306")),
            }
        )
        # SecretStr conversion must run through settings validation.
        settings = Settings(
            **{
                **settings.model_dump(),
                "mysql_password": os.environ["NOMI_TEST_MYSQL_PASSWORD"],
            }
        )
    app = auth_app.create_app(settings)
    with app.state.db.write() as connection:
        for table in reversed(TABLES):
            if table != "schema_versions":
                connection.execute(f"DELETE FROM {table}")
    return app


def backend_client(service):
    config = Config(
        nomi_auth_base_url="http://auth.test",
        nomi_bot_api_token="x" * 32,
        nomi_allowed_group_openid="group",
        nomi_bot_app_id="app",
    )
    return AuthClient(config, transport=httpx.ASGITransport(app=service))


@pytest.mark.asyncio
async def test_group_registration_login_rename_and_game_join(service):
    backend = backend_client(service)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service), base_url="http://auth.test"
        ) as launcher:
            request = (await launcher.post("/api/v1/logins", json={})).json()
            claim = await backend.submit(
                "登录", request["code"], "group", "member", "claim"
            )
            assert claim["status"] == "AWAITING_NAME"
            registered = await backend.submit(
                "注册", "Alice", "group", "member", "register"
            )
            assert registered["status"] == "REGISTERED"

            poll_headers = {
                "Authorization": "Bearer " + request["poll_token"],
                "X-Request-ID": "a" * 64,
            }
            session_path = f"/api/v1/logins/{request['request_id']}/session"
            session = (await launcher.post(session_path, headers=poll_headers)).json()
            assert (
                await launcher.post(session_path, headers=poll_headers)
            ).json() == session
            profile_id = session["game"]["selectedProfile"]["id"]
            assert profile_id == registered["uuid"]

            joined = await launcher.post(
                "/api/yggdrasil/sessionserver/session/minecraft/join",
                json={
                    "accessToken": session["game"]["accessToken"],
                    "selectedProfile": profile_id,
                    "serverId": "test-server",
                },
            )
            assert joined.status_code == 204
            renamed = await backend.submit(
                "改名", "NewAlice", "group", "member", "rename"
            )
            assert renamed["uuid"] == profile_id and renamed["name"] == "NewAlice"
            verified = await launcher.get(
                "/api/yggdrasil/sessionserver/session/minecraft/hasJoined",
                params={"username": "NewAlice", "serverId": "test-server"},
            )
            assert verified.json()["id"] == profile_id

            request = (await launcher.post("/api/v1/logins", json={})).json()
            existing = await backend.submit(
                "登录", request["code"], "group", "member", "login-again"
            )
            assert existing == {
                "status": "VERIFIED",
                "name": "NewAlice",
                "uuid": profile_id,
            }
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_real_name_conflict_closes_registration_once(service):
    backend = backend_client(service)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service), base_url="http://auth.test"
        ) as launcher:
            for member in ("first", "second"):
                request = (await launcher.post("/api/v1/logins", json={})).json()
                await backend.submit(
                    "登录", request["code"], "group", member, "claim-" + member
                )
                if member == "first":
                    await backend.submit(
                        "注册", "Alice", "group", member, "register-" + member
                    )
                else:
                    with pytest.raises(BackendError, match="ID 已被占用"):
                        await backend.submit(
                            "注册", "alice", "group", member, "register-" + member
                        )
            response = await launcher.get(
                f"/api/v1/logins/{request['request_id']}",
                headers={"Authorization": "Bearer " + request["poll_token"]},
            )
            assert response.json()["status"] == "FAILED"
            assert response.json()["error"] == "NAME_TAKEN"
            with service.state.db.read() as connection:
                assert (
                    connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
                    == 1
                )
    finally:
        await backend.close()
