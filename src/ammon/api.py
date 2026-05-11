"""Apple Music API wrapper for AMMON."""
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Bootstrap gamdl from OrpheusDL
GAMDL_PATH = Path("C:/OrpheusDL/modules/applemusic/gamdl")
if str(GAMDL_PATH) not in sys.path:
    sys.path.insert(0, str(GAMDL_PATH))

from gamdl.apple_music_api import AppleMusicApi

DEFAULT_COOKIES = Path("C:/OrpheusDL/config/cookies.txt")
STOREFRONTS_CACHE: list[str] = []


def get_api(cookies_path: Path = DEFAULT_COOKIES) -> AppleMusicApi:
    return AppleMusicApi(cookies_path=cookies_path, language="en-US")


def get_all_storefronts(api: AppleMusicApi) -> list[str]:
    global STOREFRONTS_CACHE
    if STOREFRONTS_CACHE:
        return STOREFRONTS_CACHE
    try:
        resp = api.session.get(
            "https://amp-api.music.apple.com/v1/storefronts",
            params={"limit": 200}
        )
        STOREFRONTS_CACHE = [s["id"] for s in resp.json().get("data", [])]
    except Exception:
        STOREFRONTS_CACHE = ["us"]
    return STOREFRONTS_CACHE


def get_artist_name(api: AppleMusicApi, artist_id: str) -> str | None:
    for sf in [api.storefront.lower(), "us"]:
        try:
            api.storefront = sf.upper()
            resp = api.session.get(
                f"https://amp-api.music.apple.com/v1/catalog/{sf}/artists/{artist_id}",
                params={"l": "en-US"}
            )
            if resp.status_code == 200:
                data = resp.json()["data"][0]
                return data["attributes"].get("name")
        except Exception:
            continue
    return None


_RELEASE_SUFFIXES = (
    " - Single", " - single",
    " - EP", " - ep",
    " - Album", " - album",
)

def _strip_release_suffix(name: str) -> str:
    """Remove ' - Single', ' - EP', etc. from album names — matches Orpheus behaviour."""
    for suffix in _RELEASE_SUFFIXES:
        if name.endswith(suffix):
            return name[: len(name) - len(suffix)].strip()
    return name


def _parse_album_attrs(album: dict, storefront: str) -> dict:
    attrs = album.get("attributes", {})
    return {
        "apple_id":       album["id"],
        "name":           _strip_release_suffix(attrs.get("name", "")),
        "release_date":   attrs.get("releaseDate", ""),
        "storefront":     storefront,
        "is_single":      attrs.get("isSingle", False),
        "is_compilation": attrs.get("isCompilation", False),
        "track_count":    attrs.get("trackCount", 0),
        "kind":           (attrs.get("playParams", {}) or {}).get("kind", ""),
    }


def _fetch_albums_storefront(api: AppleMusicApi, artist_id: str, storefront: str) -> dict:
    """Fetch all album IDs for an artist in one storefront. Returns {album_id: album_data}."""
    result = {}
    try:
        url = f"https://amp-api.music.apple.com/v1/catalog/{storefront}/artists/{artist_id}/albums"
        params = {"limit": 100, "l": "en-US", "include": "artists"}
        resp = api.session.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return result
        data = resp.json()
        for album in data.get("data", []):
            result[album["id"]] = _parse_album_attrs(album, storefront)
        next_path = data.get("next")
        while next_path:
            resp = api.session.get(
                f"https://amp-api.music.apple.com{next_path}", timeout=10
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for album in data.get("data", []):
                result.setdefault(album["id"], _parse_album_attrs(album, storefront))
            next_path = data.get("next")
    except Exception:
        pass
    return result


def get_artist_all_albums(api: AppleMusicApi, artist_id: str,
                          storefronts: list[str] | None = None,
                          workers: int = 25) -> dict:
    """Scan all storefronts and return merged {album_id: album_data}.

    Priority when the same album appears in multiple storefronts:
    'us' > primary > any foreign storefront.
    This ensures isSingle/trackCount/playParams are consistent with Orpheus.
    """
    if storefronts is None:
        storefronts = get_all_storefronts(api)

    primary = api.storefront.lower()
    ordered = [primary, "us"] + [s for s in storefronts if s not in (primary, "us")]

    # Collect ALL results first, keyed by storefront
    results_by_sf: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_albums_storefront, api, artist_id, sf): sf
            for sf in ordered
        }
        for future in as_completed(futures):
            sf = futures[future]
            results_by_sf[sf] = future.result()

    # Merge in priority order: us > primary > foreign
    priority = ["us"] + ([primary] if primary != "us" else []) + \
               [s for s in ordered if s not in ("us", primary)]

    all_albums: dict = {}
    for sf in priority:
        for album_id, album_data in results_by_sf.get(sf, {}).items():
            all_albums.setdefault(album_id, album_data)

    return all_albums


