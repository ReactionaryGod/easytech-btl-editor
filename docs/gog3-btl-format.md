# Glory of Generals 3 `.btl` format

Glory of Generals 3 (EasyTech, Android, engine `lib/arm64-v8a/libiron.so`) stores its battles in
`assets/stage/{stage,conquest,corps}N.btl`. Unlike World Conqueror 4's raw record dumps, these are **FlatBuffers 1.9**
buffers (the engine embeds the string `FlatBuffers 1.9.0`).

FlatBuffers files carry no field names, so the schema was recovered from the engine's machine code. The
`stage%d.btl` loader runs the generated verifier `0x1e3ab8` before it reads anything. That verifier and the 42
sub-verifiers it calls encode every field's slot, byte width, and whether it is a scalar, struct, string, vector or
nested table. The meaning of each field then came from:

1. the loaders that hand each section to a game class (`CEntityCountry`, `CEntityArmy`, `CEntityTrigger`, …, resolved through RTTI);
2. the game's JSON tables, string tables and Lua scripts; and
3. statistics over all 420 shipped maps.

**How sure each name is:** plain names are confirmed by code, or by every one of the 420 maps. A trailing `?` means
the name is inferred. `fN` means the field's meaning is unknown, but its type and size are still exact.

**Verification:**
- Every non-padding byte of all 420 maps is explained by the schema. The only exception is 44 dead bytes in
  conquest1/2, which no vtable points at.
- `gog3btl` reads all 420 maps, rebuilds them and reads them back unchanged.
- The engine's own verifier, run under an arm64 emulator, accepts all 420 originals and all 420 rebuilt files, and
  rejects a corrupted file.

## Layout

```
Battle (root table)
 0 version          u16        always 1
 1 map              MapInfo
 2 objectives       Objectives  (battle victory goals; also read by the stage preview screen)
 3 key_areas        KeyAreas
 4 countries        Countries   -> CEntityCountry
 5 areas            Areas       -> area/city entities (Lua "AREA" ids are these hexes)
 6 armies           Armies      -> CEntityArmy
 7 triggers         Triggers    -> CEntityTrigger
 8 reinforcements   Reinforcements -> CEntityReinforcement (empty in every shipped map)
 9 weather          WeatherList -> CEntityWeather
10 ai_tree          [u8]        FlexBuffers behaviour tree for the AI (CBTCountryAgent); [0,0,40,1] = empty map
```

Hex indexes are `y * width + x`. `65535` means "no hex".

### MapInfo

| # | field | type | meaning |
|---|---|---|---|
| 0 | size | struct (6 × u16) | `width, height, view_x, view_y, view_w, view_h`: map size and the playable/camera rectangle (usually `4, 3, W-8, H-5`) |
| 1 | f1 | u8 | 1-4, in 53 maps |
| 2 | hexes | [u16] | one value per hex, see below |
| 3 | overlays | [u32] | terrain sprites, consumed by the hexes in order |
| 4 | f4 | u8 | flag the engine stores on the battle object |

**Per-hex u16:** decoded by the engine function at `0x2d1740`.

| bits | meaning |
|---|---|
| 0-2 | ground: 0 earth, 1 grass, 2 desert, 3 snow, 4 (other) |
| 3-7 | ground tile variant |
| 0x0100 | hex disabled (outside the battlefield) |
| 0x0200 | sea |
| 0x0400 | layer A: takes the next overlay (decorations, terrain ids 49-57) |
| 0x0800 | layer B: takes the next overlay (main terrain: swamp, forest, hills, mountains, rivers). Sets the hex's terrain type |
| 0x1000 | layer C: takes the next overlay (upper sprites: canopies, peaks) |
| 0x2000 | extra sea flag (only together with 0x0200) |
| 0x4000 | extra flag (meaning unknown) |

**Overlay u32:** `terrain id (u8) | tile (u8) << 8 | dx (i8) << 16 | dy (i8) << 24`. The terrain id refers to
`config/def_mapterrain.xml`, and dx/dy are a pixel offset.

The engine walks hexes in index order and gives each set layer bit (A, then B, then C) the next overlay. The overlay
count therefore always equals the number of layer bits set, in all 420 maps.

**Terrain type:** follows `config/def_terraintype.xml`.
- Sea hexes are type 1.
- Otherwise the type comes from the layer-B terrain's definition. A forest whose tile index is below the definition's
  `plants` value counts as light woods (type 5).
- With no layer-B terrain, desert ground gives type 3, snow gives type 2, and anything else is plain (0).

### Objectives

`list: [Objective]`, `round_limit?: u16` (usually the stage's round limit; some stage-2xxxx maps hold large values
here).

