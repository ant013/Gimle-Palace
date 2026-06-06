from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from palace_mcp.migrations.m2026_06_short_name import (
    run_migration,
    short_name_for_symbol,
)


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __aiter__(self):
        async def _gen():
            for row in self._rows:
                yield row

        return _gen()

    async def single(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


def _mock_driver(*results: _FakeResult) -> MagicMock:
    session = AsyncMock()
    session.run = AsyncMock(side_effect=list(results))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


def test_short_name_for_symbol_decodes_scip() -> None:
    qualified_name = "UwMiniCore s%3A10UwMiniCore11WalletStoreC6select8walletIDySi_tF"
    assert short_name_for_symbol(qualified_name, "") == "select"


async def test_run_migration_backfills_in_batches() -> None:
    driver = _mock_driver(
        _FakeResult(
            [
                {
                    "uuid": "sym-1",
                    "qualified_name": "UwMiniCore s%3A10UwMiniCore11WalletStoreC",
                    "name": "",
                }
            ]
        ),
        _FakeResult([{"updated": 1}]),
        _FakeResult([]),
    )

    migrated = await run_migration(driver, batch_size=1)

    assert migrated == 1
    update_rows = driver.session.return_value.run.await_args_list[1].kwargs["rows"]
    assert update_rows == [{"uuid": "sym-1", "short_name": "WalletStore"}]
