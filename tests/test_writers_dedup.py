"""S18: the per-run dedup window in write_recommendation (Wave 1 behavior).
Session 22: fundamentals persistence + the prediction-patterns writer."""

import json

from src.persistence.writers import write_prediction_patterns, write_recommendation


class FakeCursor:
    def __init__(self, existing_count=0):
        self.existing_count = existing_count
        self.executed = []
        self.params = []

    def execute(self, sql, params=None):
        self.executed.append(" ".join(sql.split()))
        self.params.append(params)

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


def test_fundamentals_persisted_as_json_when_present():
    cur = FakeCursor(existing_count=0)
    fund = {"trailing_pe": 28.5, "currency": "USD"}
    write_recommendation(FakeConn(cur), 1, REC, {}, {}, None, fundamentals=fund)
    insert_params = cur.params[1]
    assert json.loads(insert_params[7]) == fund  # the fundamentals column


def test_fundamentals_null_when_absent():
    # NULL, never an empty JSON placeholder — ETFs/index/untyped store nothing.
    cur = FakeCursor(existing_count=0)
    write_recommendation(FakeConn(cur), 1, REC, {}, {}, None, fundamentals=None)
    assert cur.params[1][7] is None


def test_prediction_patterns_insert_and_dry_run():
    cur = FakeCursor()
    result = {"patterns": [{"name": "p", "status": "NEW"}], "narrative": "texto"}
    stats = {"total_outcomes": 4}
    write_prediction_patterns(FakeConn(cur), result, stats, horizon=30)
    assert "INSERT INTO prediction_patterns" in cur.executed[0]
    params = cur.params[0]
    assert params[1] == 30
    assert json.loads(params[2]) == result["patterns"]
    assert params[3] == "texto"
    assert json.loads(params[4]) == stats

    dry = FakeCursor()
    write_prediction_patterns(FakeConn(dry), result, stats, horizon=30, dry_run=True)
    assert dry.executed == []