Objective: `type u16, target u16, rounds? u16, f3 u16, f4 u8`. The type is the string-table key `objective_N`:

| type | text | target is |
|---|---|---|
| 0 | Annihilate the enemy | - |
| 1 | Reach the target point | hex |
| 2 | Withdraw {0} units | count |
| 3 | Protect {0} key units | count |
| 4 | Control {0} key areas | count |
| 5 | Defeat {0} key units | count |
| 6 | Occupy {0} key areas | count |
| 7 | Defeat {0} enemy units | count |
| 8 | Defeat {0} | general id |
| 9 | Occupy {0} | area hex |
| 10 | Protect {0} | general id |
| 11 | Hold {0} | area hex |
| 12 | Protect {0} and evacuate | general id |

### KeyAreas

`f0 u8`, `list: [KeyArea]`. KeyArea: `hex u16, f1 u8 (1), f2 u8, key u8`. Key uses the Lua `areakey` values: NORMAL 0,
PRIMARY 1, SECONDARY 2, PRIMARY_SECONDARY 3, HIDDEN 4, VICTORY 5.

### Countries (factions)

Countries holds `list: [Country]`. A Country has:
- `info`: a 36-byte struct.
- `tech? [u8 ×5]`: values 0-6, probably tech levels for infantry, armour, artillery, navy and air.
- `exarmy_pool? [ExArmyStock]`: entries of `exarmy u16` (ExArmySettings 401-522), `level? u8` and `f2 u8`.
- `f3 [Pair16]` and `f4 CountryExtra`: never used in shipped maps.
- `relations? [Relation]`: entries of `faction? u16` and `value? u16` (25/50/100).
- `tag`: `{id u16, data [u8]}`.
- `f7 u8`, `f8 u16`, `f9 u8`.

`info` layout:

| offset | field | type | meaning |
|---|---|---|---|
| 0 | id | u16 | faction id (referenced by units, buildings and relations) |
| 2 | country | u16 | `CountrySettings.json` id / `country_N` text |
| 4 | alliance | u8 | Lua `alliance`: N 0, A 1, B 2, C 3 |
| 5 | ai_controlled | u8 | 0 = player side |
| 6 | ai? | u16 | 0-5; probably the Lua `ai` attitude (NORMAL 0, RADICAL 1, CONSERVATIVE 2, GUARD 3, ESCAPE 4) |
| 8 | money | u32 | starting resource |
| 12 | f12 | u32 | 0-80 |
| 16 | rate_a, rate_b, rate_c | f32 ×3 | multipliers (mostly 1.0) |
| 28 | r, g, b, a | u8 ×4 | colour; 128,128,128,128 is the common "default" |
| 32 | f32 | u32 | |

### Areas (cities, buildings, fortifications)

Areas holds:
- `list: [Area]`
- conquest-map fields: `f1 [u32]`, `province_of_hex? [u16]` (one per hex, 65535 = none), `f3 [u16]`, `f4 [u64]`,
  `f5 u8`, `area_owners? [AreaOwner]` and `f7 u16`

An Area has:
- `hex u16`. Lua trigger scripts refer to areas by this value (`armytype.AREA`, `AREA_LOST`).
- `name u16`: the string-table key `battle_cityname_%03d`.
- `f2 u8`.
- `building`: a Building table.
- `fortification`: `type u8` (FortificationSettings: 1 radar, 2 trench, 3 bunker, 4 land fort, 5 coastal artillery)
  plus `f1`-`f3` u8.
- `f5`: a 3-byte struct.
- `f6 u8`.

Building has these fields:
- `info`: 8 bytes, laid out as `owner u16` (faction id), `building u16` (BuildingSettings 101-116),
  `style u8` (1 normal, 2 snow: the `b_<id>s` sprite, matching snow ground), `variant u8` (0-5, sprite variant such as
  port `b_109_<n>` / suburb `b_114_<n>`) and `f6 u16`.
- `f1 u32`.
- `ai`: an AIOrder table (see Armies).
- `f3 [Triple16]`.
- `f4`: `{f0 u8, f1 u16, f2 u8}`.
- `tag`.
- `f6 u8` and `f7 u8`.

### Armies (units)

Armies holds:
- `list: [Army]`
- `groups: [Group]`, where a Group is `{id u16, serials [u16]}`. Lua `armytype.GROUP` uses these ids.
- `next_serial u16`: max serial + 1 in 360 of 417 maps.
- `stacks?: [Stack]`, where a Stack is `{hex u16, serials? [u16]}`. Conquest maps only.

An Army has:
- `info`: a 20-byte struct.
- `ai`: an AIOrder table.
- `morale u8`: 80 by default. ArmyMoraleSettings treats 51-80 as normal.
- `flags? u8`: 1/65/129/193.
- `exarmy`: the elite unit attached to the army, `{id u16 (ExArmySettings; its Army list contains the unit's type),
  level u8, f2-f5 u16}`.
