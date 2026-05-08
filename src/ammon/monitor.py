"""Core monitoring logic for AMMON."""
from . import api as _api, db as _db, downloader as _dl
from pathlib import Path


def refresh_artist(conn, apple_api, artist_id: str, download: bool = False,
                   since: str | None = None, verbose: bool = True) -> dict:
    """
    Check for new albums for one artist.
    Returns {"new": int, "downloaded": int, "errors": int}.
    """
    artist = _db.get_artist(conn, artist_id)
    name = artist["name"] if artist else artist_id
    if verbose:
        print(f"  Checking {name} ({artist_id})...")

    albums = _api.get_artist_all_albums(apple_api, artist_id)
    new = downloaded = errors = 0

    for album_id, album_data in albums.items():
        release_date = album_data.get("release_date", "")
        if since and release_date and release_date < since:
            continue

        release_type = _api.get_release_type(album_data)
        is_new = _db.add_album(
            conn,
            apple_id       = album_id,
            artist_apple_id= artist_id,
            name           = album_data.get("name", ""),
            release_date   = release_date,
            storefront     = album_data.get("storefront", "us"),
            release_type   = release_type,
        )

        if is_new:
            new += 1
            album_name = album_data.get("name", album_id)
            if verbose:
                print(f"    + NEW: {album_name} ({release_date}) [{release_type}]")

            if download:
                ok, msg = _dl.download_album(album_id, album_data.get("storefront", "us"))
                if ok:
                    _db.mark_downloaded(conn, album_id)
                    downloaded += 1
                    if verbose:
                        print(f"      + Downloaded")
                else:
                    errors += 1
                    if verbose:
                        print(f"      x Error: {msg}")

    _db.update_last_check(conn, artist_id)
    return {"new": new, "downloaded": downloaded, "errors": errors}
