"""世界の生成。8x8タイルのタイルセットと、2048x2048ユニット(約16km四方)のタイルマップ。

1ユニット = 8m / 1タイル = 8ユニット = 64m。
タイルマップは 256x256 タイル。昼用と夜用の2枚を作る（夜は町と道路が点灯）。
"""
import random
import pyxel

TILE = 8
WORLD = 2048
TW = WORLD // TILE          # 256タイル

PAL = [0x0a0c14, 0x16244a, 0x2f4c86, 0x8fb4d8, 0x1b2e22, 0x2c4a30,
       0x42683c, 0x638d4c, 0x92b466, 0x7a6046, 0x244c7a, 0x4ce896,
       0xf0f4f0, 0xd04044, 0xf0b030, 0x3a3a46]

# ------------------------------------------------------------------ タイル定義
GRASS = (0, 0)
FIELDS = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0)]
FOREST = [(0, 1), (1, 1)]
CROP = [(2, 1), (3, 1)]
WATER = (0, 2)
ROAD_V, ROAD_H, ROAD_X = (0, 3), (1, 3), (2, 3)
TOWN = [(0, 4), (1, 4), (2, 4)]
# 南北滑走路: 通常 / しきい値 / 接地帯 / 目標点（左タイル・右タイル）
RW_L, RW_R = (0, 5), (1, 5)
RW_LT, RW_RT = (4, 5), (5, 5)
RW_LZ, RW_RZ = (2, 5), (3, 5)
RW_LA, RW_RA = (7, 5), (8, 5)
# 東西滑走路（上半分 / 下半分）
RW_T, RW_B = (0, 8), (1, 8)
RW_TT, RW_BT = (4, 8), (5, 8)
RW_TZ, RW_BZ = (2, 8), (3, 8)
RW_TA, RW_BA = (6, 8), (7, 8)
APRON = (6, 5)
TOWN_LIT = [(0, 6), (1, 6), (2, 6)]
ROAD_V_LIT, ROAD_H_LIT, ROAD_X_LIT = (0, 7), (1, 7), (2, 7)
APRON_LIT = (6, 7)

# ------------------------------------------------------------------ 空港
class Airport:
    """滑走路1本の空港。幅は2タイル(16ユニット=128m)固定。

    axis='NS': +y方向に伸びる。 axis='EW': +x方向に伸びる。
    タイル座標 (t0, t1) は伸びる方向の範囲、tc は幅方向の手前側タイル。
    """
    HALF = TILE          # 半幅 8ユニット

    def __init__(self, name, axis, tc, t0, t1):
        self.name = name
        self.axis = axis
        self.tc, self.t0, self.t1 = tc, t0, t1
        self.c = (tc + 1) * TILE                  # 中心線 [ユニット]
        self.a0, self.a1 = t0 * TILE, t1 * TILE   # 伸びる方向の両端

    @property
    def x(self):
        return self.c if self.axis == 'NS' else (self.a0 + self.a1) * 0.5

    @property
    def y(self):
        return (self.a0 + self.a1) * 0.5 if self.axis == 'NS' else self.c

    def _pt(self, along, lateral=0.0):
        """滑走路座標 -> ワールド座標。"""
        if self.axis == 'NS':
            return (self.c + lateral, along)
        return (along, self.c + lateral)

    def ends(self):
        """着陸方向2つ。(しきい値, 進入方位[deg], 滑走路番号)"""
        if self.axis == 'NS':
            return [(self.a0, 0.0, '36'), (self.a1, 180.0, '18')]
        return [(self.a0, 90.0, '09'), (self.a1, 270.0, '27')]

    def approach_end(self, ax, ay):
        """機体位置から、進入している側の端を選ぶ。"""
        along = ay if self.axis == 'NS' else ax
        e0, e1 = self.ends()
        if along < self.a0:
            return e0
        if along > self.a1:
            return e1
        return e0 if abs(along - self.a0) < abs(along - self.a1) else e1

    def sign(self, end):
        return 1.0 if end[0] == self.a0 else -1.0

    def dist_to_threshold(self, end, ax, ay):
        along = ay if self.axis == 'NS' else ax
        return (end[0] - along) * self.sign(end)

    # -------------------------------------------------- 灯火（ワールド座標）
    def edge_lights(self):
        out = []
        step = 24
        a = self.a0
        while a <= self.a1:
            out.append(self._pt(a, -self.HALF))
            out.append(self._pt(a, self.HALF))
            a += step
        return out

    def threshold_lights(self, end):
        return [self._pt(end[0], d) for d in (-6, -3, 0, 3, 6)]

    def papi(self, end):
        s = self.sign(end)
        return [self._pt(end[0] + s * 10, -22 + i * 4) for i in range(4)]

    def als(self, end):
        s = self.sign(end)
        bars = [[self._pt(end[0] - s * (12 + i * 11), d) for d in (-3, 0, 3)]
                for i in range(8)]
        cross = [self._pt(end[0] - s * (12 + 4 * 11), d)
                 for d in (-12, -9, -6, 6, 9, 12)]
        return bars, cross

    def apron_anchor(self):
        """エプロン中心（建物を置く基準）。"""
        return self._pt(self.a0 + 60, 34)