- `general`: `{id u16 (GeneralSettings / general_N), f1 u8, level? u8 1-4}`.
- `tag`.
- `f1 u16`, `f2 u8`, `f4 u16`, `f6 u8`, `f8 ArmyExtra`, `f9 s3`, `f13 u16` and `f14 u8`.

`info` layout:

| offset | field | type | meaning |
|---|---|---|---|
| 0 | hex | u16 | 65535 = off the map (reinforcement pool) |
| 2 | faction | u16 | faction id |
| 4 | serial | u16 | unique per map. Used by ReinforcementSettings `SerialId` (all 868 references resolve), groups and Lua `armytype.UNIT` |
| 6 | army | u16 | ArmySettings id (101-106 land, 201-206 naval) / `army_N` text |
| 8 | level? | u8 | 0-7 |
| 9 | number | u8 | 1-4 sub-units (ArmyNumberSettings) |
| 10 | b10 | u8 | 0/1 |
| 11 | mobility | u8 | ArmySettings mobility or more |
| 12 | hp, max_hp | u16 ×2 | |
| 16 | f16 | u32 | 100 almost always |

AIOrder is shared by armies and buildings: `mode? u8 (1-4, mostly 3)`, `f1 u16 (signed ±25/50/100)`,
`target_hex? u16`, `f3 u8`, `f4 u8 (1-9)`, `f5 u16` and `f6 u16`.

### Triggers, reinforcements, weather

- **Triggers:**
  - `name str`: empty in every map.
  - `list [TriggerEntry {f0 u16, f1 str, f2 u8}]`: empty in every map.
  - `f2 [u32 ×4]`.
  - `data [u8]`: a FlexBuffers blob, an empty map in shipped maps.
  - The actual trigger logic lives in `assets/luac/trigger/stageN.luac` (Lua 5.3 bytecode).
- **Reinforcements:** the table is present but empty in every shipped map. Reinforcements come from
  `ReinforcementSettings.json`, keyed by stage id and unit serial.
- **Weather:** `list [Weather {type u8 1-3, round u16, duration u16}]`.

## Related game data

**Checksums:**
- Like WC4, the engine has an MD5 table, `ch_battle.bin`, salted with `easytechbattle`. It loads the table at
  `0x1d61d4` and checks maps at `0x1e1894`.
- The modded copy studied here (its credits list a modified `libiron.so` and a modified asset folder) ships without
  `ch_battle.bin`.
- With no entry, the check returns *false*. The function that calls the check was not traced, so it is unconfirmed
  whether a missing table blocks edited maps in an unmodified game. Keep `ch_battle.bin` absent, or update its MD5s,
  when testing.

**Lua enums** (`luac/gamedefine.luac`):

| Table | Values |
|---|---|
| `ai` | NORMAL 0, RADICAL 1, CONSERVATIVE 2, GUARD 3, ESCAPE 4 |
| `alliance` | N 0, A 1, B 2, C 3 |
| `armytype` | UNIT 1, GROUP 2, COUNTRY 3, AREA 4 |
| `movement` | NONE 0, NOT_LAND 1, NOT_SEA 2 |
| `areakey` | NORMAL 0, PRIMARY 1, SECONDARY 2, PRIMARY_SECONDARY 3, HIDDEN 4, VICTORY 5 |
| `moral` | INC_50, INC_25, DEC_25, DEC_50, DEC_75 |

**String tables** (`stringtable_<lang>.ini`) use these keys: `stage_N`, `objective_N`, `country_N`, `army_N`,
`exarmy_N`, `general_N`, `battle_cityname_%03d`, `fortification_N`.

## Using `gog3btl`

The visual editor (`app.py` / `run.bat`) opens GoG3 maps directly: point **File › Set game folder…** at the
unpacked GoG3 APK. The same reader and writer are also usable on their own:

```bash
python -m gog3btl info  path/to/stage10101.btl            # readable summary with names from the string table
python -m gog3btl dump  path/to/stage10101.btl map.json   # whole map as named JSON (--overlays adds per-hex terrain)
python -m gog3btl build map.json stage10101.btl           # JSON back to .btl
```

```python
from gog3btl import load, save
b = load("stage10101.btl")
b["armies"]["list"][0]["morale"] = 100
save(b, "stage10101.btl")
```

The writer stores exactly the fields present in the dict; absent fields fall back to their defaults. Its layout is
not byte-identical to EasyTech's tool. Field placement and padding differ, so files are about 1% larger, but the
content and the engine's verifier result are the same.
