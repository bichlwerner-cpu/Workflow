"""Rendert das Mega-Brain-Cockpit als eigenstaendige HTML-Datei.

Liest brain-state.json (Pflicht) und morgenbriefing-daten.json (optional) und
schreibt eine Seite mit Ampel, Exit-Triggern, Risiko-Indikatoren, Watchlist und
Funden. Deterministisch: die Seite enthaelt nur, was in den JSONs steht.

    python render_cockpit.py brain-state.json --funde morgenbriefing-daten.json -o cockpit.html
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime
from pathlib import Path

AMPEL_FARBEN: dict[str, str] = {
    "ROT": "#b4332a",
    "GELB": "#a8760f",
    "GRUEN": "#2f6b45",
    "GRÜN": "#2f6b45",
}

# Ab wie vielen Tagen ohne frische Messung ein Wert als veraltet gilt.
VERALTET_AB_TAGEN = 14


def _alter_in_tagen(stand: str | None, heute: date) -> int | None:
    """Tage zwischen einem ISO-Datum und heute; None wenn unparsbar."""
    if not stand:
        return None
    try:
        return (heute - datetime.fromisoformat(stand).date()).days
    except ValueError:
        return None


def _ampel(status: str) -> str:
    return AMPEL_FARBEN.get(status.upper(), "#6b6b6b")


def _e(text: object) -> str:
    return html.escape(str(text if text is not None else ""))


def berechne_ampel(state: dict) -> tuple[str, list[dict]]:
    """Gesamtampel aus ausgeloesten Triggern und roten Indikatoren.

    ROT sobald ein Exit-Trigger scharf ist oder >= 8 Indikatoren ROT sind,
    GELB ab 4 roten Indikatoren, sonst GRUEN.
    """
    scharf = [t for t in state.get("exit_trigger", []) if t.get("status") == "ausgeloest"]
    rote = sum(1 for i in state["risiko"]["indikatoren"] if i.get("status", "").upper() == "ROT")
    if scharf or rote >= 8:
        return "ROT", scharf
    if rote >= 4:
        return "GELB", scharf
    return "GRUEN", scharf


def faellige_felder(funde_daten: dict | None, heute: date) -> list[tuple[str, int, bool]]:
    """(Feldname, Tage seit letztem Scan, faellig?) fuer jedes Beobachtungsfeld."""
    if not funde_daten:
        return []
    db = funde_daten.get("db", {})
    scans = db.get("scans", {})
    out: list[tuple[str, int, bool]] = []
    for feld in db.get("felder", []):
        name = feld["name"]
        alter = _alter_in_tagen(scans.get(name), heute)
        tage = alter if alter is not None else 999
        out.append((name, tage, feld.get("pflicht", False) or tage >= feld.get("intervall", 1)))
    return out


def _kopf(state: dict, ampel: str, scharf: list[dict]) -> str:
    stand = _e(state.get("stand", ""))
    farbe = _ampel(ampel)
    trigger_block = ""
    if scharf:
        zeilen = "".join(
            f"<p class='ausgeloest'><strong>{_e(t['name'])}</strong> — {_e(t.get('bedingung',''))}</p>"
            for t in scharf
        )
        trigger_block = f"<div class='alarm'><h2>Exit-Trigger ausgelöst</h2>{zeilen}</div>"
    return f"""
<header>
  <p class="stand">Stand {stand}</p>
  <h1>Mega Brain — Cockpit</h1>
  <div class="ampel" style="--c:{farbe}"><span></span>{_e(ampel)}</div>
</header>
{trigger_block}"""


def _trigger_tabelle(state: dict) -> str:
    zeilen = []
    for t in sorted(state.get("exit_trigger", []), key=lambda x: x.get("prio", 99)):
        scharf = t.get("status") == "ausgeloest"
        zeilen.append(
            f"<tr class='{'scharf' if scharf else ''}'>"
            f"<td class='prio'>{_e(t.get('prio'))}</td>"
            f"<td><strong>{_e(t.get('name'))}</strong><br><span class='klein'>{_e(t.get('bedingung'))}</span></td>"
            f"<td class='nowrap'>{_e(t.get('status'))}</td>"
            f"<td class='nowrap'>{_e(t.get('zuletzt_geprueft'))}</td></tr>"
        )
    return f"""
