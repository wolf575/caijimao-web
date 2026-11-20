"""Single-admin authentication: bcrypt password + signed session cookie.

Design notes
------------
* No default password ever ships.  If neither ``WEB_PASSWORD`` nor
  ``WEB_PASSWORD_HASH`` is provided, a random password is generated once,
  printed to the container log, and only its bcrypt hash is persisted.
* The session is a signed (not encrypted) cookie so the browser cannot forge
  it, with a server-side CSRF token inside it for form posts.
* Failed logins are rate limited per client IP in memory.  A restart clears
  the counters, which is acceptable for a single-instance deployment.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

import bcrypt
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger("webui.auth")

COOKIE_NAME = "cj_session"
CSRF_FIELD = "csrf_token"


@dataclass
class Session:
    user: str
    csrf: str

    @property
    def payload(self) -> dict[str, str]:
        return {"u": self.user, "c": self.csrf}


class RateLimiter:
    """Fixed-window counter: N failures inside the window locks the key."""

    def __init__(self, max_failures: int = 5, window: float = 300.0) -> None:
        self.max_failures = max_failures
        self.window = window
        self._state: dict[str, tuple[int, float]] = {}

    def locked(self, key: str) -> bool:
        fails, until = self._state.get(key, (0, 0.0))
        if fails < self.max_failures:
            return False
        if time.time() >= until:
            self._state.pop(key, None)
            return False
        return True

    def fail(self, key: str) -> None:
        fails, _ = self._state.get(key, (0, 0.0))
        self._state[key] = (fails + 1, time.time() + self.window)

    def reset(self, key: str) -> None:
        self._state.pop(key, None)


class Auth:
    def __init__(
        self,
        data_dir: str | Path,
        *,
        user: str | None = None,
        password: str | None = None,
        password_hash: str | None = None,
        secret_key: str | None = None,
        session_hours: float = 12.0,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.user = (user or os.environ.get("WEB_USER") or "admin").strip()
        self.session_seconds = int(session_hours * 3600)
        self.limiter = RateLimiter()
        self._explicit_hash = password_hash or os.environ.get("WEB_PASSWORD_HASH")
        self._plain = password if password is not None else os.environ.get("WEB_PASSWORD")
        self._secret = secret_key or os.environ.get("SECRET_KEY")
        self._serializer: URLSafeTimedSerializer | None = None
        self.password_hash: bytes = b""
        self.generated_password: str | None = None

    # ------------------------------------------------------------- bootstrap

    def bootstrap(self) -> None:
        self.password_hash = self._resolve_password()
        self._serializer = URLSafeTimedSerializer(self._resolve_secret(), salt="cj-session")
        if self.generated_password:
            log.warning(
                "未提供 WEB_PASSWORD，已生成随机管理密码（只显示这一次）: user=%s password=%s",
                self.user,
                self.generated_password,
            )
            print(
                f"\n=== 采集猫 Web 管理密码已生成 ===\n"
                f"  用户名: {self.user}\n"
                f"  密  码: {self.generated_password}\n"
                f"  哈希已保存到: {self.data_dir / '.web_credentials'}\n"
                f"================================\n",
                flush=True,
            )

    def _resolve_password(self) -> bytes:
        if self._explicit_hash:
            raw = self._explicit_hash.strip()
            if not raw.startswith("$2"):
                raise RuntimeError(
                    "WEB_PASSWORD_HASH 不是 bcrypt 哈希（应以 $2b$ / $2a$ 开头）"
                )
            return raw.encode()

        store = self.data_dir / ".web_credentials"
        if self._plain:
            hashed = bcrypt.hashpw(self._plain.encode(), bcrypt.gensalt())
            store.write_bytes(hashed)
            try:
                store.chmod(0o600)
            except OSError:
                pass
            return hashed

        if store.exists():
            data = store.read_bytes().strip()
            if data.startswith(b"$2"):
                return data

        generated = secrets.token_urlsafe(15)
        self.generated_password = generated
        hashed = bcrypt.hashpw(generated.encode(), bcrypt.gensalt())
        store.write_bytes(hashed)
        try:
            store.chmod(0o600)
        except OSError:
            pass
        return hashed

    def _resolve_secret(self) -> str:
        if self._secret:
            return self._secret
        store = self.data_dir / ".secret_key"
        if store.exists():
            value = store.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        store.write_text(value, encoding="utf-8")
        try:
            store.chmod(0o600)
        except OSError:
            pass
        log.warning("未提供 SECRET_KEY，已在 %s 生成并持久化", store)
        return value

    # --------------------------------------------------------------- session

    def _ser(self) -> URLSafeTimedSerializer:
        if self._serializer is None:
            raise RuntimeError("Auth.bootstrap() 未调用")
        return self._serializer

    def issue(self, user: str) -> tuple[str, Session]:
        session = Session(user=user, csrf=secrets.token_urlsafe(24))
        token = self._ser().dumps(session.payload)
        return token, session

    def read(self, token: str | None) -> Session | None:
        if not token:
            return None
        try:
            payload = self._ser().loads(token, max_age=self.session_seconds)
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        if not isinstance(payload, dict):
            return None
        user = payload.get("u")
        csrf = payload.get("c")
        if not isinstance(user, str) or not isinstance(csrf, str):
            return None
        return Session(user=user, csrf=csrf)

    # ---------------------------------------------------------------- login

    def verify(self, user: str, password: str, client_ip: str) -> Session | None:
        if self.limiter.locked(client_ip):
            log.warning("登录被限速: ip=%s", client_ip)
            return None
        user_ok = hmac.compare_digest(user.strip(), self.user)
        pass_ok = False
        try:
            pass_ok = bcrypt.checkpw(password.encode(), self.password_hash)
        except ValueError:
            pass_ok = False
        if not (user_ok and pass_ok):
            self.limiter.fail(client_ip)
            log.warning("登录失败: user=%r ip=%s", user, client_ip)
            return None
        self.limiter.reset(client_ip)
        log.info("登录成功: user=%s ip=%s", self.user, client_ip)
        return Session(user=self.user, csrf=secrets.token_urlsafe(24))

    @staticmethod
    def client_ip(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    # --------------------------------------------------------------- guards

    def session_of(self, request: Request) -> Session | None:
        return self.read(request.cookies.get(COOKIE_NAME))

    def require(self, request: Request) -> Session:
        session = self.session_of(request)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录",
                headers={"X-Redirect": "/login"},
            )
        return session

    @staticmethod
    def check_csrf(session: Session, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(session.csrf, token or "")
