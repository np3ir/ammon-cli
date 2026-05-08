# AMMON — Apple Music Monitor

Standalone CLI tool to monitor Apple Music artists and download new releases via OrpheusDL.

## Stack
- Python 3.11+, Click, SQLite
- Depends on OrpheusDL at `C:\OrpheusDL\` for downloading
- Uses gamdl (bundled in OrpheusDL) for Apple Music API access
- Cookies: `C:\OrpheusDL\config\cookies.txt`

## DB
- `~/.ammon/ammon.db` — artists + albums SQLite

## Install
```
pip install -e .
```

## Commands
- `ammon follow <apple_id>` — seguir artista
- `ammon unfollow <apple_id>`
- `ammon list` — listar artistas seguidos
- `ammon refresh [--download] [--since YYYY-MM-DD] [--artist ID]`
- `ammon status [--pending]`
- `ammon import-odesli` — importar IDs de Apple Music desde odesli DB
- `ammon download-pending` — descargar álbumes pendientes
