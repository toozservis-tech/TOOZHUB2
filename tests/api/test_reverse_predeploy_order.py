"""Replay of 0028 must not index columns that only 0030 can add."""
from sqlalchemy import inspect, text
from test_reverse_notification_migration import old_engine
from scripts.migrate_admin_messages import migrate as migrate28
from scripts.migrate_mobile_release import migrate as predeploy


def test_0028_replay_restores_only_its_own_indexes_on_actual_0029_schema(tmp_path):
    engine = old_engine(tmp_path)
    try:
        with engine.begin() as connection:
            connection.execute(text('DROP INDEX IF EXISTS ix_admin_message_unread'))
        migrate28(engine)
        inspector = inspect(engine)
        assert 'reply_to_message_id' not in {column['name'] for column in inspector.get_columns('admin_messages')}
        assert 'ix_admin_message_unread' in {index['name'] for index in inspector.get_indexes('admin_messages')}
        assert 'ix_admin_messages_addressed_admin_id' not in {index['name'] for index in inspector.get_indexes('admin_messages')}
    finally:
        engine.dispose()


def test_full_predeploy_0029_to_0030_then_repeat_retains_prior_receipts(tmp_path):
    engine = old_engine(tmp_path)
    try:
        predeploy(engine)
        with engine.connect() as connection:
            cursors = connection.execute(text('SELECT kind, source_id, rollout_at FROM notification_cursors ORDER BY kind')).all()
        predeploy(engine)
        with engine.connect() as connection:
            assert connection.execute(text('SELECT kind, source_id, rollout_at FROM notification_cursors ORDER BY kind')).all() == cursors
            assert connection.execute(text('SELECT id,item_id,state,attempts FROM notification_push_outbox')).one() == (12,9,'accepted',1)
            assert connection.execute(text('SELECT message_id FROM admin_message_commands')).scalar() == 5
            assert connection.execute(text('SELECT body FROM admin_messages')).scalar() == 'Retain message'
            assert not connection.execute(text('PRAGMA foreign_key_check')).all()
        indexes = {row['name'] for row in inspect(engine).get_indexes('admin_messages')}
        assert {'ix_admin_messages_addressed_admin_id','ix_admin_messages_reply_to_message_id','ix_admin_messages_reply_to_notification_id'} <= indexes
    finally:
        engine.dispose()
