from app.ai_email_assistant.duplicate_guard import thread_has_answered_in_db


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
