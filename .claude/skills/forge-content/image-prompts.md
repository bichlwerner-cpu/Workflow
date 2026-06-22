# Bild-Prompts – der eine effiziente Weg

Methode: **Reference-Anchored Generation**. Erst einmalig ein Master-Referenzblatt, dann
für jeden Post die Referenz + Pose + Style-Lock. Prompts auf Englisch (Bildmodelle
verstehen das am besten). Funktioniert mit jedem Bildgenerator, der ein **Referenzbild für
Charakter-Konsistenz** akzeptiert (Image-to-Image / Character-Reference). Genau das ist die
Funktion, auf die es ankommt.

## Engine (konkret): Gemini Ultra → Nano Banana Pro
Standard-Bild-Engine ist **Nano Banana Pro** (Gemini 3 Pro Image) in der **Gemini-App** –
im Gemini-Ultra-Abo enthalten, 2026 führend bei Charakter-/Identitäts-Konsistenz. Kein
zusätzliches Bild-Abo. So läuft's:
1. **Einmal:** Master-Referenz-Prompt (Abschnitt C) → Modell *Nano Banana Pro* → bis FORGE
   sitzt → als `assets/character/reference.png` speichern.
2. **Pro Post:** in Gemini `reference.png` **anhängen** + Pose-Prompt (Abschnitt D) + den
   **Style-Lock** (Abschnitt A, wortwörtlich). Nano Banana Pro hält dabei das Subjekt und
   ändert nur die Pose.
3. Stil driftet? Style-Lock härter formulieren, Referenz immer mitgeben.

Captions/Hooks/Skripte kommen von **Claude**, Layout von **Canva** – Bilder von Gemini.

---

## A) Style-Lock (IMMER wortwörtlich anhängen)
> Dieser String darf sich nie ändern. Er ist der Garant für den einheitlichen Look.

```
STYLE: flat cel-shaded vector illustration, bold clean maroon outline, 2-3 shading
levels, crimson-red muscular mascot character (#D23B2E body, #7A1B16 shadows, #F26A4B
edge highlights), small faint glowing orange eyes (#FF8A3D), smooth featureless face,
white sport-tape wrapped knuckles, subtle forged-steel crack lines on forearms and shins,
plain black training shorts, athletic functional build, comic mascot, no photorealism,
no text, no watermark, clean solid-color background.
```

## B) Negative-Prompt (immer mit)
```
NEGATIVE: yellow body, white slit eyes, blank white eyes, realistic human face, photo,
3d render, extra fingers, deformed hands, logos, brand marks, text, watermark, signature,
busy background, gym equipment clutter.
```
> "yellow body" und "white slit eyes" stehen bewusst im Negativ – sie schieben dich aktiv
> von der Vorlage weg.

---

## C) Master-Referenzblatt (EINMALIG erzeugen → assets/character/reference.png)
Ziel: eine saubere, neutrale Definition der Figur als Anker für alles Weitere.

```
Character reference sheet of a single original fitness mascot named FORGE. Full-body
front view, neutral standing A-pose, plus a small secondary side view. Centered, evenly
lit, flat off-white (#F4EEE6) background. Show the character clearly and consistently.
+ [Style-Lock aus A]
+ [Negative-Prompt aus B]
```
Iteriere, bis Proportionen, Augen-Glow und Knöchel-Tape eindeutig sitzen. Dann einfrieren.

---

## D) Pose-Prompt-Template (für JEDEN Post)
Referenz `reference.png` als Charakter-Anker mitgeben, dann:

```
Same character as the reference image, identical design and colors. New pose: {POSE}.
{CAMERA}. Solid {BG_COLOR} background from the FORGE palette. {ASPECT}.
+ [Style-Lock aus A]
+ [Negative-Prompt aus B]
```

Platzhalter:
- `{POSE}` – z.B. "doing a deep forward lunge", "hanging exhausted from a pull-up bar,
  sweat drop", "mid push-up, low angle", "flexing one arm, confident".
- `{CAMERA}` – z.B. "dynamic low angle", "centered front", "3/4 view".
- `{BG_COLOR}` – ein Volltonton aus der Palette (`#F4EEE6`, `#D23B2E`, `#161616` …),
  pro Post wechseln für Abwechslung.
- `{ASPECT}` – "4:5 poster", "9:16 vertical", oder "1:1 square".

### Fertige Pose-Beispiele (kopierbar)
1. Leg-Day-Poster: `{POSE}= driving up from a deep lunge, fist clenched`,
   `{CAMERA}= dynamic low angle`, `{BG_COLOR}= #F4EEE6`, `{ASPECT}= 4:5 poster`.
2. Relatable-Humor: `{POSE}= hanging from a pull-up bar, struggling, single sweat drop`,
   `{CAMERA}= centered front`, `{BG_COLOR}= #F26A4B`, `{ASPECT}= 4:5 poster`.
3. Motivation-Short: `{POSE}= standing tall, arms relaxed, looking forward`,
   `{CAMERA}= slight low angle`, `{BG_COLOR}= #161616`, `{ASPECT}= 9:16 vertical`.

---

## E) Konsistenz-Checkliste vor dem Export
- [ ] Körper crimson, NICHT gelb.
- [ ] Augen klein + orange glühend, KEINE weißen Schlitze.
- [ ] Getapte Knöchel sichtbar (Signature).
- [ ] Outline/Shading wie im Style-Lock.
- [ ] Hintergrund volltonig aus der Palette.
- [ ] Kein Text/Logo im generierten Bild (kommt erst im Branding-Schritt dazu).
