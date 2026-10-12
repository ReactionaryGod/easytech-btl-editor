"""Glory of Generals 3 .btl command line.

  python -m gog3btl info  <map.btl> [--assets <gog3>/assets] [--lang en]
  python -m gog3btl dump  <map.btl> <out.json> [--overlays]
  python -m gog3btl build <in.json> <out.btl>

dump writes the whole map as named JSON (see format.py for field meanings); build turns it back into a .btl.
With --overlays the dump also lists the terrain overlays each hex uses (read-only, for reference).
"""
import argparse
import json
import os
import re
import sys

from .format import load, overlays_by_hex, save, HEX_DISABLED, HEX_SEA, OBJECTIVE_TARGET


def strings(assets, lang):
    path = os.path.join(assets, "stringtable_%s.ini" % lang)
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig", errors="replace"):
            m = re.match(r"([A-Za-z0-9_]+)=(.*)", line.rstrip("\r\n"))
            if m:
                out[m.group(1)] = m.group(2)
    return out


def guess_assets(path):
    d = os.path.dirname(os.path.abspath(path))
    return os.path.dirname(d) if os.path.basename(d) == "stage" else d


def info(path, assets, lang):
    b = load(path)
    s = strings(assets, lang)
    t = lambda key, default: s.get(key, default)
    m = b["map"]["size"]
    hexes = b["map"].get("hexes", [])
    stage = os.path.basename(path)[5:-4]
    print("%s  %s" % (os.path.basename(path), t("stage_" + stage, "")))
    print("map %d x %d, view rect (%d, %d) %d x %d, %d sea hexes, %d disabled, %d overlays" % (
        m["width"], m["height"], m["view_x"], m["view_y"], m["view_w"], m["view_h"],
        sum(1 for v in hexes if v & HEX_SEA), sum(1 for v in hexes if v & HEX_DISABLED), len(b["map"].get("overlays", []))))
    ob = b.get("objectives", {})
    print("\nobjectives (round limit? %s):" % ob.get("round_limit?"))
    area_name = {a["hex"]: a["name"] for a in b.get("areas", {}).get("list", []) if "name" in a}
    for o in ob.get("list", []):
        target = o.get("target", 0)
        what = OBJECTIVE_TARGET.get(o.get("type", 0))
        if what == "general":
            name = "(general %s)" % t("general_%d" % target, "?")
        elif what == "area hex":
            name = "(hex %d, %s)" % (target, t("battle_cityname_%03d" % area_name[target], "?") if target in area_name else "unnamed")
        else:
            name = "(%s)" % what if what else ""
        print("  type %d %-26s target %d %s  rounds? %s" % (o.get("type", 0), t("objective_%d" % o.get("type", 0), ""),
                                                             target, name, o.get("rounds?")))
    print("\ncountries:")
    for c in b.get("countries", {}).get("list", []):
        i = c["info"]
        print("  id %d  %-12s alliance %d  %s  money %d  colour %d,%d,%d,%d" % (
            i["id"], t("country_%d" % i["country"], "country %d" % i["country"]), i["alliance"],
            "AI" if i["ai_controlled"] else "player", i["money"], i["r"], i["g"], i["b"], i["a"]))
    areas = b.get("areas", {}).get("list", [])
    cities = [a for a in areas if "name" in a]
    print("\nareas: %d (%d named): %s" % (len(areas), len(cities), ", ".join(
        t("battle_cityname_%03d" % a["name"], str(a["name"])) for a in cities[:20]) + (" ..." if len(cities) > 20 else "")))
    armies = b.get("armies", {}).get("list", [])
    on_map = [a for a in armies if a["info"]["hex"] != 0xFFFF]
    print("armies: %d (%d on the map, %d off-map / reinforcements), %d groups, next serial %s" % (
        len(armies), len(on_map), len(armies) - len(on_map), len(b.get("armies", {}).get("groups", [])),
        b.get("armies", {}).get("next_serial")))
    for a in armies[:12]:
        i = a["info"]
        g = a.get("general", {}).get("id")
        print("  #%-4d hex %-5s faction %-2d %-16s x%d hp %d/%d morale %s%s" % (
            i["serial"], i["hex"] if i["hex"] != 0xFFFF else "-", i["faction"], t("army_%d" % i["army"], str(i["army"])),
            i["number"], i["hp"], i["max_hp"], a.get("morale"), "  general " + t("general_%d" % g, str(g)) if g else ""))
    if len(armies) > 12:
        print("  ...")
    w = b.get("weather", {}).get("list", [])
    if w:
        print("weather:", ", ".join("type %d from round %d for %d" % (x.get("type", 0), x.get("round", 0), x.get("duration", 0)) for x in w))
    tree = b.get("ai_tree", [])
    print("AI behaviour tree (FlexBuffers): %d bytes" % len(tree))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m gog3btl", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("btl"); p.add_argument("--assets"); p.add_argument("--lang", default="en")
    p = sub.add_parser("dump"); p.add_argument("btl"); p.add_argument("json"); p.add_argument("--overlays", action="store_true")
    p = sub.add_parser("build"); p.add_argument("json"); p.add_argument("btl")
    a = ap.parse_args(argv)
    if a.cmd == "info":
        info(a.btl, a.assets or guess_assets(a.btl), a.lang)
    elif a.cmd == "dump":
        b = load(a.btl)
        if a.overlays:
            b = dict(b)
            b["_overlays_by_hex (ignored by build)"] = {str(k): v for k, v in overlays_by_hex(b).items()}
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(b, fh, ensure_ascii=False, indent=1)
        print("wrote", a.json)
    elif a.cmd == "build":
        with open(a.json, encoding="utf-8") as fh:
            b = json.load(fh)
        b = {k: v for k, v in b.items() if not k.startswith("_")}
        n = save(b, a.btl)
        print("wrote %s (%d bytes)" % (a.btl, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
