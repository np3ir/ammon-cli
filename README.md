# AMMON — Apple Music Monitor

A standalone CLI tool that monitors Apple Music artists and playlists for new releases, downloading them automatically via [OrpheusDL](https://github.com/OrfiDev/orpheusdl).

> Works alongside [odesli-cli](https://github.com/np3ir/odesli-cli) for cross-platform artist tracking.

---

## Features

- **Monitor artists** — follow Apple Music artists and detect new album releases
- **167 storefronts** — scans all Apple Music regions in parallel to find exclusive releases
- **Monitor playlists** — track catalog and personal library playlists for new tracks
- **Auto-download** — triggers OrpheusDL automatically when new content is detected
- **Import from odesli** — pulls Apple Music IDs from your odesli cross-platform DB
- **Extract artists from playlists** — builds your follow list from existing playlists
- **odesli sync** — writes Apple Music IDs back to odesli DB when extracting artists
- **Checkpoint support** — resumes interrupted operations without starting over

---

## Requirements

- Python 3.11+
- [OrpheusDL](https://github.com/OrfiDev/orpheusdl) installed at `C:/OrpheusDL/`
- Apple Music cookies (`C:/OrpheusDL/config/cookies.txt`) — renewed every ~30 days

---

## Install

```bash
git clone https://github.com/np3ir/ammon-cli
cd ammon-cli
pip install -e .
```

---

## Quick Start

```bash
# Follow an artist
ammon follow 159260351

# Follow a playlist (catalog or personal library)
ammon playlist follow "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y"

# Extract artists from a playlist and follow them (also syncs to odesli)
ammon playlist extract-artists "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y" --follow

# Import artists from odesli cross-platform DB
ammon import-odesli

# Check for new releases and download
ammon refresh --download

# Check playlists for new tracks and download
ammon playlist refresh --download
```

---

## Commands

### Artists

| Command | Description |
|---------|-------------|
| `ammon follow <id>` | Follow an artist by Apple Music ID |
| `ammon unfollow <id>` | Stop following an artist |
| `ammon list` | List followed artists |
| `ammon refresh` | Check for new releases (all 167 storefronts) |
| `ammon refresh --download` | Check and auto-download new releases |
| `ammon refresh --since YYYY-MM-DD` | Only check releases from this date |
| `ammon refresh --artist <id>` | Refresh a single artist |
| `ammon status` | Show DB statistics |
| `ammon status --pending` | Show pending downloads |
| `ammon download-pending` | Download pending albums |
| `ammon download-pending --force` | Re-download all albums (useful after wiping library) |
| `ammon download-pending --force --since YYYY-MM-DD` | Re-download all from date |
| `ammon download-pending --force --days N` | Re-download last N days |
| `ammon export` | Export artists to CSV (Apple Music IDs) |
| `ammon export --with-odesli` | Export with Tidal/Deezer/Spotify IDs |
| `ammon import-odesli` | Import Apple Music IDs from odesli DB |

### Playlists

| Command | Description |
|---------|-------------|
| `ammon playlist follow <id/url>` | Follow a playlist (seeds existing tracks) |
| `ammon playlist unfollow <id/url>` | Stop following a playlist |
| `ammon playlist list` | List followed playlists |
| `ammon playlist refresh` | Check playlists for new tracks |
| `ammon playlist refresh --download` | Check and auto-download new tracks |
| `ammon playlist extract-artists <id/url>` | List unique artists in a playlist |
| `ammon playlist extract-artists <id/url> --follow` | Follow artists + sync to odesli |

Accepts full Apple Music URLs or IDs directly. Supports both catalog playlists (`pl.xxx`) and personal library playlists (`p.xxx`).

---

## Global Options

```
ammon [--db PATH] [--cookies PATH] <command>
```

| Option | Description |
|--------|-------------|
| `--db PATH` | Custom DB path (default: `~/.ammon/ammon.db`) |
| `--cookies PATH` | Custom cookies.txt path |

---

## How It Works

1. **Artist monitoring** — fetches album lists from all 167 Apple Music storefronts in parallel using 25 concurrent workers. New album IDs are stored in the local DB. If an album from a foreign storefront is unavailable for streaming, it is automatically skipped.

2. **Playlist monitoring** — seeds all current tracks on first follow, then only alerts on future additions. Personal library playlists extract catalog IDs (not local library IDs) for correct artist resolution.

3. **Downloading** — calls `orpheus.py` from OrpheusDL as a subprocess with the album or track URL.

4. **odesli sync** — when extracting artists from a playlist with `--follow`, Apple Music IDs are written directly to odesli's `artist_platforms` table.

---

## Notes

- Apple Music cookies expire approximately every 30 days. Renew by exporting from your browser when 401 errors appear.
- AMMON stores its data in `~/.ammon/ammon.db` (SQLite).
- See [COMANDOS.md](COMANDOS.md) for full command documentation in Spanish.

---

## Related

- [odesli-cli](https://github.com/np3ir/odesli-cli) — Cross-platform artist ID lookup (MusicBrainz + Apple Music + Songlink)
- [OrpheusDL](https://github.com/OrfiDev/orpheusdl) — Multi-service music downloader
