"""AMMON CLI — Apple Music Monitor."""
import sys
import click
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from . import api as _api, db as _db, monitor as _monitor
from .db import DEFAULT_DB

COOKIES_PATH = Path("C:/OrpheusDL/config/cookies.txt")


def _get_conn(db_path):
    return _db.get_connection(Path(db_path) if db_path else DEFAULT_DB)


def _get_api(cookies):
    path = Path(cookies) if cookies else COOKIES_PATH
    if not path.exists():
        click.echo(f"  [!] cookies.txt not found: {path}", err=True)
        sys.exit(1)
    return _api.get_api(path)


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0", prog_name="ammon")
@click.option("--db", default=None, metavar="PATH", help=f"DB path (default: {DEFAULT_DB})")
@click.option("--cookies", default=None, metavar="PATH", help="cookies.txt path")
@click.pass_context
def cli(ctx, db, cookies):
    """AMMON — Apple Music Monitor\n\nMonitor artists and download new releases automatically."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["cookies"] = cookies


@cli.command()
@click.argument("artist_id", metavar="APPLE_ID")
@click.pass_context
def follow(ctx, artist_id):
    """Follow an Apple Music artist by their numeric ID.

    APPLE_ID is the numeric Apple Music artist ID.
    Example: ammon follow 1445958214
    """
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])

    name = _api.get_artist_name(apple_api, artist_id)
    if not name:
        click.echo(f"  [!] Artist {artist_id} not found on Apple Music.")
        sys.exit(1)

    _db.add_artist(conn, artist_id, name)
    click.echo(f"  + Following: {name} ({artist_id})")
    conn.close()


@cli.command()
@click.argument("artist_id", metavar="APPLE_ID")
@click.pass_context
def unfollow(ctx, artist_id):
    """Stop following an Apple Music artist.

    APPLE_ID is the numeric Apple Music artist ID.
    Example: ammon unfollow 1445958214
    """
    conn = _get_conn(ctx.obj["db"])
    artist = _db.get_artist(conn, artist_id)
    if not artist:
        click.echo(f"  [!] Artist {artist_id} not in follow list.")
        conn.close()
        sys.exit(1)
    _db.remove_artist(conn, artist_id)
    click.echo(f"  - Unfollowed: {artist['name']} ({artist_id})")
    conn.close()


@cli.command(name="list")
@click.pass_context
def list_artists(ctx):
    """List followed artists."""
    conn = _get_conn(ctx.obj["db"])
    artists = _db.get_all_artists(conn)
    conn.close()

    if not artists:
        click.echo("  No artists followed. Use: ammon follow <artist_id>")
        return

    click.echo(f"\n  {'Apple ID':<15} {'Name'}")
    click.echo("  " + "-" * 50)
    for a in artists:
        import datetime
        last = datetime.datetime.fromtimestamp(a["last_check"]).strftime("%Y-%m-%d") if a["last_check"] else "never"
        click.echo(f"  {a['apple_id']:<15} {a['name'] or '?'}  (last check: {last})")
    click.echo()


@cli.command()
@click.option("--download", "-d", is_flag=True, help="Download new releases automatically via orpheus")
@click.option("--since", "-s", default=None, metavar="YYYY-MM-DD", help="Only check releases from this date")
@click.option("--artist", "-a", default=None, metavar="APPLE_ID", help="Refresh only this artist")
@click.pass_context
def refresh(ctx, download, since, artist):
    """Check for new releases from followed artists.

    Scans all 167 Apple Music storefronts in parallel.
    Use --download to automatically download via orpheus.

    Examples:\n
      ammon refresh\n
      ammon refresh --download\n
      ammon refresh --download --since 2025-01-01\n
      ammon refresh --artist 1445958214
    """
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])

    if artist:
        artists = [_db.get_artist(conn, artist) or {"apple_id": artist, "name": artist}]
    else:
        artists = _db.get_all_artists(conn)

    if not artists:
        click.echo("  No artists followed.")
        conn.close()
        return

    total_new = total_dl = total_err = 0
    click.echo(f"\n  Scanning {len(artists)} artist(s)...\n")

    for a in artists:
        result = _monitor.refresh_artist(
            conn, apple_api, a["apple_id"],
            download=download, since=since, verbose=True
        )
        total_new += result["new"]
        total_dl  += result["downloaded"]
        total_err += result["errors"]

    click.echo(f"\n  Done — {total_new} new, {total_dl} downloaded, {total_err} errors.")
    conn.close()


@cli.command()
@click.option("--pending", "-p", is_flag=True, help="List albums pending download")
@click.pass_context
def status(ctx, pending):
    """Show database statistics: artists, albums discovered, pending downloads.

    Use --pending to list albums that were detected but not yet downloaded.
    """
    conn = _get_conn(ctx.obj["db"])
    stats = _db.get_stats(conn)
    click.echo(f"\n  Artists followed : {stats['artists']}")
    click.echo(f"  Albums discovered: {stats['albums']}")
    click.echo(f"  Downloaded       : {stats['downloaded']}")
    click.echo(f"  Pending          : {stats['pending']}")
    click.echo(f"  DB               : {DEFAULT_DB}\n")

    if pending and stats["pending"] > 0:
        rows = _db.get_pending_downloads(conn)
        click.echo(f"  {'Apple ID':<15} {'Date':<12} {'Type':<12} Name")
        click.echo("  " + "-" * 70)
        for r in rows[:50]:
            click.echo(f"  {r['apple_id']:<15} {r['release_date'] or '?':<12} {r['release_type'] or '?':<12} {r['name']}")
        if len(rows) > 50:
            click.echo(f"  ... and {len(rows)-50} more")
        click.echo()

    conn.close()


@cli.command(name="import-odesli")
@click.option("--db-path", default=None, metavar="PATH", help="odesli DB path (default: ~/.odesli/music.db)")
@click.pass_context
def import_odesli(ctx, db_path):
    """Import Apple Music artist IDs from odesli cross-platform database.

    Reads artists that have an Apple Music ID in odesli and adds them
    to the ammon follow list. Skips artists already followed.
    """
    import sqlite3
    odesli_db = Path(db_path) if db_path else Path.home() / ".odesli" / "music.db"
    if not odesli_db.exists():
        click.echo(f"  [!] odesli DB not found: {odesli_db}")
        sys.exit(1)

    oconn = sqlite3.connect(str(odesli_db))
    oconn.row_factory = sqlite3.Row
    rows = oconn.execute("""
        SELECT a.name, ap.platform_id
        FROM artist_platforms ap
        JOIN artists a ON a.id = ap.artist_id
        WHERE ap.platform = 'Apple Music'
        GROUP BY ap.platform_id
    """).fetchall()
    oconn.close()

    if not rows:
        click.echo("  No Apple Music IDs found in odesli DB.")
        return

    conn = _get_conn(ctx.obj["db"])
    added = 0
    for r in rows:
        existing = _db.get_artist(conn, r["platform_id"])
        if not existing:
            _db.add_artist(conn, r["platform_id"], r["name"])
            added += 1

    conn.close()
    click.echo(f"  Imported {added} new artists from odesli ({len(rows)} total with Apple ID).")


@cli.group()
def playlist():
    """Monitor Apple Music playlists for new tracks."""
    pass


def _parse_playlist_id(value: str) -> str:
    """Extract playlist ID from a full Apple Music URL or return as-is."""
    if value.startswith("http"):
        from urllib.parse import urlparse
        path = urlparse(value).path
        parts = [p for p in path.split("/") if p]
        # Last segment is the ID
        return parts[-1] if parts else value
    return value


@playlist.command(name="follow")
@click.argument("playlist_id", metavar="ID_OR_URL")
@click.pass_context
def playlist_follow(ctx, playlist_id):
    """Follow a playlist to monitor for new tracks.

    Accepts a playlist ID or full Apple Music URL.
    Seeds existing tracks silently — only future additions trigger alerts.
    Supports catalog playlists (pl.xxx) and personal library playlists (p.xxx).

    Examples:\n
      ammon playlist follow pl.4b364b8b182f4115acbf6deb83bd5222\n
      ammon playlist follow "https://music.apple.com/library/playlist/p.xxx"
    """
    playlist_id = _parse_playlist_id(playlist_id)
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])
    info = _api.get_playlist_info(apple_api, playlist_id)
    if not info:
        click.echo(f"  [!] Playlist {playlist_id} not found.")
        conn.close()
        sys.exit(1)
    _db.add_playlist(conn, playlist_id, info["name"])
    # Seed existing tracks so we only alert on FUTURE additions
    tracks = _api.get_playlist_tracks(apple_api, playlist_id)
    for t in tracks:
        _db.add_playlist_track(conn, playlist_id, t["track_id"], t["track_name"], t["artist_name"])
    _db.update_playlist_last_check(conn, playlist_id)
    click.echo(f"  + Following playlist: {info['name']} ({playlist_id})")
    click.echo(f"    Seeded {len(tracks)} existing tracks — only new additions will be flagged.")
    conn.close()


@playlist.command(name="unfollow")
@click.argument("playlist_id", metavar="ID_OR_URL")
@click.pass_context
def playlist_unfollow(ctx, playlist_id):
    """Stop monitoring a playlist for new tracks.

    Accepts a playlist ID or full Apple Music URL.
    """
    playlist_id = _parse_playlist_id(playlist_id)
    conn = _get_conn(ctx.obj["db"])
    pl = _db.get_playlist(conn, playlist_id)
    if not pl:
        click.echo(f"  [!] Playlist {playlist_id} not in follow list.")
        conn.close()
        sys.exit(1)
    _db.remove_playlist(conn, playlist_id)
    click.echo(f"  - Unfollowed: {pl['name']}")
    conn.close()


@playlist.command(name="list")
@click.pass_context
def playlist_list(ctx):
    """List followed playlists."""
    conn = _get_conn(ctx.obj["db"])
    playlists = _db.get_all_playlists(conn)
    conn.close()
    if not playlists:
        click.echo("  No playlists followed. Use: ammon playlist follow <id>")
        return
    click.echo(f"\n  {'Apple ID':<40} Name")
    click.echo("  " + "-" * 70)
    for p in playlists:
        click.echo(f"  {p['apple_id']:<40} {p['name'] or '?'}")
    click.echo()


@playlist.command(name="refresh")
@click.option("--download", "-d", is_flag=True, help="Download new tracks automatically via orpheus")
@click.option("--playlist", "-p", default=None, metavar="ID_OR_URL", help="Refresh only this playlist")
@click.pass_context
def playlist_refresh(ctx, download, playlist):
    """Check followed playlists for newly added tracks.

    Compares current playlist contents against seeded tracks.
    Only alerts on tracks added AFTER the playlist was followed.

    Examples:\n
      ammon playlist refresh\n
      ammon playlist refresh --download\n
      ammon playlist refresh --playlist pl.4b364b8b182f4115acbf6deb83bd5222
    """
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])

    playlists = [_db.get_playlist(conn, playlist)] if playlist else _db.get_all_playlists(conn)
    if not playlists or playlists[0] is None:
        click.echo("  No playlists followed.")
        conn.close()
        return

    from . import downloader as _dl
    total_new = total_dl = total_err = 0

    for pl in playlists:
        click.echo(f"  Checking: {pl['name']} ({pl['apple_id']})...")
        tracks = _api.get_playlist_tracks(apple_api, pl["apple_id"])
        new = dl = err = 0
        for t in tracks:
            is_new = _db.add_playlist_track(
                conn, pl["apple_id"], t["track_id"], t["track_name"], t["artist_name"]
            )
            if is_new:
                new += 1
                click.echo(f"    + NEW: {t['artist_name']} - {t['track_name']} ({t['track_id']})")
                if download:
                    ok, msg = _dl.download_track(t["track_id"])
                    if ok:
                        _db.mark_track_downloaded(conn, pl["apple_id"], t["track_id"])
                        dl += 1
                        click.echo(f"      + Downloaded")
                    else:
                        err += 1
                        click.echo(f"      x {msg}")
        _db.update_playlist_last_check(conn, pl["apple_id"])
        click.echo(f"    {new} new, {dl} downloaded, {err} errors")
        total_new += new; total_dl += dl; total_err += err

    click.echo(f"\n  Done — {total_new} new tracks, {total_dl} downloaded, {total_err} errors.")
    conn.close()


@playlist.command(name="extract-artists")
@click.argument("playlist_id", metavar="ID_OR_URL")
@click.option("--follow", "-f", is_flag=True, help="Add artists to ammon follow list and sync to odesli")
@click.pass_context
def playlist_extract_artists(ctx, playlist_id, follow):
    """Extract all unique artists from a playlist.

    Use --follow to add them to ammon's artist follow list and
    automatically sync their Apple Music IDs to the odesli database.

    Works with catalog playlists (pl.xxx) and personal library playlists (p.xxx).

    Examples:\n
      ammon playlist extract-artists pl.4b364b8b182f4115acbf6deb83bd5222\n
      ammon playlist extract-artists "https://music.apple.com/library/playlist/p.xxx" --follow
    """
    playlist_id = _parse_playlist_id(playlist_id)
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])

    tracks = _api.get_playlist_tracks(apple_api, playlist_id)
    if not tracks:
        click.echo("  No tracks found or playlist unavailable.")
        conn.close()
        sys.exit(1)

    # Collect unique artist IDs with individual names
    artist_ids = {}
    for t in tracks:
        name_map = t.get("artist_names", {})
        for aid in t.get("artist_ids", []):
            if aid not in artist_ids:
                artist_ids[aid] = name_map.get(aid) or t["artist_name"]

    click.echo(f"\n  Found {len(artist_ids)} unique artists in playlist\n")

    # Connect to odesli DB for sync (if available)
    odesli_conn = None
    if follow:
        odesli_db = Path.home() / ".odesli" / "music.db"
        if odesli_db.exists():
            import sqlite3
            odesli_conn = sqlite3.connect(str(odesli_db), timeout=10)
            odesli_conn.row_factory = sqlite3.Row

    added = odesli_added = 0
    for apple_id, name in artist_ids.items():
        click.echo(f"  {apple_id:<15} {name}")
        if follow:
            # Add to ammon
            if not _db.get_artist(conn, apple_id):
                _db.add_artist(conn, apple_id, name)
                added += 1

            # Sync to odesli
            if odesli_conn:
                try:
                    # Find or create artist in odesli
                    row = odesli_conn.execute(
                        "SELECT id FROM artists WHERE name = ? COLLATE NOCASE", (name,)
                    ).fetchone()
                    if not row:
                        cur = odesli_conn.execute(
                            "INSERT OR IGNORE INTO artists (name, mbid) VALUES (?, '')", (name,)
                        )
                        artist_db_id = cur.lastrowid or odesli_conn.execute(
                            "SELECT id FROM artists WHERE name=?", (name,)
                        ).fetchone()["id"]
                    else:
                        artist_db_id = row["id"]

                    odesli_conn.execute("""
                        INSERT INTO artist_platforms (artist_id, platform, platform_id, url)
                        VALUES (?, 'Apple Music', ?, ?)
                        ON CONFLICT(artist_id, platform) DO UPDATE SET
                            platform_id = excluded.platform_id,
                            url = excluded.url
                    """, (artist_db_id, apple_id,
                          f"https://music.apple.com/us/artist/{apple_id}"))
                    odesli_added += 1
                except Exception:
                    pass

    if odesli_conn:
        odesli_conn.commit()
        odesli_conn.close()

    if follow:
        click.echo(f"\n  + Added {added} new artists to ammon.")
        click.echo(f"  + Synced {odesli_added} artists to odesli DB.")
    else:
        click.echo(f"\n  Run with --follow to add these artists to ammon + odesli.")

    conn.close()


@cli.command(name="download-pending")
@click.option("--force", "-f", is_flag=True, help="Re-download all albums, including already downloaded ones")
@click.pass_context
def download_pending(ctx, force):
    """Download albums detected by refresh.

    By default downloads only pending (not yet downloaded) albums.
    Use --force to re-download everything in the DB regardless of status
    (useful after wiping your music library).

    Examples:\n
      ammon download-pending\n
      ammon download-pending --force
    """
    from . import downloader as _dl
    conn = _get_conn(ctx.obj["db"])

    if force:
        rows = conn.execute("SELECT * FROM albums ORDER BY release_date DESC").fetchall()
        albums = [dict(r) for r in rows]
        label = "all"
    else:
        albums = _db.get_pending_downloads(conn)
        label = "pending"

    if not albums:
        click.echo(f"  No {label} albums.")
        conn.close()
        return

    click.echo(f"\n  Downloading {len(albums)} {label} album(s)...\n")
    ok = errors = 0
    for i, album in enumerate(albums, 1):
        click.echo(f"  [{i}/{len(albums)}] {album['name']} ({album['apple_id']})")
        success, msg = _dl.download_album(album["apple_id"], album.get("storefront") or "us")
        if success:
            _db.mark_downloaded(conn, album["apple_id"])
            ok += 1
            click.echo(f"    + OK")
        else:
            errors += 1
            click.echo(f"    x {msg}")

    conn.close()
    click.echo(f"\n  Done — {ok} downloaded, {errors} errors.")


@cli.command(name="export")
@click.option("--output", "-o", default="ammon_artists.csv", metavar="FILE", help="Output CSV path (default: ammon_artists.csv)")
@click.option("--with-odesli", is_flag=True, help="Also include Tidal/Deezer/Spotify IDs from odesli DB")
@click.pass_context
def export_artists(ctx, output, with_odesli):
    """Export followed artists and their Apple Music IDs to a CSV file.

    Use --with-odesli to enrich the export with Tidal, Deezer and
    Spotify IDs from the odesli cross-platform database.

    Examples:\n
      ammon export\n
      ammon export --with-odesli -o my_artists.csv
    """
    import csv, sqlite3

    conn = _get_conn(ctx.obj["db"])
    artists = _db.get_all_artists(conn)
    conn.close()

    # Load odesli platform IDs if requested
    odesli_data = {}
    if with_odesli:
        odesli_db = Path.home() / ".odesli" / "music.db"
        if odesli_db.exists():
            oc = sqlite3.connect(str(odesli_db))
            oc.row_factory = sqlite3.Row
            for r in oc.execute("""
                SELECT a.name, ap.platform, ap.platform_id
                FROM artist_platforms ap
                JOIN artists a ON a.id = ap.artist_id
                WHERE ap.platform IN ('TIDAL','Deezer','Spotify','Apple Music')
            """).fetchall():
                key = r["name"].lower().strip()
                odesli_data.setdefault(key, {})[r["platform"]] = r["platform_id"]
            oc.close()

    headers = ["Name", "Apple Music ID"]
    if with_odesli:
        headers += ["TIDAL ID", "Deezer ID", "Spotify ID"]

    output_path = Path(output)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for a in artists:
            row = [a["name"], a["apple_id"]]
            if with_odesli:
                extra = odesli_data.get(a["name"].lower().strip(), {})
                row += [
                    extra.get("TIDAL", ""),
                    extra.get("Deezer", ""),
                    extra.get("Spotify", ""),
                ]
            w.writerow(row)

    click.echo(f"  Exported {len(artists)} artists to {output_path.resolve()}")


def main():
    cli()


if __name__ == "__main__":
    main()
