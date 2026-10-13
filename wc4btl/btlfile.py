"""World Conqueror 4 (v1.30.0) .btl battle-map reader/writer.

Section order and record sizes follow the game's own loader (see reference/WC4_1.30.0_engine_reference.md);
field meanings combine that reference with the field names used by EModule's BtlEditor and checks against
all 1383 shipped maps.  Every section, including the unknown 8-byte block (header 27) and the v3 trailing
bytes (header 21), is kept, so load -> save without edits reproduces the file byte for byte.

Faction references inside records (mines, reinforcements, air raids, events, faction generals, air support)
store the faction *id* (Faction.id).  The per-hex owner array stores the faction *index* (position in the list).
"""
import struct

# (key, struct code, original Chinese name, English label)
F = tuple


class RecordType:
    def __init__(self, name, fields):
        self.name = name
        self.fields = [F(f) for f in fields]
        self.keys = [f[0] for f in self.fields]
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.fmt = "<" + "".join(f[1] for f in self.fields)
        self.size = struct.calcsize(self.fmt)
        self._st = struct.Struct(self.fmt)

    def unpack(self, buf, off):
        return Record(self, list(self._st.unpack_from(buf, off)))

    def pack(self, rec):
        return self._st.pack(*rec.v)

    def new(self, **kw):
        r = Record(self, [0.0 if f[1] in "fd" else 0 for f in self.fields])
        for k, v in kw.items():
            r[k] = v
        return r

    def field(self, key):
        return self.fields[self.index[key]]


class Record:
    __slots__ = ("rt", "v")

    def __init__(self, rt, values):
        self.rt = rt
        self.v = values

    def __getitem__(self, k):
        return self.v[self.rt.index[k]]

    def __setitem__(self, k, val):
        code = self.rt.fields[self.rt.index[k]][1]
        self.v[self.rt.index[k]] = clamp(code, val)

    def get(self, k, default=None):
        i = self.rt.index.get(k)
        return default if i is None else self.v[i]

    def has(self, k):
        return k in self.rt.index

    def clone(self):
        return Record(self.rt, list(self.v))

    def __repr__(self):
        return "<%s %s>" % (self.rt.name, dict(zip(self.rt.keys, self.v)))


RANGES = {"B": (0, 255), "b": (-128, 127), "H": (0, 65535), "h": (-32768, 32767),
          "I": (0, 2**32 - 1), "i": (-2**31, 2**31 - 1)}


def clamp(code, val):
    if code in "fd":
        return float(val)
    lo, hi = RANGES[code]
    val = int(val)
    return lo if val < lo else hi if val > hi else val


def _u(n, prefix="u"):
    return (prefix + str(n), "B", "未知", "Unknown byte %d" % n)


