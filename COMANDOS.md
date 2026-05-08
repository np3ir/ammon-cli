# AMMON — Comandos

**AMMON** (Apple Music Monitor) monitorea artistas en Apple Music y descarga nuevos lanzamientos automáticamente via OrpheusDL.

- **DB:** `~/.ammon/ammon.db`
- **Cookies:** `C:/OrpheusDL/config/cookies.txt`
- **Descarga via:** `orpheus` (OrpheusDL en `C:/OrpheusDL/`)

---

## Opciones globales

```
ammon [--db PATH] [--cookies PATH] <comando>
```

| Opción | Descripción |
|--------|-------------|
| `--db PATH` | Ruta alternativa a la DB (default: `~/.ammon/ammon.db`) |
| `--cookies PATH` | Ruta alternativa a `cookies.txt` de Apple Music |
| `--version` | Muestra la versión instalada |

---

## Artistas

### `ammon follow <apple_id>`
Sigue un artista de Apple Music por su ID numérico.
Verifica que el artista existe antes de agregarlo.

```bash
ammon follow 1445958214
ammon follow 159260351
```

---

### `ammon unfollow <apple_id>`
Deja de seguir un artista.

```bash
ammon unfollow 1445958214
```

---

### `ammon list`
Lista todos los artistas seguidos con su Apple ID y fecha del último chequeo.

```bash
ammon list
```

---

### `ammon refresh`
Chequea nuevos lanzamientos de todos los artistas seguidos.
Escanea los **167 storefronts** de Apple Music en paralelo para catálogo completo.

```bash
# Solo detectar — no descargar
ammon refresh

# Detectar y descargar automáticamente
ammon refresh --download

# Solo un artista específico
ammon refresh --artist 1445958214

# Solo lanzamientos desde una fecha
ammon refresh --since 2025-01-01

# Combinado
ammon refresh --download --since 2024-06-01 --artist 159260351
```

| Opción | Descripción |
|--------|-------------|
| `--download, -d` | Descarga los nuevos lanzamientos via orpheus |
| `--since YYYY-MM-DD` | Solo chequea lanzamientos desde esta fecha |
| `--artist ID` | Solo refresca este artista |

---

### `ammon status`
Muestra estadísticas de la DB: artistas, álbumes, descargas pendientes.

```bash
ammon status

# Ver lista de álbumes pendientes de descarga
ammon status --pending
```

---

### `ammon download-pending`
Descarga todos los álbumes que fueron detectados pero no descargados aún.

```bash
ammon download-pending
```

---

### `ammon import-odesli`
Importa artistas con Apple Music ID desde la DB de **odesli** (`~/.odesli/music.db`).
Solo agrega los que no están aún en ammon. Deduplica por Apple ID.

```bash
ammon import-odesli

# DB de odesli en ruta alternativa
ammon import-odesli --db-path "D:/music.db"
```

---

## Playlists

### `ammon playlist follow <id_o_url>`
Sigue una playlist para monitorear nuevas canciones.
Siembra los tracks actuales — **solo alerta sobre adiciones futuras**.
Acepta URL completa o ID directamente.
Soporta playlists del catálogo (`pl.xxx`) y de biblioteca personal (`p.xxx`).

```bash
# Por ID
ammon playlist follow pl.4b364b8b182f4115acbf6deb83bd5222

# Por URL de catálogo
ammon playlist follow "https://music.apple.com/us/playlist/dale-play/pl.4b364b8b182f4115acbf6deb83bd5222"

# Por URL de biblioteca personal
ammon playlist follow "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y"
```

---

### `ammon playlist unfollow <id_o_url>`
Deja de seguir una playlist.

```bash
ammon playlist unfollow pl.4b364b8b182f4115acbf6deb83bd5222
ammon playlist unfollow "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y"
```

---

### `ammon playlist list`
Lista todas las playlists seguidas.

```bash
ammon playlist list
```

---

### `ammon playlist refresh`
Chequea las playlists seguidas por tracks nuevos.

```bash
# Solo detectar
ammon playlist refresh

# Detectar y descargar tracks nuevos
ammon playlist refresh --download

# Solo una playlist
ammon playlist refresh --playlist pl.4b364b8b182f4115acbf6deb83bd5222
```

| Opción | Descripción |
|--------|-------------|
| `--download, -d` | Descarga los tracks nuevos via orpheus |
| `--playlist ID` | Solo refresca esta playlist |

---

### `ammon playlist extract-artists <id_o_url>`
Extrae todos los artistas únicos de una playlist.
Cuando se usa `--follow`:
- Agrega los artistas a la lista de seguimiento de ammon
- **Sincroniza automáticamente los Apple IDs a la DB de odesli**
- Para playlists de biblioteca personal, extrae IDs desde el catálogo (no los IDs de biblioteca)

```bash
# Solo ver qué artistas hay
ammon playlist extract-artists "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y"

# Agregar a ammon + sincronizar a odesli
ammon playlist extract-artists "https://music.apple.com/library/playlist/p.ldvAJK1coEp23Y" --follow

# Playlist de catálogo
ammon playlist extract-artists pl.4b364b8b182f4115acbf6deb83bd5222 --follow
```

---

## Flujo típico

```bash
# 1. Importar artistas desde odesli (Apple IDs ya conocidos)
ammon import-odesli

# 2. Extraer artistas de tus playlists
ammon playlist follow "https://music.apple.com/library/playlist/p.xxx"
ammon playlist extract-artists "https://music.apple.com/library/playlist/p.xxx" --follow

# 3. Chequear nuevos lanzamientos
ammon refresh --download

# 4. Ver estado
ammon status --pending

# 5. Descargar lo que quedó pendiente
ammon download-pending

# 6. Monitorear playlists
ammon playlist refresh --download
```

---

## Notas

- Los **cookies.txt** de Apple Music expiran cada ~30 días. Cuando aparezcan errores 401, renueva exportando desde el browser.
- El refresh de artistas escanea 167 storefronts en paralelo (25 workers). Para artistas con catálogo grande puede tardar varios segundos.
- Los álbumes encontrados en storefronts extranjeros que no estén disponibles en tu región son omitidos automáticamente (pre-flight check).
- AMMON llama a `orpheus.py` en `C:/OrpheusDL/` para descargar. Asegúrate de que OrpheusDL esté configurado correctamente.
