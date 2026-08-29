from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import redis

db = SQLAlchemy()
migrate = Migrate()
jwt_manager = JWTManager()
cors = CORS()


class RedisClient:
    """Redis 客户端封装"""

    def __init__(self):
        self._client = None

    def init_app(self, app):
        self._client = redis.from_url(
            app.config["REDIS_URL"],
            decode_responses=True,
        )

    @property
    def client(self) -> redis.Redis:
        return self._client

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def setex(self, key: str, ttl: int, value: str):
        return self._client.setex(key, ttl, value)

    def delete(self, *keys: str):
        if keys:
            return self._client.delete(*keys)

    def keys(self, pattern: str) -> list[str]:
        return self._client.keys(pattern)

    def ttl(self, key: str) -> int:
        return self._client.ttl(key)


redis_client = RedisClient()
