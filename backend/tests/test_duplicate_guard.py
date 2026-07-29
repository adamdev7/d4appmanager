from app.ai_email_assistant.duplicate_guard import (
    thread_has_answered_in_db,
    thread_has_sent_reply,
)


def test_thread_not_answered_empty():
    class FakeScalars:
        def all(self):
            return []

    class FakeDb:
        def scalars(self, _q):
            return FakeScalars()

    assert not thread_has_answered_in_db(
        FakeDb(),  # type: ignore[arg-type]
        gmail_account_id="g1",
        thread_id="t1",
    )
    assert not thread_has_sent_reply(
        FakeDb(),  # type: ignore[arg-type]
        gmail_account_id="g1",
        thread_id="t1",
    )


def test_thread_answered_when_sibling_sent():
    class Reply:
        def __init__(self, status: str, reply_id: str = "r1"):
            self.status = status
            self.id = reply_id
            self.created_at = None

    class Row:
        def __init__(self, row_id: str, status: str, replies: list):
            self.id = row_id
            self.status = status
            self.replies = replies

    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    rows = [
        Row("a", "new", []),
        Row("b", "replied", [Reply("sent", "r-sent")]),
    ]

    class FakeDb:
        def scalars(self, _q):
            return FakeScalars(rows)

    assert thread_has_answered_in_db(
        FakeDb(),  # type: ignore[arg-type]
        gmail_account_id="g1",
        thread_id="t1",
        exclude_inbox_id="a",
    )
    assert thread_has_sent_reply(
        FakeDb(),  # type: ignore[arg-type]
        gmail_account_id="g1",
        thread_id="t1",
        exclude_reply_id="other",
    )
    assert not thread_has_sent_reply(
        FakeDb(),  # type: ignore[arg-type]
        gmail_account_id="g1",
        thread_id="t1",
        exclude_reply_id="r-sent",
    )
