# Channel-OS – Batch, Cadence, Anbindung an die Repo-Pipeline

## Batch-Workflow (so wird's effizient)
Nicht Post-für-Post denken, sondern in Batches – die Figur ist gesperrt, also skaliert es:
1. **30 Ideen** sammeln (nach Pillar-Mix, siehe `content-templates.md`).
2. **30 Posen** ableiten (je Idee 1 Pose aus dem Pose-Template, `image-prompts.md`).
3. **30 Arts** generieren (Referenz-Anker + Style-Lock, alle in einem Rutsch).
4. **In Templates** ziehen (Canva-Brand-Template, nur Slots befüllen).
5. **In die Queue** (planen, siehe Cadence).

## Cadence
- Stetiger Start: 1 Post/Tag, davon 2–3 Shorts/Woche.
- Reichweiten-Pillar (Humor) auf die stärksten Tage legen.
- Wiederkehrende Serien helfen (z.B. "Move-Monday", "Form-Friday").

## Datei- & Namens-Schema
```
content/
  YYYY-MM-DD_{pillar}_{slug}/
    art.png            # generierte Mascot-Illustration
    poster.png         # finales Canva-Export (4:5)
    short.mp4          # optional, aus yt-automation
    caption.txt        # Caption + Hashtags
```
Beispiel-Slug: `2026-06-22_humor_first-set-vs-last-set`.

## Hashtag-Sets (rotieren, nicht spammen)
- Core: `#calisthenics #homeworkout #fitnessmotivation #bodyweight`
- Pillar-spezifisch (Beispiele): Legs → `#legday #legworkout`; Pull → `#pullups #backday`.
- Brand: ein eigener, konsistenter Tag, z.B. `#forgedaily` (deiner – nicht der der Vorlage).

## Short-Pipeline (Anbindung an dieses Repo)
Voll automatisch über die bestehende CLI (siehe `README.md`):
1. Skript als `.txt` schreiben (erster Absatz = Hook, letzter = CTA; Format siehe
   `skript_beispiel.txt`). Eigene Texte, kein Fremdmaterial.
2. Mascot-Art als Hintergrund/Loop ablegen (z.B. `assets/character/` oder ein kurzer
   Pan/Zoom-Clip der Illustration).
3. Bauen:
   ```bash
   yt-automation from-text skript.txt --format shorts \
     --background ./assets/character --word-captions
   ```
   → edge-tts spricht, Whisper brennt Word-Captions, FFmpeg rendert 9:16.
4. Voice-Vibe: knapp, ruhig, hart – passend zu FORGE. Musik dezent, Auto-Ducking ist an.

## Definition of Done (pro Post)
- [ ] Pillar + Hook gewählt (eigener Text).
- [ ] Art mit Referenz-Anker + Style-Lock generiert, Konsistenz-Checkliste bestanden.
- [ ] Im Brand-Template, Logo-Ecke gesetzt, Palette eingehalten.
- [ ] Caption + Hashtags geschrieben.
- [ ] `copyright-safety.md` einmal durchgegangen.