MASTER = RecordType("Master", [
    ("version", "i", "Btl版本", "Version (1-3)"),
    ("map_index", "i", "地图序号", "World map index (0 = own terrain)"),
    ("crop_x", "i", "地图截取x", "World crop X"),
    ("crop_y", "i", "地图截取y", "World crop Y"),
    ("width", "i", "地图宽", "Width (hexes)"),
    ("height", "i", "地图高", "Height (hexes)"),
    ("n_factions", "i", "军团总数", "Factions"),
    ("n_cities", "i", "建筑总数", "Cities"),
    ("n_troops", "i", "军队总数", "Troops"),
    ("n_schemes", "i", "方案总数", "Schemes"),
    ("n_events", "i", "事件总数", "Events"),
    ("n_weather", "i", "天气总数", "Weather"),
    ("victory", "i", "胜利条件", "Victory condition"),
    ("min_round", "i", "最小回合", "Victory round"),
    ("max_round", "i", "最大回合", "Great-victory round"),
    ("n_reinf", "i", "援军总数", "Reinforcements"),
    ("n_airraids", "i", "空袭总数", "Air raids"),
    ("n_deploy_a", "i", "放置单位A", "Deploy slots A"),
    ("n_deploy_b", "i", "放置单位B", "Deploy slots B"),
    ("n_capitals", "i", "国家首都", "Capitals / key areas"),
    ("era", "i", "战役时代", "Era / flags"),
    ("n_tail", "i", "尾部字节", "Trailing bytes (v3)"),
    ("n_hexes", "i", "地块总数", "Hex count"),
    ("stock_money", "i", "积攒金钱", "Stockpile money"),
    ("stock_industry", "i", "积攒齿轮", "Stockpile industry"),
    ("stock_energy", "i", "积攒原子", "Stockpile energy"),
    ("n_mines", "i", "陷阱总数", "Mines"),
    ("n_s27", "i", "未知8字节段", "Unknown 8-byte records"),
    ("n_generals", "i", "战略总数", "Faction generals"),
    ("h29", "i", "empty6", "Header 29"),
    ("h30", "i", "empty7", "Header 30"),
    ("n_airsupport", "i", "空中支援", "Air support"),
])
COUNT_KEYS = {"n_factions", "n_cities", "n_troops", "n_schemes", "n_events", "n_weather", "n_reinf",
              "n_airraids", "n_deploy_a", "n_deploy_b", "n_capitals", "n_tail", "n_hexes", "n_mines",
              "n_s27", "n_generals", "n_airsupport"}

TECHS = [
    ("机动等级", "Mobility"), ("步枪等级", "Rifle"), ("迷彩等级", "Camouflage"), ("工兵等级", "Sapper"),
    ("手雷等级", "Grenade"), ("迫击炮等级", "Mortar"), ("行军等级", "Marching"), ("防弹衣等级", "Body armour"),
    ("装甲等级", "Tank armor"), ("主炮等级", "Main gun"), ("车体等级", "Vehicle body"), ("引擎等级", "Engine"),
    ("机枪等级", "Machine gun"), ("突袭等级", "Assault"), ("坦克防空等级", "Tank air defense"),
    ("强化车体等级", "Reinforced vehicle"), ("火炮炮击等级", "Artillery shelling"), ("火箭弹等级", "Rocket shells"),
    ("火炮牵引等级", "Traction"), ("火炮装甲等级", "Artillery armor"), ("火炮火力等级", "Artillery firepower"),
    ("火炮火箭等级", "Artillery rockets"), ("伪装等级", "Disguise"), ("舰艇船体等级", "Hull"),
    ("推进器等级", "Propeller"), ("舰艇装甲等级", "Ship armor"), ("武器等级", "Ship weapons"),
    ("舰艇舰炮等级", "Naval guns"), ("鱼雷等级", "Torpedo"), ("舰艇扫雷", "Minesweeping"),
    ("防空武器等级", "Ship air defense"), ("现代舰艇等级", "Modern ships"), ("航空燃油等级", "Aircraft fuel"),
    ("航空发动机等级", "Aircraft engine"), ("航空炸弹等级", "Aircraft bombs"), ("空袭等级", "Air strike"),
    ("轰炸等级", "Bombing"), ("战略轰炸等级", "Strategic bombing"), ("空降兵等级", "Airborne"),
    ("喷气发动机等级", "Jet engine"), ("机枪堡等级", "Bunker"), ("要塞炮等级", "Land fort"),
    ("海岸炮等级", "Coastal artillery"), ("火箭发射器等级", "Rocket launcher"), ("工事等级", "Fortifications"),
    ("高射机枪等级", "AA machine gun"), ("防空炮等级", "AA artillery"), ("对空导弹等级", "AA missile"),
    ("雷达等级", "Radar"), ("弹头", "Warhead"), ("固体火箭发动机等级", "Solid rocket engine"),
    ("破防等级", "Break defense"), ("核聚变等级", "Nuclear fusion"),
]
TECH_KEYS = ["tech_%d" % i for i in range(len(TECHS))]

