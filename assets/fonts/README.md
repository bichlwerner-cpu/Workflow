# Fonts

Drop a bold display font here for thumbnails, captions and chapter cards, e.g.:

- **Anton** — https://fonts.google.com/specimen/Anton (save as `Anton-Regular.ttf`)
- **Archivo Black** — https://fonts.google.com/specimen/Archivo+Black

Both are free for commercial use (OFL). Without a font here the pipeline falls
back to DejaVu Sans Bold (fine, but less "thumbnail-grade").

The lookup order is configured in `config/settings.yaml` under `fonts:`.
For burned-in subtitles, also set `subtitles.font_name` to the font's family
name (e.g. `Anton`) and make sure the font is installed system-wide so
ffmpeg/libass can find it.
