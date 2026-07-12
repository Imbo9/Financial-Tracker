from unittest.mock import MagicMock

import scripts.migrate_taxonomy as mig  # pyrefly: ignore


def _conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.rowcount = 3
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_remap_table_covers_all_legacy_modal_names():
    assert mig.MANUAL_REMAP == {
        "Transport": "Transit",
        "Career & Professional": "Career & Professional development",
        "Housing": None,
        "Other": None,
    }


def test_migrate_remaps_manual_then_resets_the_rest():
    conn, cur = _conn()
    counts = mig.migrate(conn)

    executed = [c.args for c in cur.execute.call_args_list]
    # 4 manual remaps + 1 manual catch-all + 1 non-manual reset
    assert len(executed) == 6
    assert executed[0][1] == ("Transit", "Transport")
    assert "source = 'manual'" in executed[0][0]
    assert "source != 'manual'" in executed[-1][0]
    assert conn.commit.called
    assert len(counts) == 6