FACTION = RecordType("Faction", [
    ("id", "i", "序号", "Faction id"),
    ("country", "i", "国家", "Country"),
    ("money", "i", "金钱", "Money"),
    ("industry", "i", "齿轮", "Industry"),
    ("energy", "i", "原子", "Energy"),
    ("ai", "i", "控制", "AI controlled (0 = player side)"),
    ("alliance", "i", "阵营", "Alliance"),
    ("defeat", "i", "战败条件", "Defeat condition"),
    ("unit_bonus", "f", "兵种加成", "Unit bonus factor"),
    ("tax_bonus", "f", "税率加成", "Tax bonus factor"),
    ("r", "B", "R8", "Color R"), ("g", "B", "G8", "Color G"), ("b", "B", "B8", "Color B"), ("a", "B", "A8", "Color A"),
    ("atomic", "i", "原子弹数量", "Atomic bombs"),
    ("hydrogen", "i", "氢弹数量", "Hydrogen bombs"),
    ("triphase", "i", "三相弹数量", "Tri-phase bombs"),
    ("antimatter", "i", "反物质弹数量", "Antimatter bombs"),
] + [(TECH_KEYS[i], "i", cn, en) for i, (cn, en) in enumerate(TECHS)] + [
    ("x68", "i", "empty1", "Unknown 68"), ("x69", "i", "empty2", "Unknown 69"), ("x70", "i", "empty3", "Unknown 70"),
    ("strategy_group", "i", "empty4", "AI strategy group (def_strategy)"),
    ("tech_level", "i", "科技等级", "Tech level"),
    ("x73", "i", "empty5", "Unknown 73"), ("x74", "i", "empty6", "Unknown 74"),
])

TERRAIN = RecordType("Terrain", [
    ("terrain", "B", "地块类型", "Terrain type"), ("tile", "B", "地块ID", "Tile"),
    ("tx", "b", "地块X", "Offset X"), ("ty", "b", "地块Y", "Offset Y"),
    ("a_terrain", "B", "装饰类型A", "Decor A type"), ("a_tile", "B", "装饰AID", "Decor A tile"),
    ("ax", "b", "装饰AX", "Decor A X"), ("ay", "b", "装饰AY", "Decor A Y"),
    ("b_terrain", "B", "装饰类型B", "Decor B type"), ("b_tile", "B", "装饰BID", "Decor B tile"),
    ("bx", "b", "装饰BX", "Decor B X"), ("by", "b", "装饰BY", "Decor B Y"),
    ("water_edge", "B", "水边缘", "Water edge"), ("road_edge", "B", "路边缘", "Road edge"),
    ("coast", "B", "海岸", "Coast"), ("t15", "B", "empty", "Unknown"),
])

CITY = RecordType("City", [
    ("hex", "H", "坐标", "Hex"),
    ("name", "h", "名称", "Name id (battle_cityname_NNN)"),
    ("building", "B", "等级", "Building (BuildingSettings id)"),
    ("look", "B", "外观", "Appearance"),
    ("landmark", "B", "地标", "Landmark"),
    ("wonder", "B", "奇观", "Capital image (capital_NN)"),
    ("reward_type", "h", "奖励类型", "Reward type"),
    ("reward_amount", "h", "奖励数量", "Reward amount"),
    ("hatred", "B", "仇恨值", "Hatred"),
    ("stronghold", "B", "据点", "Stronghold ring"),
    ("trigger", "B", "触发事件", "Trigger event"),
    _u(15), _u(16), _u(17), _u(18),
    ("transport", "B", "运输船", "Transport"),
    ("fire_type", "B", "火焰类型", "Fire type"),
    ("fire_rounds", "B", "持续回合", "Fire rounds"),
    ("aa", "B", "防空武器", "Air defense (AirDefence id)"),
    ("aa_range", "B", "防空武器范围", "Air defense range"),
    ("factory", "B", "工厂", "Factory level"),
    ("lab", "B", "科技", "Lab level"),
    ("depot", "B", "补给站", "Supply depot level"),
    ("airport", "B", "航空", "Airport level"),
    ("missile", "B", "导弹", "Missile base level"),
    ("nuke", "B", "核弹", "Nuke factory level"),
    _u(30), _u(31),
])