AIRPORTS = [
    Airport('CENTRAL', 'NS', 127, 120, 136),
    Airport('NORTH', 'EW', 44, 152, 168),
    Airport('WEST', 'NS', 59, 190, 206),
]
HOME = AIRPORTS[0]


class Landmark:
    """遊覧の見どころ。上空を通ると記録される。"""

    def __init__(self, name, tx, ty, radius=26.0):
        self.name = name
        self.x = tx * TILE
        self.y = ty * TILE
        self.radius = radius            # この距離[ユニット]まで近づけば到達


# 町・川・道の交点など、地形として見分けのつく場所に置く
LANDMARKS = [
    Landmark('EAST CITY', 162, 52),
    Landmark('SOUTH TOWN', 74, 176),
    Landmark('FAR CORNER', 214, 208),
    Landmark('MIDLANDS', 108, 96),
    Landmark('WEST VILLAGE', 30, 120),
    Landmark('RIVER BEND', 46, 54, 22.0),
    Landmark('EAST RIVER', 196, 130, 22.0),
    Landmark('CROSSROADS', 150, 198, 22.0),
]

# 目的地として順に選べるもの（空港のあとに見どころ）
DESTS = AIRPORTS + LANDMARKS

# 旧コードとの互換（滑走路36を指す）
RW_X, RW_Y0, RW_Y1 = HOME.c, HOME.a0, HOME.a1
RW_HALF = Airport.HALF


APT_NAMES = frozenset(a.name for a in AIRPORTS)


def is_airport(name):
    return name in APT_NAMES


def apt_short(name):
    """HUDと計器盤用の表示名。「NORTH」だけでは方角と紛らわしい。"""
    return ('%s APT' % name) if name in APT_NAMES else name


def nearest_airport(x, y):
    return min(AIRPORTS, key=lambda a: (a.x - x) ** 2 + (a.y - y) ** 2)


def _px(img, u, v, x, y, c):
    img.pset(u * 8 + x, v * 8 + y, c)


def _fill(img, uv, c):
    img.rect(uv[0] * 8, uv[1] * 8, 8, 8, c)


