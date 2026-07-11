"""S18: the per-run dedup window in write_recommendation (Wave 1 behavior)."""

from src.persistence.writers import write_recommendation


class FakeCursor:
    def __init__(self, existing_count):
        self.existing_count = existing_count
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(" ".join(sql.split()))

    def fetchone(self):
        return {"cnt": self.existing_count}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


REC = {"action": "BUY", "confidence": 0.7, "reasoning": "r"}


def test_recommendation_skipped_when_row_within_dedup_window():
    cur = FakeCursor(existing_count=1)
    write_recommendation(FakeConn(cur), 1, REC, {}, {}, None)
    assert len(cur.executed) == 1  # only the dedup SELECT — no INSERT
    assert cur.executed[0].startswith("SELECT COUNT(*)")


def test_recommendation_written_when_window_clear():
    cur = FakeCursor(existing_count=0)
    write_recommendation(FakeConn(cur), 1, REC, {}, {}, None)
    assert len(cur.executed) == 2
    assert "INSERT INTO recommendations" in cur.executed[1]


def test_dry_run_touches_nothing():
    cur = FakeCursor(existing_count=0)
    write_recommendation(FakeConn(cur), 1, REC, {}, {}, None, dry_run=True)
    assert cur.executed == []
