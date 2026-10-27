"""Real stored bookings and captured mail; no external SMTP or customer changes."""
from datetime import datetime, timezone, timedelta

import pytest

from test_reservation_service_routing import state, create  # shared isolated SQLite fixture
from src.modules.vehicle_hub import email_notifications as mail


@pytest.mark.parametrize("utc_time,local_label", [
    (datetime(2026, 10, 28, 7, 50), "28.10.2026 08:50"),
    (datetime(2026, 7, 28, 6, 50), "28.07.2026 08:50"),
    (datetime(2026, 10, 24, 23, 30), "25.10.2026 01:30"),
    (datetime(2026, 10, 25, 0, 30), "25.10.2026 02:30"),
    (datetime(2026, 10, 25, 1, 30), "25.10.2026 02:30"),
    (datetime(2026, 3, 29, 1, 30), "29.03.2026 03:30"),
])
def test_all_booking_notifications_use_czech_time_without_changing_storage(state, utc_time, local_label):
    s = state
    row = create(s)
    row.start_datetime = utc_time
    row.end_datetime = None
    row.status = "CONFIRMED"
    s.db.commit()
    s.db.expire_all()
    assert row.start_datetime == utc_time
    s.mailbox.messages.clear()
    assert mail.send_reservation_created_email(s.db, row, s.mailbox) == (True, True)
    assert mail.send_reservation_status_email(s.db, row, "PENDING", s.mailbox)
    row.status = "CANCELLED"
    assert mail.send_reservation_status_email(s.db, row, "CONFIRMED", s.mailbox)
    row.status = "CONFIRMED"
    assert mail.send_reservation_rescheduled_email(
        s.db, row, utc_time - timedelta(hours=1), email_service=s.mailbox)
    assert len(s.mailbox.messages) == 5  # creation: owner + service; then 3 owner mails
    for message in s.mailbox.messages:
        assert local_label in message.body
        assert local_label in message.html_body
        assert "český čas" in message.body
        assert "český čas" in message.html_body
    s.db.refresh(row)
    assert row.start_datetime == utc_time


def test_original_and_new_term_and_end_time_are_converted_independently(state):
    s = state
    row = create(s)
    row.start_datetime = datetime(2026, 10, 28, 7, 50)
    row.end_datetime = datetime(2026, 10, 28, 8, 20)
    s.db.commit()
    s.mailbox.messages.clear()
    assert mail.send_reservation_rescheduled_email(s.db, row,
        datetime(2026, 10, 28, 7), datetime(2026, 10, 28, 7, 30),
        email_service=s.mailbox)
    for body in (s.mailbox.messages[0].body, s.mailbox.messages[0].html_body):
        assert "28.10.2026 08:00 - 08:30" in body
        assert "28.10.2026 08:50 - 09:20" in body
        assert "28.10.2026 07:50" not in body


@pytest.mark.parametrize("source", [
    datetime(2026, 10, 28, 7, 50),
    datetime(2026, 10, 28, 7, 50, tzinfo=timezone.utc),
    datetime(2026, 10, 28, 8, 50, tzinfo=timezone(timedelta(hours=1))),
])
def test_offset_aware_values_are_not_shifted_twice(source):
    assert mail._format_reservation_time(source) == "28.10.2026 08:50 (český čas)"


def test_range_crossing_midnight_includes_both_local_dates():
    assert mail._format_reservation_time(datetime(2026, 10, 28, 22, 30), datetime(2026, 10, 28, 23, 30)) == (
        "28.10.2026 23:30 - 29.10.2026 00:30 (český čas)")


def test_range_crossing_clock_change_identifies_repeated_hour():
    assert mail._format_reservation_time(datetime(2026, 10, 25, 0, 30), datetime(2026, 10, 25, 1, 30)) == (
        "25.10.2026 02:30 CEST - 02:30 CET (český čas)")
