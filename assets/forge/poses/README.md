# assets/forge/poses

Hier legst du die **in Gemini generierten FORGE-Pose-Stills** ab (PNG). Von hier liest die
Pipeline sie als Video-Hintergrund — `footage.prepare_background` akzeptiert jetzt Bilder:
ein Ordner wird zur Slideshow (je Pose ~3 s, zyklisch auf die Voiceover-Länge), ein
Einzelbild wird statisch.

## So läuft die Übergabe
1. Pose in Gemini generieren (Referenz `reference.png` anhängen — siehe Skill
   `image-prompts.md`), **9:16, Ganzkörper, Figur zentriert**.
2. Hier ablegen, Namensschema: `forge_<slug>_9x16.png` (z. B. `forge_lunge_9x16.png`).
3. Committen + pushen. PNGs werden von git getrackt (nicht in `.gitignore`).
4. Claude baut daraus das Video:
   ```bash
   yt-automation from-text skript.txt --format shorts \
     --background ./assets/forge/poses --word-captions
   ```

## Für einen einzelnen Short
Nur die 1–3 Posen in einen eigenen Unterordner legen und den als `--background` geben,
z. B. `./assets/forge/poses/legday/`.
