# Mega Brain

Ein täglich laufendes Auswertungssystem für KI-Infrastruktur-News und -Aktien.
Es lebt in Google Drive, wird von einer Routine gefeuert und erinnert sich zwischen
den Läufen über zwei JSON-Dateien.

## Die drei Schichten

Das System macht genau drei Dinge, und die Reihenfolge ist Absicht:

```
1. ABSICHERN   5 Exit-Trigger + 13 Blasen-Indikatoren neu messen   → jeden Tag
2. BEWERTEN    27 Watchlist-Werte: Bewegung, Termine, Signale       → jeden Tag
3. ENTDECKEN   6 Beobachtungsfelder nach Intervall scannen          → nach Fälligkeit
```

**Absichern zuerst**, weil es die einzige Schicht mit harten, regelbasierten
Schwellen ist. Eine These über Photonik-Verdrängung kann man diskutieren; ein
High-Yield-Spread über 400 Basispunkten ist ein Messwert. Wenn morgens nur eine
Zahl gelesen wird, dann die Ampel.

## Dateien

| Datei | Ort | Inhalt |
|---|---|---|
| `brain-state.json` | Drive: Mega Brain | Watchlist, Risiko-Cockpit, Exit-Trigger, Lauf-Historie |
| `morgenbriefing-daten.json` | Drive: Mega Brain | Felder, Funde, Scans, Läufe, Briefing-Index |
| `tagesroutine.md` | dieses Verzeichnis | Der Prompt, den die Routine feuert |
| `render_cockpit.py` | dieses Verzeichnis | Rendert das Cockpit-HTML aus beiden JSONs |

Die beiden JSONs sind bewusst **getrennt**. `morgenbriefing-daten.json` behält ihr
bestehendes Schema, weil der Discovery Loop schon daran hängt — sie wird erweitert,
nicht ersetzt. `brain-state.json` ist neu und trägt die beiden neuen Schichten.

## Woher die Inhalte kommen

Nichts davon ist erfunden. Die Startwerte stammen aus drei vorhandenen Analysen:

- **Watchlist, Gruppe `melt-up-ranking`** (16 Werte, Rang 1–16) aus
  *KI-Infrastruktur-Aktien-Ranking für Melt-up* (04.06.2026) — sortiert nach
  Hebelwirkung auf Hyperscaler-Capex, mit Purity, Beta, Short Interest, IV.
- **Watchlist, Gruppe `discovery-kette`** (11 Werte) aus dem bestehenden
  Discovery Loop — GOOGL, ASML, ANET, POET, LPKF, Weebit, Centrus, BWXT, Cameco,
  Oklo, NuScale.
- **Risiko-Cockpit und Exit-Trigger** aus *Blasen-Top-Indikatoren: Aktuelle Analyse*
  (04.06.2026) — 13 Indikatoren mit historischen Gefahrenschwellen, 5 priorisierte
  Ausstiegsmarken.

**Alle Kennzahlen haben Datenstand Juni 2026.** Sie sind Startpunkt, nicht Wahrheit.
Der erste Tageslauf überschreibt, was er frisch messen kann; alles andere bleibt mit
sichtbarem Alter stehen.

## Die zwei Regeln, die das System tragen

**These und Gegenrede sind gleichrangig.** Jeder Watchlist-Wert und jeder Fund hat
beide Felder, und beide werden gepflegt. Das ist die Konstruktion, die aus einer
Nachrichtensammlung ein Bewertungssystem macht. Ein Bestand, dessen These wächst
während die Gegenrede seit Wochen unverändert steht, ist ein Warnzeichen.

**Ein veralteter Wert mit Datum schlägt einen erfundenen frischen Wert.** Indikatoren
ohne belegte Messung behalten ihren alten Stand und werden als veraltet markiert.
Nicht erreichbare Quellen kommen mit Grund unter `quellen_fehler`, Unverifiziertes
unter `blindstellen`. Ein Lauf ohne Blindstellen ist verdächtig, nicht gut.

## Was das System nicht tut

Keine Kauf- oder Verkaufsempfehlungen. Es misst Bedingungen, die vorher selbst
definiert wurden, und stellt These gegen Gegenrede. Löst ein Exit-Trigger aus, wird
das mit Beleg sichtbar gemacht — gehandelt wird nicht.

## Ändern

- **Andere Werte beobachten** → `watchlist` in `brain-state.json`. Pflichtfelder:
  `ticker`, `name`, `gruppe`, `rolle`, `these`, `gegenrede`, `beobachten`.
- **Andere Schwellen** → `exit_trigger[].bedingung` und `risiko.indikatoren[].schwelle`.
- **Anderer Takt oder Ablauf** → `tagesroutine.md`, danach den Routine-Prompt neu setzen.
  Die Routine liest diese Datei nicht selbst — der Text ist im Trigger gespeichert.
- **Neues Beobachtungsfeld** → `felder` in `morgenbriefing-daten.json`, mit
  `intervall` und `pflicht`.

## Die Routine

Angelegt als `Mega Brain — Tageslauf` (`trig_01PHeRhaDirK1qnAUieCPokn`), werktags
`30 4 * * 1-5` UTC = **06:30 Wien** (Sommerzeit; ab der Zeitumstellung Ende Oktober
wird daraus 05:30 lokal — dann den Cron auf `30 5 * * 1-5` setzen). Jeder Lauf startet
eine frische Session, Push-Benachrichtigung ist an.

**Offener Punkt — Connector-Zugriff.** Das Anlegen der Routine über die MCP-Schnittstelle
konnte den Google-Drive-Zugriff nicht mitspeichern; die Organisation erlaubt den
`connectors`-Parameter dort nicht. Ohne diesen Zugriff kann der Tageslauf das Gedächtnis
in Drive weder lesen noch zurückschreiben.

Der Routine-Prompt fängt das ab: fehlt Drive, läuft nur die Absichern-Schicht aus
frischer Recherche (die fünf Exit-Trigger stehen vollständig im Prompt und brauchen
keinen State), und der Lauf sagt das im ersten Satz.

**Fix:** die Routine in den claude.ai-Einstellungen unter Routines öffnen und Google
Drive als Connector zuweisen. Danach läuft der volle Kreislauf inklusive Gedächtnis.