<section><h2>Exit-Trigger</h2>
<div class="scroll"><table>
<thead><tr><th>Prio</th><th>Bedingung</th><th>Status</th><th>geprüft</th></tr></thead>
<tbody>{''.join(zeilen)}</tbody></table></div></section>"""


def _indikator_tabelle(state: dict, heute: date) -> str:
    zeilen = []
    for i in state["risiko"]["indikatoren"]:
        alter = _alter_in_tagen(i.get("stand"), heute)
        veraltet = alter is not None and alter > VERALTET_AB_TAGEN
        alt_txt = f"{alter} Tage" if alter is not None else "—"
        zeilen.append(
            f"<tr><td><strong>{_e(i['name'])}</strong><br><span class='klein'>{_e(i.get('metrik'))}</span></td>"
            f"<td>{_e(i.get('wert'))}</td>"
            f"<td class='klein'>{_e(i.get('schwelle'))}</td>"
            f"<td class='nowrap'><span class='punkt' style='--c:{_ampel(i.get('status',''))}'></span>{_e(i.get('status'))}</td>"
            f"<td class='nowrap {'veraltet' if veraltet else ''}'>{alt_txt}</td></tr>"
        )
    return f"""
<section><h2>Blasen-Indikatoren</h2>
<div class="scroll"><table>
<thead><tr><th>Indikator</th><th>Wert</th><th>Schwelle</th><th>Status</th><th>Alter</th></tr></thead>
<tbody>{''.join(zeilen)}</tbody></table></div></section>"""


def _watchlist(state: dict) -> str:
    blocks = []
    for gruppe, titel in (
        ("melt-up-ranking", "Melt-up-Ranking"),
        ("discovery-kette", "Discovery-Kette"),
    ):
        werte = [w for w in state["watchlist"] if w.get("gruppe") == gruppe]
        if not werte:
            continue
        werte.sort(key=lambda w: w.get("rang", 99))
        karten = "".join(
            f"<article class='wert'>"
            f"<h3><span class='ticker'>{_e(w['ticker'])}</span> {_e(w['name'])}"
            + (f" <span class='rang'>#{_e(w['rang'])}</span>" if w.get("rang") else "")
            + f"</h3><p class='rolle'>{_e(w.get('rolle'))}</p>"
            f"<div class='duell'><div><h4>These</h4><p>{_e(w.get('these'))}</p></div>"
            f"<div><h4>Gegenrede</h4><p>{_e(w.get('gegenrede'))}</p></div></div></article>"
            for w in werte
        )
        blocks.append(f"<section><h2>{titel}</h2>{karten}</section>")
    return "".join(blocks)


def _funde(funde_daten: dict | None, heute: date) -> str:
    if not funde_daten:
        return ""
    db = funde_daten.get("db", {})
    faellig = faellige_felder(funde_daten, heute)
    zeilen = "".join(
        f"<tr><td>{_e(n)}</td><td class='nowrap'>{t} Tage</td>"
        f"<td class='nowrap'>{'fällig' if f else '—'}</td></tr>"
        for n, t, f in faellig
    )
    karten = "".join(
        f"<article class='wert'><h3>{_e(f['name'])} <span class='rang'>{_e(f.get('status'))}</span></h3>"
        f"<p class='rolle'>{_e(f.get('bereich'))} · {_e(f.get('naehe'))}</p>"
        f"<div class='duell'><div><h4>These</h4><p>{_e(f.get('these'))}</p></div>"
        f"<div><h4>Gegenrede</h4><p>{_e(f.get('gegenrede'))}</p></div></div></article>"
        for f in db.get("funde", {}).values()
    )
    return f"""
