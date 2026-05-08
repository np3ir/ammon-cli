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
@click.argument("artist_id")
@click.pass_context
def follow(ctx, artist_id):
    """Follow an Apple Music artist by ID."""
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
@click.argument("artist_id")
@click.pass_context
def unfollow(ctx, artist_id):
    """Stop following an Apple Music artist."""
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
@click.option("--download", "-d", is_flag=True, help="Download new releases automatically")
@click.option("--since", "-s", default=None, metavar="YYYY-MM-DD", help="Only check releases from this date")
@click.option("--artist", "-a", default=None, metavar="APPLE_ID", help="Refresh only this artist")
@click.pass_context
def refresh(ctx, download, since, artist):
    """Check for new releases from followed artists."""
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
@click.option("--pending", "-p", is_flag=True, help="Show pending downloads")
@click.pass_context
def status(ctx, pending):
    """Show database statistics."""
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
@click.option("--db-path", default=None, metavar="PATH", help="odesli DB path")
@click.pass_context
def import_odesli(ctx, db_path):
    """Import Apple Music artist IDs from odesli database."""
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
@click.argument("playlist_id")
@click.pass_context
def playlist_follow(ctx, playlist_id):
    playlist_id = _parse_playlist_id(playlist_id)
    """Follow a playlist by ID (e.g. pl.xxx or catalog album ID)."""
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
@click.argument("playlist_id")
@click.pass_context
def playlist_unfollow(ctx, playlist_id):
    """Stop following a playlist."""
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
@click.option("--download", "-d", is_flag=True, help="Download new tracks automatically")
@click.option("--playlist", "-p", default=None, metavar="ID", help="Refresh only this playlist")
@click.pass_context
def playlist_refresh(ctx, download, playlist):
    """Check followed playlists for new tracks."""
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
@click.argument("playlist_id")
@click.option("--follow", "-f", is_flag=True, help="Add extracted artists to ammon follow list")
@click.pass_context
def playlist_extract_artists(ctx, playlist_id, follow):
    """Extract all artists from a playlist and optionally follow them."""
    playlist_id = _parse_playlist_id(playlist_id)
    conn = _get_conn(ctx.obj["db"])
    apple_api = _get_api(ctx.obj["cookies"])

    tracks = _api.get_playlist_tracks(apple_api, playlist_id)
    if not tracks:
        click.echo("  No tracks found or playlist unavailable.")
        conn.close()
        sys.exit(1)

    # Collect unique artist IDs
    artist_ids = {}
    for t in tracks:
        for aid in t.get("artist_ids", []):
            if aid not in artist_ids:
                artist_ids[aid] = t["artist_name"]

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
@click.pass_context
def download_pending(ctx):
    """Download all pending (not yet downloaded) albums."""
    from . import downloader as _dl
    conn = _get_conn(ctx.obj["db"])
    pending = _db.get_pending_downloads(conn)

    if not pending:
        click.echo("  No pending downloads.")
        conn.close()
        return

    click.echo(f"\n  Downloading {len(pending)} pending album(s)...\n")
    ok = errors = 0
    for i, album in enumerate(pending, 1):
        click.echo(f"  [{i}/{len(pending)}] {album['name']} ({album['apple_id']})")
        success, msg = _dl.download_album(album["apple_id"], album["storefront"] or "us")
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
@click.option("--output", "-o", default="ammon_artists.csv", metavar="FILE", help="Output CSV file")
@click.option("--with-odesli", is_flag=True, help="Include Tidal/Deezer/Spotify IDs from odesli DB")
@click.pass_context
def export_artists(ctx, output, with_odesli):
    """Export followed artists and their IDs to a CSV file."""
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
    with open(output_path, "w", newline="", encoding="utf-8") as f:
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
