# MCP Python SDK streamable HTTP API truth (2026-05-15)

## Контекст

Нужно было проверить, относится ли GIM-313 runtime blocker к устаревшему MCP client API в CLI path (`palace_mcp.cli`) или к фактической server/runtime деградации во время full `project analyze`.

## Локально проверённая версия

`services/palace-mcp` использует:

```text
mcp==1.23.3
```

Команда:

```bash
cd services/palace-mcp && uv run python - <<'PY'
import importlib.metadata
print(importlib.metadata.version('mcp'))
PY
```

## Что говорит актуальная официальная документация

По README `modelcontextprotocol/python-sdk` (stable v1.x, просмотрено 2026-05-15):

- examples используют `from mcp.client.streamable_http import streamable_http_client`;
- OAuth example показывает custom `httpx.AsyncClient` через `http_client=...`.

Ссылка: <https://github.com/modelcontextprotocol/python-sdk>

## Что реально экспортирует установленный пакет

Локальная introspection в `mcp==1.23.3`:

```bash
cd services/palace-mcp && uv run python - <<'PY'
import inspect
import mcp.client.streamable_http as s
print([n for n in dir(s) if 'streamable' in n])
print(inspect.signature(s.streamablehttp_client))
PY
```

Вывод:

```text
['streamablehttp_client']
(url: str, headers: dict[str, str] | None = None, timeout: float | datetime.timedelta = 30, sse_read_timeout: float | datetime.timedelta = 300, terminate_on_close: bool = True, httpx_client_factory: mcp.shared._httpx_utils.McpHttpClientFactory = <function create_mcp_http_client ...>, auth: httpx.Auth | None = None)
```

Проверка нового имени в локальной версии:

```bash
cd services/palace-mcp && uv run python - <<'PY'
try:
    from mcp.client.streamable_http import streamable_http_client
    print('ok')
except Exception as exc:
    print(type(exc).__name__, exc)
PY
```

Вывод:

```text
ImportError cannot import name 'streamable_http_client' from 'mcp.client.streamable_http'
```

## Важное наблюдение про redirect behavior

В локальном `mcp==1.23.3` дефолтный `create_mcp_http_client(...)` уже включает:

```text
follow_redirects=True
```

Это проверено через:

```bash
cd services/palace-mcp && uv run python - <<'PY'
import inspect
from mcp.shared._httpx_utils import create_mcp_http_client
print(inspect.getsource(create_mcp_http_client))
PY
```

## Вывод для GIM-313

1. На текущем pinned dependency нельзя просто заменить импорт на `streamable_http_client`: такого символа в установленном SDK нет.
2. Текущий transport path уже ходит с `follow_redirects=True`, поэтому 307 redirect сам по себе не объясняет `RemoteProtocolError`.
3. Для GIM-313 разумная граница такая:
   - не делать dependency-upgrade MCP SDK в этом узком fix;
   - доказать живым integration-test, что текущий CLI polling path успешно проходит `healthz`, `initialize()`, `analyze_status`, `analyze_resume` и достигает terminal status;
   - считать runtime blocker из QA smoke изолированным к server/container/Neo4j health path, а не к самому факту использования текущего transport API.
