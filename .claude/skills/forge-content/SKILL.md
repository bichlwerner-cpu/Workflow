---
name: forge-content
description: >
  Produziere Fitness-/Calisthenics-Content im Maskottchen-Format (wie der "Yellow
  Dude"-Channel), aber mit der EIGENEN Marke FORGE – einem crimson-roten Mascot mit
  schwach glühenden Augen und getapten Knöcheln. Nutze diese Skill, wenn der User einen
  Post, ein Carousel oder ein Short erstellen, einen konsistenten Charakter generieren
  oder einen Content-Batch planen will. Sie liefert die komplette Pipeline: Charakter-
  Konsistenz, Bild-Prompts, Caption-Vorlagen, Branding und Veröffentlichung. Auslöser u.a.:
  "neuen Post erstellen", "Short bauen", "Mascot generieren", "Leg-Day Carousel", "Content
  planen", "Channel reproduzieren".
---

# FORGE Content Factory

Das ist **ein** System, um den Maskottchen-Fitness-Channel als Format zu reproduzieren –
mit deiner eigenen Marke statt einer Kopie. Das Format (farbiges Muskel-Mascot macht
Calisthenics + fette Captions/Tipps) ist Genre und frei nutzbar. Geschützt ist die
konkrete Figur, der Name, das Logo, exakte Posen und Caption-Texte des Originals. Deshalb
baut diese Skill eine **eigenständige Figur (FORGE)** und eigene Texte – das ist der
ganze Trick, um nicht zu "copyrighten". Details: `copyright-safety.md` (immer einhalten).

## Der Kern: warum das überhaupt funktioniert

Der einzige echte Engpass beim Nachbauen so eines Channels ist **Charakter-Konsistenz** –
dass das Mascot in 300 Posts gleich aussieht. Claude malt die Illustrationen nicht. Diese
Skill löst das mit *genau einem* Weg: **Reference-Anchored Generation**.

1. Du erzeugst **einmal** ein Master-Referenzblatt der Figur.
2. Dieses Bild ist ab dann der Anker. Für jeden Post fütterst du Referenz + Pose-Prompt +
   fixen Style-Lock in einen Bildgenerator → gleiche Figur, neue Pose.
3. Der Style-Lock-String bleibt **wortwörtlich** in jedem Prompt. Das hält den Look stabil.

Mehr macht das System nicht kompliziert. Ein Anker, ein Style-Lock, fertig.

## Die Pipeline (immer diese Reihenfolge)

```
[1] Figur sperren     →  einmalig: Master-Referenzblatt erzeugen
[2] Idee → Pose        →  Content-Pillar + Hook wählen (content-templates.md)
[3] Art generieren     →  Referenz + Pose-Prompt + Style-Lock (image-prompts.md)
[4] Branding           →  Art in Canva-Brand-Template, Caption + Logo drauf
[5] Short (optional)   →  yt-automation-Pipeline: Skript → edge-tts → Captions → MP4
[6] Batch & Posten     →  Cadence + Hashtags + Planung (channel-os.md)
```

## Toolstack (konkret – was du wofür benutzt)
| Aufgabe                         | Tool                                             |
|---------------------------------|--------------------------------------------------|
| FORGE-Posen / Illustrationen    | **Gemini Ultra → Nano Banana Pro** (Bild-Engine) |
| Ideen, Hooks, Captions, Steuerung| **Claude**                                       |
| Branding / Layout / Poster      | **Canva** (Brand-Template)                        |
| Short-Video (Voice/Captions/Render)| **dieses Repo** (edge-tts + Whisper + FFmpeg)   |
| Posten & Planen                 | **Buffer** (oder OneUp für Multi-Plattform-Shorts)|

Alles Schwere läuft über Abos, die du schon hast (Gemini Ultra + Claude). ~0 € Mehrkosten.

## Schritt für Schritt

### [1] Figur einmalig sperren
- Lies `character-bible.md`. Das ist die verbindliche Spezifikation von FORGE.
- Nimm den **Master-Reference-Sheet-Prompt** aus `image-prompts.md`, generiere, iteriere
  bis es "die Eine" ist. Speichere als `assets/character/reference.png`.
- Ab jetzt nie wieder die Figur neu erfinden – nur noch anchorn.

### [2] Idee → Pose
- Wähle einen Content-Pillar und eine Hook aus `content-templates.md` (eigener Hook-Bank,
  keine Original-Sprüche übernehmen).
- Leite daraus ab, welche **Pose/Szene** das Mascot zeigen soll (z.B. "Ausfallschritt",
  "hängt erschöpft an der Klimmzugstange").

### [3] Art generieren
- Aus `image-prompts.md`: `Pose-Prompt-Template` + `Style-Lock` + `Negative-Prompt`.
- Immer mit `reference.png` als Charakter-Anker generieren.
- Format passend zum Ziel: Poster 4:5, Short/Reel 9:16, Carousel 1:1.

### [4] Branding
- Empfohlener (einziger) Weg: **Canva-Brand-Template**. Lege einmal ein Brand-Kit mit der
  FORGE-Palette + Logo + Font an, dann pro Post nur Art + Caption einfüllen und exportieren.
- Die Canva-MCP-Tools sind verfügbar (Brand-Template anlegen, Design erzeugen, exportieren).
- Layout-Spezifikation (Textplatzierung, Sicherheitsränder, Logo-Ecke): `content-templates.md`.

### [5] Short bauen (optional, voll automatisch)
- Nutze die bestehende Repo-Pipeline (`README.md`): Skript-`.txt` schreiben →
  `yt-automation from-text skript.txt --format shorts --background ./assets/character ...`.
- Das Mascot-Bild/-Loop wird zum 9:16-Hintergrund, edge-tts spricht, Whisper brennt
  Word-Captions. Caption-Stil + Voice-Vibe: `channel-os.md`.

### [6] Batch & Posten
- `channel-os.md`: Pillars-Mix, Posting-Cadence, Datei-/Namens-Schema, Hashtag-Sets,
  Batch-Workflow (30 Ideen → 30 Posen → 30 Arts → Templates → Queue).

## Referenz-Dateien
- `character-bible.md` – wer FORGE ist (verbindlich, das ist deine IP).
- `image-prompts.md` – Master-Referenz-Prompt, Pose-Template, Style-Lock, Negative-Prompt.
- `content-templates.md` – Content-Pillars, Hook-Bank, Caption-Formeln, Layout.
- `channel-os.md` – Cadence, Batching, Naming, Hashtags, Short-Pipeline-Anbindung.
- `copyright-safety.md` – die Regeln, die FORGE rechtlich von der Vorlage trennen.

> Sprache: Skill-Doku ist Deutsch (wie das Repo). Bild-Prompts und Caption-Banks sind
> Englisch – Bildmodelle und die Reichweiten-Zielgruppe arbeiten so am besten.
