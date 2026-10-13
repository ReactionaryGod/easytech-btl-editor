# Changelog

## 0.2.1 (2026-10-13)

- World Conqueror 4: troop byte 47 is now its own **Elite skin** field. EModule and 0.2.0 read bytes 44-47 as one
  "hold min distance" int, so skin 1 appeared as 16777216. The troop form lists the unit's skins by in-game name
  (EliteSkinSettings + `def_motion.xml` `skin_<n>` entries) and warns when a skin has no sprite. Skinned troops get
  an S1 badge on the map, and the skin shows in the troop summary and status bar. Hold distance is now a 2-byte field
  (bytes 45-46 are 0 in every map). Files still save byte-identical.

## 0.2.0 (2026-10-12)

**Glory of Generals 3 support**, in the same window as World Conqueror 4 (the game is detected from the folder or
the map file):

- Map browser with in-game titles; rendering with the game's terrain, river, building, army-icon, flag and portrait
  art; ownership tint and province borders on conquest maps.
- Hex panel (terrain bits and sprite layers, area/building/fortification/key area, army), data panel (objectives,
  factions, key areas, groups, off-map units, weather, map settings, JSON editor for any section), multi-select
  tools, army drag-and-drop, undo/redo, backups, `ch_battle.bin` update when present.
- `gog3btl` package: FlatBuffers schema recovered from the game engine, reader/writer, `python -m gog3btl`
  info/dump/build. All 420 shipped maps round-trip; rebuilt maps pass the engine's own verifier.
- Format reference: `docs/gog3-btl-format.md`.

Other changes:

- The UI smoke tests use throwaway settings instead of clearing the user's saved settings.
- CI also runs the GoG3 format tests.

## 0.1.0 (2026-10-12)

First public release.

- World Conqueror 4 v1.30.0: reads and writes `.btl` versions 1-3. All 1383 shipped maps re-save byte-identical.
- Map view with the game's terrain, plant, building, flag and portrait art.
- Hex panel (land, city, city HP, troop, mine, reinforcements, air raids, capital/deploy) and Data panel (header,
  factions, events, weather, schemes, faction generals, air support, deploy slots).
- Select, multi-select, province paint and crop modes; drag troops to move them.
- Undo/redo, `.bak` backups, optional `ch_battle.bin` MD5 update.