_TROOP_BASE = [
    ("hex", "H", "坐标", "Hex"),
    ("army", "B", "兵种", "Army code"),
    ("level", "B", "等级", "Level (elite: tier 1-12)"),
    ("formation", "B", "编制", "Formation count"),
    ("facing", "B", "方向", "Facing"),
    ("mobility", "B", "移动力", "Mobility left"),
    ("build_rounds", "B", "建造回合", "Build rounds"),
    ("exp", "h", "兵种经验", "Experience"),
    ("hp_bonus", "h", "血量加成", "HP %"),
    ("hp", "h", "当前血量", "Current HP"),
    ("hp_max", "h", "血量上限", "Max HP"),
    ("general", "h", "将领", "General id"),
    ("rank", "B", "军衔", "General rank"),
    ("quality", "B", "爵位", "General quality"),
    ("medal1", "B", "胸章一", "Medal 1"), ("medal2", "B", "胸章二", "Medal 2"), ("medal3", "B", "胸章三", "Medal 3"),
    ("skill1", "B", "技能等级1", "Skill 1 level"), ("skill2", "B", "技能等级2", "Skill 2 level"),
    ("skill3", "B", "技能等级3", "Skill 3 level"), ("skill4", "B", "技能等级4", "Skill 4 level"),
    ("skill5", "B", "技能等级5", "Skill 5 level"),
    ("stronghold", "B", "据点", "Stronghold ring"),
    ("ai", "B", "方针", "AI order"),
    ("transport", "B", "运输船", "Transport"),
    ("hatred", "B", "仇恨值", "Hatred"),
    ("move_target", "h", "移动目标", "Move target hex (-1 none)"),
    _u(34), _u(35),
    ("scheme", "h", "行为方案", "Behaviour scheme"),
    ("change_round", "h", "改变回合", "Order change round"),
    ("morale", "b", "士气", "Morale"),
    ("morale_rounds", "B", "士气持续回合", "Morale rounds"),
    ("trigger", "B", "触发事件", "Trigger event"),
    ("shield", "B", "盾牌标志", "Shield / hold flag"),
    # EModule reads 44-47 as one int "hold min distance"; byte 47 is really the elite skin index (the map loader reads
    # troop byte 0x2f into army init; drawing looks up "<Anim> skin_<n>" in def_motion.xml).  45-46 are 0 in every map.
    ("hold_dist", "H", "固守最短距离", "Hold min distance"),
    _u(46),
    ("skin", "B", "皮肤", "Elite skin (0 = default look)"),
]
TROOP1 = RecordType("Troop", _TROOP_BASE)
TROOP3 = RecordType("Troop", _TROOP_BASE + [
    ("v3_medal1", "B", "勋章1", "Medal 1 (v2/v3)"), ("v3_medal2", "B", "勋章2", "Medal 2 (v2/v3)"),
    ("v3_medal3", "B", "勋章3", "Medal 3 (v2/v3)"),
    ("ribbon1", "B", "勋带1", "Ribbon 1"), ("ribbon2", "B", "勋带2", "Ribbon 2"), ("ribbon3", "B", "勋带3", "Ribbon 3"),
    ("x54", "H", "empty", "Unknown 54"), ("x56", "H", "empty", "Unknown 56"), ("x58", "H", "empty", "Unknown 58"),
    ("x60", "i", "empty9", "Unknown 60"),
])

MINE = RecordType("Mine", [
    ("hex", "H", "坐标", "Hex"),
    ("owner", "H", "所属军团", "Owner faction id"),
    ("level", "H", "陷阱编制", "Level (1-4)"),
    ("hp", "H", "陷阱血量", "HP"),
    ("army", "H", "兵种", "Army code (33 land / 34 sea)"),
    ("x10", "H", "empty", "Unknown"),
])