def make_tileset(img):
    """画像バンクに8x8タイルを描く。"""
    rnd = random.Random(4)
    img.cls(0)
    # 農地・草地
    for i, c in enumerate((6, 7, 5, 8, 9, 6, 8, 7)):
        uv = FIELDS[i]
        _fill(img, uv, c)
        for _ in range(3):                       # わずかなムラ
            _px(img, uv[0], uv[1], rnd.randrange(8), rnd.randrange(8),
                c + 1 if c < 9 else c - 1)
    # 森
    for uv in FOREST:
        _fill(img, uv, 4)
        for _ in range(10):
            _px(img, uv[0], uv[1], rnd.randrange(8), rnd.randrange(8), 5)
    # 畑の畝
    for i, uv in enumerate(CROP):
        _fill(img, uv, 8 if i == 0 else 9)
        for x in range(0 if i == 0 else 1, 8, 2):
            img.rect(uv[0] * 8 + x, uv[1] * 8, 1, 8, 7)
    # 水面
    _fill(img, WATER, 10)
    for _ in range(4):
        _px(img, WATER[0], WATER[1], rnd.randrange(8), rnd.randrange(8), 2)
    # 道路
    for uv, lit in ((ROAD_V, False), (ROAD_V_LIT, True)):
        _fill(img, uv, 6)
        img.rect(uv[0] * 8 + 3, uv[1] * 8, 2, 8, 15)
        if lit:
            _px(img, uv[0], uv[1], 2, 2, 14); _px(img, uv[0], uv[1], 5, 6, 14)
    for uv, lit in ((ROAD_H, False), (ROAD_H_LIT, True)):
        _fill(img, uv, 6)
        img.rect(uv[0] * 8, uv[1] * 8 + 3, 8, 2, 15)
        if lit:
            _px(img, uv[0], uv[1], 2, 2, 14); _px(img, uv[0], uv[1], 6, 5, 14)
    for uv, lit in ((ROAD_X, False), (ROAD_X_LIT, True)):
        _fill(img, uv, 6)
        img.rect(uv[0] * 8 + 3, uv[1] * 8, 2, 8, 15)
        img.rect(uv[0] * 8, uv[1] * 8 + 3, 8, 2, 15)
        if lit:
            _px(img, uv[0], uv[1], 1, 1, 14); _px(img, uv[0], uv[1], 6, 6, 14)
    # 町（昼／夜）
    for i in range(3):
        for uv, lit in ((TOWN[i], False), (TOWN_LIT[i], True)):
            _fill(img, uv, 5 if i else 6)
            r2 = random.Random(20 + i)
            for _ in range(5 + i):
                bx, by = r2.randrange(6), r2.randrange(6)
                bw, bh = r2.randrange(1, 3), r2.randrange(1, 3)
                img.rect(uv[0] * 8 + bx, uv[1] * 8 + by, bw, bh, 15 if lit else
                         r2.choice([15, 12, 9]))
                if lit and r2.random() < 0.65:
                    _px(img, uv[0], uv[1], bx, by, r2.choice([12, 14]))
    # 滑走路（南北向き: 左タイル / 右タイル）
    # センターラインはタイルに焼かず、scene.draw_centerline() が投影ポリゴンで描く。
    # 1テクセル=8m なので地上視点だとテクスチャの破線が巨大な白塊になってしまう。
    def _rw_ns(l, r, mark=None):
        _fill(img, l, 15); _fill(img, r, 15)
        img.rect(l[0] * 8, l[1] * 8, 1, 8, 12)              # 左端の縁線
        img.rect(r[0] * 8 + 7, r[1] * 8, 1, 8, 12)          # 右端の縁線
        if mark == 'zone':                                   # 接地帯標識
            for x in (2, 4):
                img.rect(l[0] * 8 + x, l[1] * 8 + 1, 1, 6, 12)
            for x in (3, 5):
                img.rect(r[0] * 8 + x, r[1] * 8 + 1, 1, 6, 12)
        elif mark == 'aim':                                  # 目標点標識
            img.rect(l[0] * 8 + 4, l[1] * 8 + 1, 2, 6, 12)
            img.rect(r[0] * 8 + 2, r[1] * 8 + 1, 2, 6, 12)
    _rw_ns(RW_L, RW_R)
    _rw_ns(RW_LZ, RW_RZ, 'zone')
    _rw_ns(RW_LA, RW_RA, 'aim')
    _fill(img, RW_LT, 15); _fill(img, RW_RT, 15)
    for x in (1, 3, 5, 7):                                    # しきい値標識
        img.rect(RW_LT[0] * 8 + x - 1, RW_LT[1] * 8 + 1, 1, 6, 12)
        img.rect(RW_RT[0] * 8 + x - 1, RW_RT[1] * 8 + 1, 1, 6, 12)
    # 滑走路（東西向き: 縦向きを90度回した意匠）
    def _rw_ew(t, b, mark=None):
        _fill(img, t, 15); _fill(img, b, 15)
        img.rect(t[0] * 8, t[1] * 8, 8, 1, 12)              # 上端の縁線
        img.rect(b[0] * 8, b[1] * 8 + 7, 8, 1, 12)          # 下端の縁線
        if mark == 'zone':
            for y in (2, 4):
                img.rect(t[0] * 8 + 1, t[1] * 8 + y, 6, 1, 12)
            for y in (3, 5):
                img.rect(b[0] * 8 + 1, b[1] * 8 + y, 6, 1, 12)
        elif mark == 'aim':
            img.rect(t[0] * 8 + 1, t[1] * 8 + 4, 6, 2, 12)
            img.rect(b[0] * 8 + 1, b[1] * 8 + 2, 6, 2, 12)
    _rw_ew(RW_T, RW_B)
    _rw_ew(RW_TZ, RW_BZ, 'zone')
    _rw_ew(RW_TA, RW_BA, 'aim')
    _fill(img, RW_TT, 15); _fill(img, RW_BT, 15)
    for y in (1, 3, 5, 7):
        img.rect(RW_TT[0] * 8 + 1, RW_TT[1] * 8 + y - 1, 6, 1, 12)
        img.rect(RW_BT[0] * 8 + 1, RW_BT[1] * 8 + y - 1, 6, 1, 12)
    # エプロン
    for uv, lit in ((APRON, False), (APRON_LIT, True)):
        _fill(img, uv, 15)
        for _ in range(3):
            _px(img, uv[0], uv[1], rnd.randrange(8), rnd.randrange(8),
                14 if lit else 5)


