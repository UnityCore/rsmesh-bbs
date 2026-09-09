def configure_sqlite_connection(conn, read_only=False):
    """Enable WAL and sensible defaults for concurrent server/admin access."""
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
