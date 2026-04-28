"""Phase 1 storage backend tests."""
import pytest
from atrium.core.storage import open_storage
from atrium.core.storage.sqlite import SQLiteStorage


@pytest.fixture
async def sqlite_storage(tmp_path):
    s = SQLiteStorage(f"sqlite:///{tmp_path}/test.db")
    await s.init()
    yield s
    await s.close()


async def test_sqlite_storage_executes_and_fetches(sqlite_storage):
    await sqlite_storage.execute(
        "CREATE TABLE test_tbl (id TEXT PRIMARY KEY, val TEXT)"
    )
    await sqlite_storage.execute(
        "INSERT INTO test_tbl (id, val) VALUES (?, ?)", ("1", "hello")
    )
    row = await sqlite_storage.fetch_one("SELECT val FROM test_tbl WHERE id = ?", ("1",))
    assert row is not None
    assert row[0] == "hello"


async def test_sqlite_storage_fetch_all_returns_all_rows(sqlite_storage):
    await sqlite_storage.execute(
        "CREATE TABLE items (id TEXT PRIMARY KEY, val TEXT)"
    )
    await sqlite_storage.execute_many(
        "INSERT INTO items (id, val) VALUES (?, ?)",
        [("a", "1"), ("b", "2"), ("c", "3")],
    )
    rows = await sqlite_storage.fetch_all("SELECT id FROM items ORDER BY id")
    assert [r[0] for r in rows] == ["a", "b", "c"]


async def test_sqlite_storage_fetch_one_returns_none_when_missing(sqlite_storage):
    await sqlite_storage.execute("CREATE TABLE t (id TEXT PRIMARY KEY)")
    row = await sqlite_storage.fetch_one("SELECT id FROM t WHERE id = ?", ("nope",))
    assert row is None


async def test_storage_factory_picks_sqlite_for_sqlite_url(tmp_path):
    url = f"sqlite:///{tmp_path}/fac.db"
    s = open_storage(url)
    assert isinstance(s, SQLiteStorage)
    await s.init()
    await s.close()


async def test_storage_factory_picks_sqlite_for_memory():
    s = open_storage(":memory:")
    assert isinstance(s, SQLiteStorage)
    await s.init()
    await s.close()


async def test_storage_factory_raises_for_unknown_scheme():
    import pytest
    with pytest.raises(ValueError, match="unsupported db_url"):
        open_storage("redis://localhost")


async def test_sqlite_storage_serializes_concurrent_writes(tmp_path):
    """Multiple concurrent executes must not raise errors."""
    import asyncio
    s = SQLiteStorage(f"sqlite:///{tmp_path}/concurrent.db")
    await s.init()
    await s.execute("CREATE TABLE c (id TEXT PRIMARY KEY, n INTEGER)")

    async def write(i: int):
        await s.execute("INSERT OR REPLACE INTO c (id, n) VALUES (?, ?)", (str(i), i))

    await asyncio.gather(*[write(i) for i in range(20)])
    rows = await s.fetch_all("SELECT id FROM c")
    assert len(rows) == 20
    await s.close()