# ------------------------------------------------------------------ 世界
TOWN_CELLS = []
ROAD_CELLS = []
APRON_CELLS = []


def _river(tm, seed=3):
    rnd = random.Random(seed)
    x = 46.0
    for y in range(TW):
        x += rnd.uniform(-0.6, 0.6) + (46 - x) * 0.006
        tm.pset(int(x), y, WATER)
        if y % 3:
            tm.pset(int(x) + 1, y, WATER)
    x = 196.0
    for y in range(TW):
        x += rnd.uniform(-0.5, 0.5) + (196 - x) * 0.004
        tm.pset(int(x), y, WATER)


def _road_v(tm, x0, wobble, seed):
    rnd = random.Random(seed)
    x = float(x0)
    for y in range(TW):
        x += rnd.uniform(-wobble, wobble) + (x0 - x) * 0.02
        tm.pset(int(x), y, ROAD_V)
        ROAD_CELLS.append((int(x), y, ROAD_V_LIT))


def _road_h(tm, y0):
    for x in range(TW):
        cur = tm.pget(x, y0)
        t = ROAD_X if cur == ROAD_V else ROAD_H
        tm.pset(x, y0, t)
        ROAD_CELLS.append((x, y0, ROAD_X_LIT if t == ROAD_X else ROAD_H_LIT))


def _town(tm, cx, cy, r, seed):
    rnd = random.Random(seed)
    for _ in range(int(r * r * 2.6)):
        a = rnd.uniform(0, 6.283)
        d = rnd.uniform(0, 1) ** 0.6 * r
        x = int(cx + d * pyxel.cos(a * 57.2958))
        y = int(cy + d * pyxel.sin(a * 57.2958))
        if 0 <= x < TW and 0 <= y < TW:
            i = rnd.randrange(3)
            tm.pset(x, y, TOWN[i])
            TOWN_CELLS.append((x, y, TOWN_LIT[i]))