<section><h2>Beobachtungsfelder</h2>
<div class="scroll"><table>
<thead><tr><th>Feld</th><th>letzter Scan</th><th>heute</th></tr></thead>
<tbody>{zeilen}</tbody></table></div></section>
<section><h2>Funde</h2>{karten}</section>"""


STIL = """
:root{--bg:#faf9f7;--fg:#1c1b19;--mut:#6b6862;--lin:#e3e0da;--kar:#fff}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161513;--fg:#eceae6;--mut:#9b968d;--lin:#2e2c28;--kar:#1e1d1a}}
:root[data-theme="dark"]{--bg:#161513;--fg:#eceae6;--mut:#9b968d;--lin:#2e2c28;--kar:#1e1d1a}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0}
main{max-width:70rem;margin:0 auto;padding:2rem 1.25rem 5rem}
header{border-bottom:1px solid var(--lin);padding-bottom:1.25rem;margin-bottom:2rem}
h1{font-size:1.9rem;margin:.2rem 0 .8rem;letter-spacing:-.02em}
h2{font-size:1.15rem;margin:2.5rem 0 .9rem;letter-spacing:-.01em}
h3{font-size:1rem;margin:0 0 .2rem}
h4{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:0 0 .3rem}
.stand{color:var(--mut);font-size:.8rem;margin:0}
.ampel{display:inline-flex;align-items:center;gap:.5rem;font-weight:600;font-size:.9rem;
  border:1px solid var(--c);color:var(--c);border-radius:2rem;padding:.3rem .85rem}
.ampel span{width:.6rem;height:.6rem;border-radius:50%;background:var(--c)}
.punkt{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;background:var(--c);margin-right:.4rem}
.alarm{border:1px solid #b4332a;border-left-width:4px;border-radius:.4rem;padding:1rem 1.2rem;margin-bottom:2rem;background:var(--kar)}
.alarm h2{margin:0 0 .5rem;color:#b4332a;font-size:1rem}
.ausgeloest{margin:.3rem 0;font-size:.9rem}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.87rem;min-width:34rem}
th{text-align:left;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;
  color:var(--mut);border-bottom:1px solid var(--lin);padding:.5rem .6rem}
td{border-bottom:1px solid var(--lin);padding:.6rem;vertical-align:top}
tr.scharf td{background:rgba(180,51,42,.08)}
.prio{font-variant-numeric:tabular-nums;color:var(--mut)}
.nowrap{white-space:nowrap}
.veraltet{color:#a8760f}
.klein{font-size:.8rem;color:var(--mut)}
.wert{background:var(--kar);border:1px solid var(--lin);border-radius:.5rem;padding:1rem 1.15rem;margin-bottom:.7rem}
.ticker{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85rem;
  background:var(--bg);border:1px solid var(--lin);border-radius:.25rem;padding:.1rem .35rem;margin-right:.3rem}
.rang{color:var(--mut);font-weight:400;font-size:.8rem}
.rolle{color:var(--mut);font-size:.83rem;margin:.1rem 0 .8rem}
.duell{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem}
.duell p{margin:0;font-size:.88rem}
@media(max-width:44rem){.duell{grid-template-columns:1fr;gap:.9rem}}
"""


def render(state: dict, funde_daten: dict | None, heute: date) -> str:
    ampel, scharf = berechne_ampel(state)
    return (
        f"<title>Mega Brain — Cockpit</title>\n<style>{STIL}</style>\n<main>"
        + _kopf(state, ampel, scharf)
        + _trigger_tabelle(state)
        + _indikator_tabelle(state, heute)
        + _funde(funde_daten, heute)
        + _watchlist(state)
        + "</main>"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Rendert das Mega-Brain-Cockpit als HTML.")
    p.add_argument("state", type=Path, help="Pfad zu brain-state.json")
    p.add_argument("--funde", type=Path, default=None, help="Pfad zu morgenbriefing-daten.json")
    p.add_argument("-o", "--out", type=Path, default=Path("cockpit.html"))
    args = p.parse_args()

    state = json.loads(args.state.read_text(encoding="utf-8"))
    funde = json.loads(args.funde.read_text(encoding="utf-8")) if args.funde else None

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(state, funde, date.today()), encoding="utf-8")
    print(f"✓ {args.out}")


if __name__ == "__main__":
    main()
