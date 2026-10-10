import asyncio
from unittest.mock import patch

from api.bot import tg


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


class _Client:
    def __init__(self, *a, **k):
        self.enviados = []
        _Client.ultimo = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json):
        self.enviados.append(dict(json))
        if json.get("parse_mode"):
            return _Resp({"ok": False, "description": "Bad Request: can't parse entities: ..."})
        return _Resp({"ok": True})


def test_asterisco_del_comercio_reintenta_sin_formato():
    with patch.object(tg.httpx, "AsyncClient", _Client):
        r = asyncio.run(tg._send(1, "📌 *💳 Santander · DLO*PedidosYa Carrefou* · *$35,960*", "t"))
    assert r["ok"]
    env = _Client.ultimo.enviados
    assert len(env) == 2 and "parse_mode" not in env[1] and "*" not in env[1]["text"]