def _rw_tiles(d, ns):
    """滑走路端からのタイル数 d に応じた (手前側, 奥側) タイル。"""
    if d == 0:
        return (RW_LT, RW_RT) if ns else (RW_TT, RW_BT)     # しきい値標識
    if d in (2, 6):
        return (RW_LZ, RW_RZ) if ns else (RW_TZ, RW_BZ)     # 接地帯標識
    if d == 4:
        return (RW_LA, RW_RA) if ns else (RW_TA, RW_BA)     # 目標点標識
    return (RW_L, RW_R) if ns else (RW_T, RW_B)


def _airport(tm, ap):
    t0, t1, tc = ap.t0, ap.t1, ap.tc
    n = t1 - t0
    if ap.axis == 'NS':
        for y in range(t0 - 2, t1 + 3):
            for x in range(tc - 3, tc + 5):
                tm.pset(x, y, FIELDS[2])
        for y in range(t0, t1):
            i = y - t0
            a, b = _rw_tiles(min(i, n - 1 - i), True)
            tm.pset(tc, y, a)
            tm.pset(tc + 1, y, b)
        ax, ay = range(tc + 3, tc + 7), range(t0 + 6, t0 + 12)
    else:
        for x in range(t0 - 2, t1 + 3):
            for y in range(tc - 3, tc + 5):
                tm.pset(x, y, FIELDS[2])
        for x in range(t0, t1):
            i = x - t0
            a, b = _rw_tiles(min(i, n - 1 - i), False)
            tm.pset(x, tc, a)
            tm.pset(x, tc + 1, b)
        ax, ay = range(t0 + 6, t0 + 12), range(tc + 3, tc + 7)
    for x in ax:
        for y in ay:
            tm.pset(x, y, APRON)
            APRON_CELLS.append((x, y, APRON_LIT))


def make_world(tm_day, tm_night, seed=9):
    """昼用タイルマップを作り、夜用へ複製して町と道路を点灯させる。"""
    del TOWN_CELLS[:], ROAD_CELLS[:], APRON_CELLS[:]
    rnd = random.Random(seed)
    tm = tm_day
    tm.cls(GRASS)
    for _ in range(5200):                          # 農地のパッチワーク
        x, y = rnd.randrange(TW), rnd.randrange(TW)
        w, h = rnd.randrange(2, 8), rnd.randrange(2, 7)
        tm.rect(x, y, w, h, rnd.choice(FIELDS + CROP))
    for _ in range(700):                           # 森
        x, y = rnd.randrange(TW), rnd.randrange(TW)
        tm.circ(x, y, rnd.randrange(1, 5), rnd.choice(FOREST))
    _river(tm)
    for i, (x0, wob) in enumerate(((150, 0.35), (78, 0.25), (228, 0.3))):
        _road_v(tm, x0, wob, 30 + i)
    for y0 in (54, 130, 198):
        _road_h(tm, y0)
    for cx, cy, r, s in ((162, 52, 13, 1), (74, 176, 10, 2), (214, 208, 8, 3),
                         (108, 96, 7, 4), (30, 120, 6, 5)):
        _town(tm, cx, cy, r, s)
    for _ap in AIRPORTS:
        _airport(tm, _ap)
    # 夜用へ複製。1タイルずつ写すと65536回のループになって非力な機器で
    # 数十秒かかるので、Tilemap.blt で一度に転送する。
    tm_night.blt(0, 0, tm, 0, 0, TW, TW)
    for cells in (TOWN_CELLS, ROAD_CELLS, APRON_CELLS):
        for x, y, lit in cells:
            tm_night.pset(x, y, lit)


