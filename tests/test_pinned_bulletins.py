from datetime import datetime, timedelta

from rsmesh_bbs import db_operations


def _insert_bulletin(board, subject, pinned, age_days):
    posted = (datetime.now() - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M")
    conn = db_operations.get_db_connection()
    conn.execute(
        "INSERT INTO bulletins "
        "(board, sender_short_name, date, subject, content, unique_id, synced, pinned, deleted) "
        "VALUES (?, ?, ?, ?, ?, lower(hex(randomblob(16))), 'Y', ?, 'N')",
        (board, "OPS", posted, subject, "Body", pinned),
    )
    conn.commit()


class TestPinnedBulletinDisplay:
    def test_mesh_board_hides_old_unpinned_posts(self, temp_db):
        _insert_bulletin("General", "Old post", "N", age_days=60)
        _insert_bulletin("General", "Recent post", "N", age_days=1)

        subjects = [row[1] for row in db_operations.get_mesh_bulletins("General")]
        assert subjects == ["Recent post"]

    def test_mesh_board_keeps_old_pinned_posts(self, temp_db):
        _insert_bulletin("General", "Pinned old", "Y", age_days=90)
        _insert_bulletin("General", "Recent", "N", age_days=1)

        subjects = [row[1] for row in db_operations.get_mesh_bulletins("General")]
        assert subjects == ["Pinned old", "Recent"]

    def test_pinned_posts_listed_before_unpinned(self, temp_db):
        _insert_bulletin("General", "Recent unpinned", "N", age_days=1)
        _insert_bulletin("General", "Pinned old", "Y", age_days=90)

        subjects = [row[1] for row in db_operations.get_mesh_bulletins("General")]
        assert subjects == ["Pinned old", "Recent unpinned"]
