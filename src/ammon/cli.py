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


def main():
    cli()


if __name__ == "__main__":
    main()