def make_clouds(img, seed=5, n=15):
    """雲テクスチャ（0=透明）。タイルマップで敷き詰めて空全体を覆う。"""
    rnd = random.Random(seed)
    img.cls(0)
    for _ in range(n):
        x, y = rnd.randrange(256), rnd.randrange(256)
        for _ in range(9):
            img.circ(x + rnd.randrange(-17, 17), y + rnd.randrange(-8, 8) + 3,
                     rnd.randrange(4, 10), 3)
        for _ in range(9):
            img.circ(x + rnd.randrange(-16, 16), y + rnd.randrange(-8, 8),
                     rnd.randrange(4, 10), 12)


def make_rain_clouds(img, seed=11, n=110):
    """雨雲。晴天の積雲より密で、色も暗い（下から見た雲底の色）。"""
    rnd = random.Random(seed)
    img.cls(0)
    for _ in range(n):
        x, y = rnd.randrange(256), rnd.randrange(256)
        for _ in range(12):                       # 暗い雲底
            img.circ(x + rnd.randrange(-22, 22), y + rnd.randrange(-11, 11),
                     rnd.randrange(5, 14), 15)
    for _ in range(n // 3):                       # ところどころ明るい切れ間
        x, y = rnd.randrange(256), rnd.randrange(256)
        for _ in range(5):
            img.circ(x + rnd.randrange(-14, 14), y + rnd.randrange(-7, 7),
                     rnd.randrange(3, 8), 3)


def make_cloud_shadow(dst, seed=5, n=13):
    """雲影テクスチャ。塗りは実体のままで、薄さは描画時の dither で出す。

    以前は1ピクセルずつ間引いていたが、65536回のループになって非力な機器では
    起動が数十秒延びるため、fx.draw_cloud_shadows 側の dither に任せている。
    """
    rnd = random.Random(seed)
    dst.cls(0)
    for _ in range(n):
        x, y = rnd.randrange(256), rnd.randrange(256)
        for _ in range(9):
            dst.circ(x + rnd.randrange(-16, 16), y + rnd.randrange(-8, 8),
                     rnd.randrange(4, 10), 5)


def tile_wrap(tm, src_tiles=32, scratch=7):
    """256x256画像を敷き詰めたタイルマップを作る（雲・雲影用）。

    1タイルずつ埋めると65536回のループになって非力な機器では時間がかかるので、
    32x32だけ作って Tilemap.blt で並べる。
    自分自身を転送元にすると Pyxel 2.9.9 が panic するため、別のタイルマップを経由する。
    """
    tmp = pyxel.tilemaps[scratch]
    for y in range(src_tiles):
        for x in range(src_tiles):
            tmp.pset(x, y, (x, y))
    for by in range(0, TW, src_tiles):
        for bx in range(0, TW, src_tiles):
            tm.blt(bx, by, tmp, 0, 0, src_tiles, src_tiles)


def apply_palette():
    for i, c in enumerate(PAL):
        pyxel.colors[i] = c


# ------------------------------------------------------------------ GPS表示色
_MAP_COL = {}
for _uv in FIELDS + CROP:
    _MAP_COL[_uv] = 0                      # 農地・草地は背景
for _uv in FOREST:
    _MAP_COL[_uv] = 5
_MAP_COL[WATER] = 10
for _uv in (ROAD_V, ROAD_H, ROAD_X, ROAD_V_LIT, ROAD_H_LIT, ROAD_X_LIT):
    _MAP_COL[_uv] = 15
for _uv in TOWN + TOWN_LIT:
    _MAP_COL[_uv] = 14
for _uv in (RW_L, RW_R, RW_LZ, RW_RZ, RW_LA, RW_RA, RW_LT, RW_RT,
            RW_T, RW_B, RW_TZ, RW_BZ, RW_TA, RW_BA, RW_TT, RW_BT,
            APRON, APRON_LIT):
    _MAP_COL[_uv] = 12


def tile_color(tile):
    """タイルをGPS上の色に落とす。町・道路・空港は固定色なので夜でも読める。"""
    return _MAP_COL.get(tuple(tile), 0)