def _is_library_playlist(playlist_id: str) -> bool:
    return playlist_id.startswith("p.")


def _playlist_base_url(api: AppleMusicApi, playlist_id: str) -> str:
    if _is_library_playlist(playlist_id):
        return f"https://amp-api.music.apple.com/v1/me/library/playlists/{playlist_id}"
    return f"https://amp-api.music.apple.com/v1/catalog/{api.storefront.lower()}/playlists/{playlist_id}"


def get_playlist_info(api: AppleMusicApi, playlist_id: str) -> dict | None:
    """Fetch playlist name and basic info. Handles both catalog (pl.) and library (p.) playlists."""
    try:
        resp = api.session.get(
            _playlist_base_url(api, playlist_id),
            params={"l": "en-US"}
        )
        if resp.status_code == 200:
            data = resp.json()["data"][0]
            attrs = data.get("attributes", {})
            return {"apple_id": playlist_id, "name": attrs.get("name", playlist_id)}
    except Exception:
        pass
    return None


def get_playlist_tracks(api: AppleMusicApi, playlist_id: str) -> list[dict]:
    """Fetch all tracks in a playlist. Returns list of track dicts."""
    tracks = []
    is_lib = _is_library_playlist(playlist_id)
    base_url = _playlist_base_url(api, playlist_id) + "/tracks"
    base_params = {"limit": 100, "l": "en-US",
                   "include": "artists,catalog" if is_lib else "artists"}
    offset = 0
    url = base_url
    try:
        while url:
            params = {**base_params, "offset": offset} if offset > 0 else base_params
            resp = api.session.get(base_url, params=params, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            batch = data.get("data", [])
            if not batch:
                break
            for track in batch:
                attrs = track.get("attributes", {})
                rels  = track.get("relationships", {})

                # Library playlist tracks: artist IDs live inside catalog relationship
                catalog_items = rels.get("catalog", {}).get("data", [])
                if catalog_items:
                    catalog_rels = catalog_items[0].get("relationships", {})
                    artist_rels  = catalog_rels.get("artists", {}).get("data", [])
                    catalog_id   = catalog_items[0].get("id", track["id"])
                else:
                    artist_rels = rels.get("artists", {}).get("data", [])
                    catalog_id  = track["id"]

                # Build {artist_id: artist_name} using individual names from attributes
                artist_map = {}
                for a in artist_rels:
                    if "id" not in a:
                        continue
                    individual_name = a.get("attributes", {}).get("name", "")
                    artist_map[a["id"]] = individual_name or attrs.get("artistName", "")

                tracks.append({
                    "track_id":    catalog_id,
                    "track_name":  attrs.get("name", ""),
                    "artist_name": attrs.get("artistName", ""),
                    "artist_ids":  list(artist_map.keys()),
                    "artist_names": artist_map,
                })
            offset += len(batch)
            total = data.get("meta", {}).get("total", 0)
            url = base_url if offset < total else None
    except Exception:
        pass
    return tracks


def get_release_type(album_data: dict) -> str:
    """Mirrors Orpheus's get_album_info() release type logic exactly."""
    if album_data.get("is_compilation"):
        return "COMPILATION"
    if album_data.get("is_single") or album_data.get("track_count") == 1:
        return "SINGLE"
    kind = (album_data.get("kind") or "").lower()
    return {"album": "ALBUM", "single": "SINGLE", "ep": "EP",
            "compilation": "COMPILATION"}.get(kind, "ALBUM")