SCHEME = RecordType("Scheme", [
    ("scheme_id", "i", "方案编号", "Scheme id"),
    ("end_event", "i", "终结事件", "End event"),
    ("round", "i", "触发回合", "Trigger round"),
    ("target", "i", "目标地块", "Target hex"),
])

WEATHER = RecordType("Weather", [
    ("type", "i", "天气类型", "Weather type"),
    ("x4", "i", "empty", "Unknown"),
    ("round", "i", "触发回合", "Start round"),
    ("duration", "i", "持续回合", "Duration"),
])

EVENT = RecordType("Event", [
    ("event_id", "i", "事件ID", "Event id"),
    ("linked", "i", "关联事件", "Linked event"),
    ("condition", "i", "触发条件", "Trigger condition"),
    ("action", "i", "事件类型", "Event type"),
    ("trigger_faction", "i", "触发军团", "Trigger faction id"),
    ("affect_faction", "i", "影响军团", "Affected faction id"),
    ("target", "i", "目标值", "Target value"),
    ("x28", "i", "Zero", "Unknown"),
    ("round", "i", "触发回合", "Trigger round"),
    ("dialogue", "i", "对话代码", "Dialogue id"),
    ("end_part", "i", "默认结束段", "Default end segment"),
])

_REINF_BASE = [
    ("hex", "i", "坐标", "Hex"),
    ("army", "i", "兵种", "Army code"),
    ("level", "i", "等级", "Level (elite: tier)"),
    ("formation", "i", "编制", "Formation count"),
    ("transport", "i", "运输船", "Transport"),
    ("ai", "i", "方针", "AI order"),
    ("x24", "i", "empty1", "Unknown 24"),
    ("general", "i", "将领", "General id"),
    ("rank", "i", "军衔", "General rank"),
    ("quality", "i", "爵位", "General quality"),
    ("skill1", "i", "技能等级1", "Skill 1 level"), ("skill2", "i", "技能等级2", "Skill 2 level"),
    ("skill3", "i", "技能等级3", "Skill 3 level"), ("skill4", "i", "技能等级4", "Skill 4 level"),
    ("skill5", "i", "技能等级5", "Skill 5 level"),
]
REINF1 = RecordType("Reinforcement", _REINF_BASE + [
    ("medal1", "i", "胸章一", "Medal 1"), ("medal2", "i", "胸章二", "Medal 2"), ("medal3", "i", "胸章三", "Medal 3"),
    ("country", "i", "所属国家", "Faction id"),
    ("round", "i", "爆兵回合", "Arrival round"),
])
REINF3 = RecordType("Reinforcement", _REINF_BASE + [
    ("medal1", "i", "勋章1", "Medal 1"), ("medal2", "i", "勋章2", "Medal 2"), ("medal3", "i", "勋章3", "Medal 3"),
    ("country", "i", "所属国家", "Faction id"),
    ("round", "i", "爆兵回合", "Arrival round"),
    ("medal4", "i", "胸章1", "Medal 4"), ("medal5", "i", "胸章2", "Medal 5"), ("medal6", "i", "胸章3", "Medal 6"),
    ("ribbon1", "i", "勋带1", "Ribbon 1"), ("ribbon2", "i", "勋带2", "Ribbon 2"), ("ribbon3", "i", "勋带3", "Ribbon 3"),
])

AIRRAID = RecordType("AirRaid", [
    ("hex", "i", "坐标", "Target hex"),
    ("army", "h", "兵种", "Army code"),
    ("elite_army", "h", "精英兵种", "Elite army id"),
    ("ammo", "i", "弹药", "Ammo"),
    ("faction", "i", "军团", "Faction id"),
    ("round", "i", "回合", "Round"),
])

