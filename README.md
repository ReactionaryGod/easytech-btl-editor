<div align="center">

# EasyTech BTL Editor

**A visual battle-map editor for EasyTech strategy games: edit `.btl` maps on a hex map instead of in a hex editor.**

[![CI](https://github.com/ReactionaryGod/easytech-btl-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/ReactionaryGod/easytech-btl-editor/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/GUI-PySide6%20(Qt%206)-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Maps verified](https://img.shields.io/badge/WC4%20maps%20round--tripped-1383%2F1383-success)

<img src="docs/screenshots/troop-editor.png" alt="Editing a troop on a World Conqueror 4 campaign map" width="900">

</div>

EasyTech (World Conqueror, European War, Great Conqueror, …) stores every battle in `.btl` files: factions,
terrain, cities, units, generals, reinforcements, events and weather, all packed as raw binary records. This editor
draws the map with the game's own art and lets you click a hex to edit what's on it.

> **Supported game:** World Conqueror 4 v1.30.0 (all 1383 shipped maps: format versions 1, 2 and 3).
> Other EasyTech titles use the same `.btl` idea with different record layouts. See [Other EasyTech games](#other-easytech-games).

## Features

- 🗺️ **Map browser:** every map in the game's `stage/` folder, grouped by mode (Conquest, Campaign, General stage, Frontier, Invade corps, War zone, Event, Legend), with campaign names and a filter box.
- 🎨 **Real game rendering:** terrain and plant sprites, ownership colours and borders, cities and capitals, flags and general portraits, read from the game's own atlases. Each layer can be switched off.
- 🖱️ **Hex panel:** click a hex to edit its land, city, city HP, troop, mine, reinforcements, air raids and capital or deploy slots. Add, copy, paste and delete on every tab.
- 🪖 **Searchable pickers** for army types, generals and countries. Picking a general fills in rank, quality and skill levels.
- ✋ **Drag a troop** onto another hex to move it.
- 🧰 **Multi-select:** create or delete troops, cities and mines, set the owner or province, or set any troop or city field across many hexes at once.
- 🖌️ **Province painting:** paint which hexes belong to a city, then apply.
- ✂️ **Crop:** save any rectangle of a map as a new standalone map.
- 📋 **Data panel:** header, factions (colour picker, resources, 53 tech levels, reorder), events, weather, schemes, faction generals, air support and deploy slots.
- ↩️ **Undo/redo**, a `.bak` copy before the first save, and an optional `ch_battle.bin` MD5 update (WC4 1.30.0 doesn't check it, but it keeps the table in sync).
- 🌐 Game text in any of the game's 7 languages; field labels in English or the original Chinese.

<table>
<tr>
<td><img src="docs/screenshots/factions.png" alt="Faction data panel on the Conquest map"></td>
<td><img src="docs/screenshots/overview.png" alt="A whole event map zoomed out"></td>
</tr>
<tr>
<td align="center">Faction resources, colours and tech in the Data panel</td>
<td align="center">A whole event map at a glance</td>
</tr>
</table>

## Getting started

You need Python 3.10 or newer and your own copy of the game, unpacked (the editor ships no game files).

**Windows:** double-click `run.bat`. The first run creates a `.venv` and installs PySide6.

**Any OS:**

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/python app.py [path/to/map.btl]
```

Then use **File › Set game folder…** and point it at the unpacked APK: the folder that contains `assets/`, or
`assets/` itself. The editor reads `assets/stage/*.btl`, the `*settings.json` tables, the stringtables, `world.bin`
and the texture atlases from there.

> ⚠️ Saving writes into your game folder. The editor keeps a `.bak` of each map the first time you save it, but back up
> the folder before big edits.

### Shortcuts

| Key | Action |
|---|---|
| `1` / `2` / `3` / `4` | Select / Multi-select / Province paint / Crop mode |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | Open / save / save as |
| `Ctrl+=` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / fit |
| Wheel | Zoom |
| Right or middle drag, `Alt`+drag | Pan |

## How it compares with EModule

The design follows **EModule 0.1.3's BtlEditor**, an Android `.btl` editor. This is an independent desktop
rewrite with no activation code or login. Its file handling was checked against every WC4 map, which surfaced
several problems the original has:

| Issue in EModule | Here |
|---|---|
| War zone (v2) maps read with 80-byte reinforcements | Correct 104-byte records |
| The header-27 section and v3 trailing bytes are dropped while their counts stay in the header, corrupting the map | Both kept byte-for-byte |
| Every faction id rewritten to its list position | Ids never renumbered |
| Mine HP read as an i32, absorbing the army code | `u16 hex, owner, level, HP, army (33/34), pad` |
| Schemes keyed by target hex, duplicates lost | Kept as a list |
| Every section re-sorted into hex order on save | Original record order kept |

Loading and saving any shipped map without edits gives a **byte-identical file**.

## The `.btl` format

All record layouts, with the original Chinese field names next to English ones, are in
[`wc4btl/btlfile.py`](wc4btl/btlfile.py). In short:

```
header → factions → terrain (own-terrain maps only) → province u16[n] → owner u8[n]
→ cities → troops → mines → schemes → weather → events → reinforcements → air raids
→ deploy A → deploy B → capitals → header-27 section → faction generals → air support → tail (v3)
```

- Version 1 uses 48-byte troops and 80-byte reinforcements. Versions 2 and 3 use 64 and 104 bytes.
- Maps with `map_index ≠ 0` sit on the 148 × 54 world grid from `world.bin`. Their hex references are world hex ids
  `(y + crop_y) × 148 + (x + crop_x)`.
- Owner bytes hold faction **indexes**. Every other faction reference holds faction **ids**.
- Hexes are flat-topped, with odd columns shifted down half a row (odd-q).

## Project layout

```
app.py                 entry point
wc4btl/btlfile.py      .btl reader/writer (all record types)
wc4btl/worldbin.py     world.bin (world terrain + provinces)
wc4btl/gamedata.py     game tables, stringtables, atlases, terrain config
wc4btl/model.py        per-hex document, edit operations, undo, crop, save
wc4btl/ui/             Qt interface (map view, hex/data/tool panels, dialogs)
tests/                 format tests (no game needed) + round-trip / model / UI tests (need the game)
```

## Tests

```bash
python -m unittest discover -s tests -p "test_format.py"     # no game files needed; runs in CI
python tests/test_roundtrip.py "<game>/assets/stage"         # every map must re-save byte-identical
python tests/test_model.py "<game>"                          # edit operations + undo
python tests/smoke_ui.py <screenshot-dir>                    # headless UI run
```

## Other EasyTech games

EasyTech's other strategy games also use `.btl` battle files, but the records differ between games and versions.
Support for another game means adding its record layouts to `btlfile.py`, plus its tables and atlases in
`gamedata.py`. Issues and pull requests with layout notes or sample maps for other titles are welcome.

## Disclaimer

A fan-made modding tool, not affiliated with or endorsed by EasyTech. World Conqueror and all game assets belong to
their owners. This repository contains only original code and screenshots of the editor; you need your own copy of
the game. Edit only games you own.

## License

[MIT](LICENSE)
