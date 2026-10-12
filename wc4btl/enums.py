"""Value lists for dropdowns (from EModule's option enums, translated) and per-field editor hints."""

FORMATION = {1: "1 (single)", 2: "2", 3: "3", 4: "4 (full)"}
FACING = {0: "Left", 1: "Right"}
STRONGHOLD = {0: "None", 1: "Red ring", 2: "Green ring"}
AI_ORDER = {0: "Free action", 1: "Aggressive attack", 2: "Cautious attack", 3: "Hold position", 4: "Retreat"}
TRANSPORT = {0: "Free (may embark)", 2: "Cannot go to sea"}
MORALE = {0: "Normal", 1: "High", -1: "Low", -2: "Very low", -3: "Chaos"}
SHIELD = {0: "None", 1: "Hold position", 9: "Show shield"}
WEATHER = {1: "Rain", 2: "Heavy rain", 3: "Snow"}
TRIGGER_CONDITION = {0: "City captured", 1: "Unit destroyed", 2: "Round reached", 4: "Chained (linked event)"}
EVENT_ACTION = {0: "Morale up", 1: "Morale down", 2: "Morale drops sharply", 3: "Morale chaos", 4: "Show dialogue",
                5: "Start fire", 6: "Change faction AI order", 7: "Change alliance", 8: "Faction moves toward hex",
                10: "Add money", 11: "Add industry", 12: "Add technology"}
AI_CONTROL = {0: "Player side", 1: "AI"}
GENERAL_QUALITY = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum"}

# per record type: key -> hint.  Hints: ("enum", dict) | "faction_id" | "army" | "general" | "hex" | "country"
#                  | "victory" | "ro" (read only) | "medal" | "ribbon" | "building" | "airdefence"
HINTS = {
    "Troop": {"army": "army", "formation": ("enum", FORMATION), "facing": ("enum", FACING),
              "stronghold": ("enum", STRONGHOLD), "ai": ("enum", AI_ORDER), "transport": ("enum", TRANSPORT),
              "morale": ("enum", MORALE), "shield": ("enum", SHIELD), "general": "general", "hex": "ro",
              "quality": ("enum", GENERAL_QUALITY), "move_target": "hex",
              "medal1": "medal", "medal2": "medal", "medal3": "medal",
              "v3_medal1": "medal", "v3_medal2": "medal", "v3_medal3": "medal",
              "ribbon1": "ribbon", "ribbon2": "ribbon", "ribbon3": "ribbon"},
    "Reinforcement": {"army": "army", "formation": ("enum", FORMATION), "ai": ("enum", AI_ORDER),
                      "transport": ("enum", TRANSPORT), "general": "general", "country": "faction_id",
                      "hex": "ro", "quality": ("enum", GENERAL_QUALITY)},
    "City": {"stronghold": ("enum", STRONGHOLD), "transport": ("enum", TRANSPORT), "hex": "ro",
             "building": "building", "aa": "airdefence"},
    "Mine": {"owner": "faction_id", "hex": "ro"},
    "AirRaid": {"faction": "faction_id", "army": "army", "hex": "ro"},
    "Capital": {"hex": "ro"},
    "Weather": {"type": ("enum", WEATHER)},
    "Event": {"condition": ("enum", TRIGGER_CONDITION), "action": ("enum", EVENT_ACTION),
              "trigger_faction": "faction_id", "affect_faction": "faction_id"},
    "FactionGeneral": {"faction": "faction_id", "general": "general"},
    "AirSupport": {"faction": "faction_id", "army": "army"},
    "Faction": {"country": "country", "ai": ("enum", AI_CONTROL)},
    "Master": {"victory": "victory", "version": "ro", "map_index": "ro", "crop_x": "ro", "crop_y": "ro",
               "width": "ro", "height": "ro"},
    "Deploy": {"facing": ("enum", FACING), "transport": ("enum", TRANSPORT), "hex": "hex"},
    "Scheme": {"target": "hex"},
}


def hint(rt_name, key):
    return HINTS.get(rt_name, {}).get(key)