DEPLOY = RecordType("Deploy", [
    ("hex", "H", "坐标", "Hex (65535 = empty)"),
    ("x2", "H", "empty", "Unknown"),
    ("facing", "B", "方向", "Facing"),
    ("slot", "B", "Id", "Slot id"),
    ("transport", "B", "运输船", "Transport"),
    ("x7", "B", "empty2", "Unknown"),
])

CAPITAL = RecordType("Capital", [
    ("hex", "H", "坐标", "Hex"),
    ("x2", "H", "empty", "Unknown"),
])

S27 = RecordType("Unknown8", [("a", "i", "?", "Value A"), ("b", "i", "?", "Value B")])

GENERAL = RecordType("FactionGeneral", [
    ("faction", "i", "军团序号", "Faction id"),
    ("x4", "i", "empty", "Unknown"),
    ("flag", "i", "回合", "Flag / round"),
    ("general", "i", "建设代码", "General id"),
])

AIRSUPPORT = RecordType("AirSupport", [
    ("army", "i", "兵种", "Army code"),
    ("ammo", "i", "弹药", "Ammo"),
    ("faction", "i", "军团", "Faction id"),
    ("round", "i", "回合", "Round"),
])


class BtlFile:
    """Whole .btl file as Python lists.  Header counts are recomputed on save."""

    def __init__(self):
        self.master = MASTER.new(version=3)
        self.factions = []
        self.terrain = []        # per hex (only when master.map_index == 0)
        self.provinces = []      # u16 per hex: hex id (file coordinates) of the city owning this hex, 0xFFFF none
        self.owners = []         # u8 per hex: faction INDEX, 255 none
        self.cities = []
        self.troops = []
        self.mines = []
        self.schemes = []
        self.weather = []
        self.events = []
        self.reinforcements = []
        self.airraids = []
        self.deploy_a = []
        self.deploy_b = []
        self.capitals = []
        self.s27 = []
        self.generals = []
        self.airsupport = []
        self.tail = b""

    # record types depending on version
    @property
    def version(self):
        return self.master["version"]

    def troop_type(self):
        return TROOP1 if self.version == 1 else TROOP3

    def reinf_type(self):
        return REINF1 if self.version == 1 else REINF3

    @property
    def own_terrain(self):
        return self.master["map_index"] == 0

    @property
    def width(self):
        return self.master["width"]

    @property
    def height(self):
        return self.master["height"]

    @property
    def hex_count(self):
        n = self.master["n_hexes"]
        return n if n > 0 else self.width * self.height

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            return cls.parse(fh.read())

    @classmethod
    def parse(cls, data):
        self = cls()
        pos = 0

        def take(rt, n):
            nonlocal pos
            if n < 0 or pos + rt.size * n > len(data):
                raise ValueError("file is truncated in section %s" % rt.name)
            out = [rt.unpack(data, pos + i * rt.size) for i in range(n)]
            pos += rt.size * n
            return out

        self.master = take(MASTER, 1)[0]
        m = self.master
        if m["version"] not in (1, 2, 3):
            raise ValueError("unknown .btl version %d" % m["version"])
        self.factions = take(FACTION, m["n_factions"])
        n = self.hex_count
        if self.own_terrain:
            self.terrain = take(TERRAIN, m["width"] * m["height"])
        if pos + 3 * n > len(data):
            raise ValueError("file is truncated in the province/owner arrays")
        self.provinces = list(struct.unpack_from("<%dH" % n, data, pos)); pos += 2 * n
        self.owners = list(data[pos:pos + n]); pos += n
        self.cities = take(CITY, m["n_cities"])
        self.troops = take(self.troop_type(), m["n_troops"])
        self.mines = take(MINE, m["n_mines"])
        self.schemes = take(SCHEME, m["n_schemes"])
        self.weather = take(WEATHER, m["n_weather"])
        self.events = take(EVENT, m["n_events"])
        self.reinforcements = take(self.reinf_type(), m["n_reinf"])
        self.airraids = take(AIRRAID, m["n_airraids"])
        self.deploy_a = take(DEPLOY, m["n_deploy_a"])
        self.deploy_b = take(DEPLOY, m["n_deploy_b"])
        self.capitals = take(CAPITAL, m["n_capitals"])
        self.s27 = take(S27, m["n_s27"])
        self.generals = take(GENERAL, m["n_generals"])
        self.airsupport = take(AIRSUPPORT, m["n_airsupport"])
        if m["version"] >= 3 and m["n_tail"] > 0:
            self.tail = data[pos:pos + m["n_tail"]]; pos += m["n_tail"]
        if pos != len(data):
            raise ValueError("unexpected file size: parsed %d of %d bytes" % (pos, len(data)))
        return self

    def update_counts(self):
        m = self.master
        m["n_factions"] = len(self.factions)
        m["n_cities"] = len(self.cities)
        m["n_troops"] = len(self.troops)
        m["n_mines"] = len(self.mines)
        m["n_schemes"] = len(self.schemes)
        m["n_weather"] = len(self.weather)
        m["n_events"] = len(self.events)
        m["n_reinf"] = len(self.reinforcements)
        m["n_airraids"] = len(self.airraids)
        m["n_deploy_a"] = len(self.deploy_a)
        m["n_deploy_b"] = len(self.deploy_b)
        m["n_capitals"] = len(self.capitals)
        m["n_s27"] = len(self.s27)
        m["n_generals"] = len(self.generals)
        m["n_airsupport"] = len(self.airsupport)
        if m["version"] >= 3:
            m["n_tail"] = len(self.tail)
        if m["n_hexes"] != 0 or len(self.owners) != m["width"] * m["height"]:
            m["n_hexes"] = len(self.owners)

    def serialize(self):
        self.update_counts()
        n = self.hex_count
        if len(self.provinces) != n or len(self.owners) != n:
            raise ValueError("province/owner arrays must have %d entries" % n)
        if self.own_terrain and len(self.terrain) != self.width * self.height:
            raise ValueError("terrain must have width*height entries")
        out = [MASTER.pack(self.master)]
        out += [FACTION.pack(r) for r in self.factions]
        if self.own_terrain:
            out += [TERRAIN.pack(r) for r in self.terrain]
        out.append(struct.pack("<%dH" % n, *self.provinces))
        out.append(bytes(self.owners))
        tt, rt = self.troop_type(), self.reinf_type()
        for rows, typ in ((self.cities, CITY), (self.troops, tt), (self.mines, MINE), (self.schemes, SCHEME),
                          (self.weather, WEATHER), (self.events, EVENT), (self.reinforcements, rt),
                          (self.airraids, AIRRAID), (self.deploy_a, DEPLOY), (self.deploy_b, DEPLOY),
                          (self.capitals, CAPITAL), (self.s27, S27), (self.generals, GENERAL),
                          (self.airsupport, AIRSUPPORT)):
            for r in rows:
                if r.rt is not typ:
                    r = convert(r, typ)
                out.append(typ.pack(r))
        if self.version >= 3:
            out.append(bytes(self.tail))
        return b"".join(out)

    def save(self, path):
        data = self.serialize()
        with open(path, "wb") as fh:
            fh.write(data)
        return len(data)


def convert(rec, typ):
    """Copy a record into another record type with matching keys (e.g. v1 troop -> v3 troop)."""
    if rec.rt is typ:
        return rec
    new = typ.new()
    for k, v in zip(rec.rt.keys, rec.v):
        if k in typ.index:
            new[k] = v
    return new


ALL_TYPES = [MASTER, FACTION, TERRAIN, CITY, TROOP1, TROOP3, MINE, SCHEME, WEATHER, EVENT, REINF1, REINF3,
             AIRRAID, DEPLOY, CAPITAL, S27, GENERAL, AIRSUPPORT]
