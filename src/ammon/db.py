"""SQLite database for AMMON — Apple Music Monitor."""
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path.home() / ".ammon" / "ammon.db"


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS artists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            apple_id   TEXT    UNIQUE NOT NULL,
            name       TEXT,
            added_at   INTEGER DEFAULT (strftime('%s','now')),
            last_check INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS albums (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            apple_id      TEXT    UNIQUE NOT NULL,
            artist_apple_id TEXT,
            name          TEXT,
            release_date  TEXT,
            storefront    TEXT    DEFAULT 'us',
            release_type  TEXT,
            downloaded    INTEGER DEFAULT 0,
            download_path TEXT,
            discovered_at INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_apple_id);
        CREATE INDEX IF NOT EXISTS idx_albums_downloaded ON albums(downloaded);

        CREATE TABLE IF NOT EXISTS playlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            apple_id   TEXT    UNIQUE NOT NULL,
            name       TEXT,
            added_at   INTEGER DEFAULT (strftime('%s','now')),
            last_check INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id TEXT NOT NULL,
            track_id    TEXT NOT NULL,
            track_name  TEXT,
            artist_name TEXT,
            downloaded  INTEGER DEFAULT 0,
            discovered_at INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(playlist_id, track_id)
        );

        CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks(playlist_id);
        CREATE INDEX IF NOT EXISTS idx_playlist_tracks_dl ON playlist_tracks(downloaded);
    """)
    conn.commit()


# ── Artists ───────────────────────────────────────────────────────────────────

def add_artist(conn, apple_id: str, name: str) -> int:
    now = int(time.time())
    cur = conn.execute(
        "INSERT OR IGNORE INTO artists (apple_id, name, added_at) VALUES (?,?,?)",
        (apple_id, name, now)
    )
    if cur.rowcount == 0:
        conn.execute("UPDATE artists SET name=? WHERE apple_id=?", (name, apple_id))
    conn.commit()
    return conn.execute("SELECT id FROM artists WHERE apple_id=?", (apple_id,)).fetchone()["id"]


def remove_artist(conn, apple_id: str) -> bool:
    cur = conn.execute("DELETE FROM artists WHERE apple_id=?", (apple_id,))
    conn.commit()
    return cur.rowcount > 0


def get_all_artists(conn) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM artists ORDER BY name COLLATE NOCASE"
    ).fetchall()]


def get_artist(conn, apple_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM artists WHERE apple_id=?", (apple_id,)).fetchone()
    return dict(row) if row else None


def update_last_check(conn, apple_id: str):
    conn.execute("UPDATE artists SET last_check=? WHERE apple_id=?",
                 (int(time.time()), apple_id))
    conn.commit()


# ── Albums ────────────────────────────────────────────────────────────────────

def album_exists(conn, apple_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM albums WHERE apple_id=?", (apple_id,)
    ).fetchone() is not None


def add_album(conn, apple_id: str, artist_apple_id: str, name: str,
              release_date: str, storefront: str, release_type: str) -> bool:
    """Returns True if newly inserted, False if already existed."""
    cur = conn.execute("""
        INSERT OR IGNORE INTO albums
            (apple_id, artist_apple_id, name, release_date, storefront, release_type)
        VALUES (?,?,?,?,?,?)
    """, (apple_id, artist_apple_id, name, release_date, storefront, release_type))
    conn.commit()
    return cur.rowcount > 0


def mark_downloaded(conn, apple_id: str, path: str = ""):
    conn.execute("UPDATE albums SET downloaded=1, download_path=? WHERE apple_id=?",
                 (path, apple_id))
    conn.commit()


def get_pending_downloads(conn) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM albums WHERE downloaded=0 ORDER BY release_date DESC"
    ).fetchall()]


# ── Playlists ─────────────────────────────────────────────────────────────────

def add_playlist(conn, apple_id: str, name: str) -> int:
    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO playlists (apple_id, name, added_at) VALUES (?,?,?)",
        (apple_id, name, now)
    )
    conn.execute("UPDATE playlists SET name=? WHERE apple_id=?", (name, apple_id))
    conn.commit()
    return conn.execute("SELECT id FROM playlists WHERE apple_id=?", (apple_id,)).fetchone()["id"]


def remove_playlist(conn, apple_id: str) -> bool:
    cur = conn.execute("DELETE FROM playlists WHERE apple_id=?", (apple_id,))
    conn.commit()
    return cur.rowcount > 0


def get_all_playlists(conn) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM playlists ORDER BY name COLLATE NOCASE"
    ).fetchall()]


def get_playlist(conn, apple_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM playlists WHERE apple_id=?", (apple_id,)).fetchone()
    return dict(row) if row else None


def update_playlist_last_check(conn, apple_id: str):
    conn.execute("UPDATE playlists SET last_check=? WHERE apple_id=?",
                 (int(time.time()), apple_id))
    conn.commit()


def add_playlist_track(conn, playlist_id: str, track_id: str,
                       track_name: str, artist_name: str) -> bool:
    """Returns True if newly inserted."""
    cur = conn.execute("""
        INSERT OR IGNORE INTO playlist_tracks
            (playlist_id, track_id, track_name, artist_name)
        VALUES (?,?,?,?)
    """, (playlist_id, track_id, track_name, artist_name))
    conn.commit()
    return cur.rowcount > 0


def mark_track_downloaded(conn, playlist_id: str, track_id: str):
    conn.execute(
        "UPDATE playlist_tracks SET downloaded=1 WHERE playlist_id=? AND track_id=?",
        (playlist_id, track_id)
    )
    conn.commit()


def get_pending_playlist_tracks(conn, playlist_id: str = None) -> list:
    if playlist_id:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM playlist_tracks WHERE downloaded=0 AND playlist_id=?",
            (playlist_id,)
        ).fetchall()]
    return [dict(r) for r in conn.execute(
        "SELECT * FROM playlist_tracks WHERE downloaded=0"
    ).fetchall()]


def get_stats(conn) -> dict:
    return {
        "artists":    conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0],
        "albums":     conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0],
        "downloaded": conn.execute("SELECT COUNT(*) FROM albums WHERE downloaded=1").fetchone()[0],
        "pending":    conn.execute("SELECT COUNT(*) FROM albums WHERE downloaded=0").fetchone()[0],
    }
