from rsmesh_bbs import db_operations


class TestModuleIds:
    def test_default_modules_are_sequential_on_init(self, temp_db):
        ids = [row[0] for row in db_operations.get_modules()]
        assert ids == [1, 2, 3, 4]

    def test_repeated_init_does_not_burn_module_ids(self, temp_db):
        for _ in range(25):
            db_operations.initialize_database(quiet=True)
        ids = [row[0] for row in db_operations.get_modules()]
        assert ids == [1, 2, 3, 4]

    def test_compact_module_ids_renumbers_gaps(self, temp_db):
        conn = db_operations.get_db_connection()
        conn.execute("UPDATE modules SET id = 143 WHERE module_dir = 'fortune'")
        conn.commit()

        db_operations.initialize_database(quiet=True)

        ids = [row[0] for row in db_operations.get_modules()]
        assert ids == [1, 2, 3, 4]

    def test_compact_module_ids_remaps_sync_peer_modules(self, temp_db):
        conn = db_operations.get_db_connection()
        conn.execute("UPDATE modules SET id = 143 WHERE module_dir = 'fortune'")
        conn.commit()

        assert db_operations.add_sync_peer("!abc12345", "rsv1")
        peer_id = db_operations._peer_id_for_bbs_node("!abc12345")
        db_operations.set_sync_peer_module_flags(peer_id, 143, "N", "Y")

        db_operations.initialize_database(quiet=True)

        fortune = db_operations.get_module_by_menu_option("F")
        assert fortune[0] == 4
        sync_out, ingest_in = db_operations.get_sync_peer_module_flags(peer_id, 4)
        assert sync_out == "N"
        assert ingest_in == "Y"
