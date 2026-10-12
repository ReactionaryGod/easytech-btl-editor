import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from wc4btl.gamedata import GameData
from wc4btl.model import BtlDoc
from wc4btl.btlfile import BtlFile

WORK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "World Conqueror 4_1.30.0_learning")
g = GameData(WORK)
for lvl, msg in g.log:
    if lvl != "ok": print(lvl, msg)
print("assets", g.assets, "armies", len(g.armies), "generals", len(g.generals), "atlases", sorted(g.atlases), "world", g.world.width, g.world.height)
stage = os.path.join(g.assets, "stage")
for fn in ("stage10101.btl", "conquest1.btl", "event10201.btl", "warzone101.btl", "frontier10101.btl"):
    d = BtlDoc(os.path.join(stage, fn), g)
    orig = d.snapshot()
    print(fn, "W,H", d.W, d.H, "world" if d.world else "own", "cities", len(d.city_at), "troops", len(d.troop_at),
          "cityhp", len(d.cityhp_at), "reinf hexes", len(d.reinf_at), "unplaced troops", len(d.btl.troops) - len(d.troop_at) - len(d.cityhp_at))
    # edits + undo
    empty = next(i for i in range(d.n) if i not in d.troop_at and not d.is_sea(i))
    d.begin(); d.set_troop(empty, None)
    src = empty
    dst = next(i for i in range(d.n) if i not in d.troop_at and i != src)
    d.begin(); assert d.move_troop(src, dst)
    d.begin(); d.delete_troop(dst)
    d.begin(); d.set_city(empty); d.begin(); d.add_city_hp(empty); d.begin(); d.add_reinforcement(empty)
    d.begin(); d.add_mine(empty); d.begin(); d.add_capital(empty); d.begin(); d.add_airraid(empty)
    d.begin(); d.add_faction(); d.begin(); d.delete_faction(len(d.btl.factions) - 1)
    BtlFile.parse(d.snapshot())          # still a valid file
    while d.undo(): pass
    assert d.snapshot() == orig, "undo did not restore the original"
    c = d.crop(2, 2, min(d.W - 1, 20), min(d.H - 1, 12))
    data = c.serialize(); c2 = BtlFile.parse(data)
    print("   crop ->", c2.width, c2.height, "factions", len(c2.factions), "cities", len(c2.cities), "troops", len(c2.troops), "bytes", len(data))
print("OK")
