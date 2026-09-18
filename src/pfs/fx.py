"""フライトシムの演出レイヤ。空・雲・大気・光源・灯火。"""
import math
import pyxel

FOV = 60.0
_OFF = None

def _off():
    global _OFF
    if _OFF is None:
        _OFF = pyxel.Image(256, 256)
    return _OFF

# ---------------------------------------------------------------- 時刻パレット
# 11,13,14,15,0 はUI用に固定。空(1,2,3)・地表(4-8)・岩(9)・水(10)・雲(12)を差し替える。
TOD = {
    'day':    [0x0a0c14, 0x16244a, 0x2f4c86, 0x8fb4d8, 0x1b2e22, 0x2c4a30, 0x42683c,
               0x638d4c, 0x92b466, 0x7a6046, 0x244c7a, 0x4ce896, 0xf0f4f0, 0xd04044,
               0xf0b030, 0x3a3a46],
    'golden': [0x0a0c14, 0x2a2a60, 0x7a5a8c, 0xf0a860, 0x1a2018, 0x2e3521, 0x4c4f2a,
               0x7d6a38, 0xc09052, 0x8a5a3a, 0x4a5a8a, 0x4ce896, 0xffd8a0, 0xd04044,
               0xf0b030, 0x3a3a46],
    'dusk':   [0x0a0c14, 0x0e1030, 0x24265c, 0x6e4a78, 0x0e1418, 0x161f1c, 0x243029,
               0x364638, 0x4e6048, 0x3a3038, 0x1a2a48, 0x4ce896, 0xb0a0c0, 0xd04044,
               0xf0b030, 0x3a3a46],
    'night':  [0x05060c, 0x04050d, 0x090d20, 0x232a4a, 0x030606, 0x06090a, 0x090f0e,
               0x0d1411, 0x121a15, 0x0d0a0a, 0x040810, 0x4ce896, 0xfff4d0, 0xe05050,
               0xffc040, 0x0c0c14],
}

def _lerp_rgb(a, b, t):
    out = 0
    for sh in (16, 8, 0):
        ca, cb = (a >> sh) & 255, (b >> sh) & 255
        out |= int(ca + (cb - ca) * t + 0.5) << sh
    return out

_TOD_CACHE = None


def invalidate():
    """次の apply_tod で必ずパレットを塗り直させる。"""
    global _TOD_CACHE
    _TOD_CACHE = None


def apply_tod(name, blend=None, t=0.0, alt=0.0):
    """パレットを時刻に合わせる。altが高いほど天頂を暗くして高高度感を出す。

    毎フレーム16色書き戻すのは無駄なので、内容が変わったときだけ適用する。
    """
    global _TOD_CACHE
    key = (name, blend, round(t, 2), int(alt / 8.0))
    if key == _TOD_CACHE:
        return
    _TOD_CACHE = key
    base = TOD[name]
    cols = list(base if blend is None else
                [_lerp_rgb(a, b, t) for a, b in zip(base, TOD[blend])])
    if alt > 60:                       # 高高度: 天頂を締める
        k = min(1.0, (alt - 60) / 140.0) * 0.55
        cols[1] = _lerp_rgb(cols[1], 0x080a20, k)
        cols[2] = _lerp_rgb(cols[2], cols[1], k * 0.5)
        cols[3] = _lerp_rgb(cols[3], cols[2], k * 0.45)
    for i, c in enumerate(cols):
        pyxel.colors[i] = c

# ---------------------------------------------------------------- 水平線の座標系
def horizon_frame(rect, pitch, roll):
    """水平線上の一点と機体上方向ベクトル、焦点距離を返す。"""
    x, y, w, h = rect
    f = (h / 2) / math.tan(math.radians(FOV / 2))
    a = math.radians(-roll)            # 地表はblt3dの反転を経て-rollだけ回る
    ux, uy = math.sin(a), -math.cos(a)
    d = f * math.tan(math.radians(pitch))
    return (x + w / 2 - ux * d, y + h / 2 - uy * d, ux, uy, f)

def band(hx, hy, ux, uy, t0, t1, col):
    """水平線からの距離 t0..t1 の帯を回転矩形で塗る（三角形2枚）。"""
    ax, ay = -uy, ux
    L = 420.0
    x0, y0 = hx + ux * t0, hy + uy * t0
    x1, y1 = hx + ux * t1, hy + uy * t1
    pyxel.tri(x0 - ax * L, y0 - ay * L, x0 + ax * L, y0 + ay * L,
              x1 + ax * L, y1 + ay * L, col)
    pyxel.tri(x0 - ax * L, y0 - ay * L, x1 + ax * L, y1 + ay * L,
              x1 - ax * L, y1 - ay * L, col)

# ---------------------------------------------------------------- 空
def draw_sky(rect, pitch, roll):
    x, y, w, h = rect
    hx, hy, ux, uy, f = horizon_frame(rect, pitch, roll)
    pyxel.clip(x, y, w, h)
    pyxel.rect(x, y, w, h, 3)
    t1 = f * math.tan(math.radians(6.0))
    t2 = f * math.tan(math.radians(18.0))
    band(hx, hy, ux, uy, t1, 900, 2)
    pyxel.dither(0.5); band(hx, hy, ux, uy, t1 * 0.55, t1, 2); pyxel.dither(1.0)
    band(hx, hy, ux, uy, t2, 900, 1)
    pyxel.dither(0.5); band(hx, hy, ux, uy, t2 * 0.78, t2, 1); pyxel.dither(1.0)
    pyxel.clip()

# 霞み始める距離[ユニット]と濃さ。遠い順。
HAZE_STEPS = ((None, 3600.0, 0.52), (3600.0, 2300.0, 0.40), (2300.0, 1600.0, 0.29),
              (1600.0, 1100.0, 0.19), (1100.0, 750.0, 0.10))


def fog(rect, amount, col=3):
    """視界不良。画面全体を霞み色で覆う。灯火より前に描いて、灯火だけ残す。"""
    if amount <= 0.02:
        return
    x, y, w, h = rect
    pyxel.dither(min(1.0, amount))
    pyxel.rect(x, y, w, h, col)
    pyxel.dither(1.0)


def draw_haze(rect, pitch, roll, alt=20.0, strength=1.0, scale=1.0):
    """水平線の手前側を霞ませる。

    帯の位置は「見下ろし角」ではなく「地上までの距離」で決める。
    そのため低空では帯が水平線際に圧縮され、手前の視界が開ける。
    """
    x, y, w, h = rect
    hx, hy, ux, uy, f = horizon_frame(rect, pitch, roll)
    a = max(0.3, alt)
    pyxel.clip(x, y, w, h)
    for d_far, d_near, dens in HAZE_STEPS:
        t_far = 0.0 if d_far is None else -f * (a / (d_far * scale))
        t_near = -f * (a / (d_near * scale))
        if t_near > -0.6:                      # 画面上で潰れる帯は描かない
            continue
        pyxel.dither(dens * strength)
        band(hx, hy, ux, uy, t_near, t_far, 3)
    pyxel.dither(1.0)
    pyxel.clip()

# ---------------------------------------------------------------- 雲
def draw_cloud_plane(rect, cam, pitch, hdg, roll, dz, tm=1):
    """dz = 雲層の高度 - 機体高度。正なら頭上、負なら足下に描かれる。"""
    x, y, w, h = rect
    o = _off(); o.cls(0)
    o.bltm3d(0, 0, w, h, tm, (cam[0], cam[1], -dz), (-90.0 - pitch, hdg, -roll), FOV)
    pyxel.blt(x, y, o, 0, 0, w, -h, 0)

def draw_cloud_shadows(rect, cam, pitch, hdg, roll, base, sun_az=-40.0, tm=2):
    """雲影を地表に落とす。太陽方位に応じてずらした位置で雲テクスチャを地面に貼る。"""
    a = math.radians(sun_az)
    off = base * 0.55
    x, y, w, h = rect
    o = _off(); o.cls(0)
    o.bltm3d(0, 0, w, h, tm, (cam[0] + math.sin(a) * off, cam[1] + math.cos(a) * off,
                               cam[2]), (-90.0 - pitch, hdg, -roll), FOV)
    pyxel.dither(0.28)                 # 影の薄さは転送時のディザで出す
    pyxel.blt(x, y, o, 0, 0, w, -h, 0)
    pyxel.dither(1.0)

def whiteout(rect, amount, col=12):
    """雲中のホワイトアウト。amount 0..1。"""
    x, y, w, h = rect
    if amount <= 0.02:
        return
    pyxel.dither(min(1.0, amount))
    pyxel.rect(x, y, w, h, col)
    pyxel.dither(1.0)

# ---------------------------------------------------------------- 投影
def project(wx, wy, wz, cam, pitch, hdg, roll, rect):
    """world -> screen。blt3dの見え方と一致（実測平均誤差0.8px）。"""
    x, y, w, h = rect
    f = (h / 2) / math.tan(math.radians(FOV / 2))
    dx, dy, dz = wx - cam[0], wy - cam[1], wz - cam[2]
    a = math.radians(-hdg)
    depth = dx * math.sin(a) + dy * math.cos(a)
    right = dx * math.cos(a) - dy * math.sin(a)
    t = math.radians(pitch)
    y1 = dz * math.cos(t) - depth * math.sin(t)
    z1 = dz * math.sin(t) + depth * math.cos(t)
    if z1 <= 0.5:
        return None
    p = math.radians(-roll)
    xs = right * math.cos(p) + y1 * math.sin(p)
    ys = -right * math.sin(p) + y1 * math.cos(p)
    return (x + w / 2 + f * xs / z1, y + h / 2 - f * ys / z1, z1)

def project_dir(dx, dy, dz, pitch, hdg, roll, rect):
    """無限遠の方向（太陽など）を投影する。"""
    return project(dx * 9000, dy * 9000, dz * 9000, (0, 0, 0), pitch, hdg, roll, rect)

# ---------------------------------------------------------------- 太陽
_STARS = None


def _make_stars(n=460, seed=17):
    """天球上に星をまく。(方向ベクトル, 明るさ) の一覧。"""
    import random
    r = random.Random(seed)
    out = []
    for _ in range(n):
        a = r.uniform(0.0, math.tau)
        # 地平線近くは霞んで見えないので、上寄りに分布させる
        e = math.radians(88.0 * (r.uniform(0.04, 1.0) ** 0.7))
        out.append(((math.cos(e) * math.sin(a), math.cos(e) * math.cos(a),
                     math.sin(e)), 0.35 + r.random() * 0.65))
    return out


def draw_stars(rect, pitch, hdg, roll, amount=1.0, phase=0.0):
    """夜空の星。天球に固定してあるので、機体を傾ければ一緒に回る。

    amount は 0..1（薄暮では薄く、夜で最大）。
    """
    global _STARS
    if amount <= 0.02:
        return
    if _STARS is None:
        _STARS = _make_stars()
    x, y, w, h = rect
    pyxel.clip(x, y, w, h)
    for (dx, dy, dz), b in _STARS:
        p = project_dir(dx, dy, dz, pitch, hdg, roll, rect)
        if p is None:
            continue
        sx, sy, _ = p
        if not (x <= sx < x + w and y <= sy < y + h):
            continue
        # またたき。星ごとに位相をずらす
        tw = 0.70 + 0.30 * math.sin(phase * 2.1 + b * 31.0)
        v = b * amount * tw
        if v < 0.30:
            continue
        pyxel.pset(sx, sy, 12)
        if v > 0.85:                       # とくに明るい星は十字に伸ばす
            pyxel.pset(sx - 1, sy, 12)
            pyxel.pset(sx + 1, sy, 12)
    pyxel.clip()


def draw_sun(rect, pitch, hdg, roll, az, el, disc=6, glow=3, col=14, halo=3):
    a, e = math.radians(az), math.radians(el)
    d = (math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e))
    if el < 0.0:
        return None
    p = project_dir(d[0], d[1], d[2], pitch, hdg, roll, rect)
    if p is None:
        return None
    sx, sy, _ = p
    x, y, w, h = rect
    if not (x - 40 < sx < x + w + 40 and y - 40 < sy < y + h + 40):
        return None
    pyxel.clip(x, y, w, h)
    for i in range(glow, 0, -1):
        pyxel.dither(0.16 * i)
        pyxel.circ(sx, sy, disc + i * 4, halo)
    pyxel.dither(1.0)
    pyxel.circ(sx, sy, disc, col)
    pyxel.circ(sx, sy, disc - 2, 12)
    pyxel.clip()
    return (sx, sy)


# ---------------------------------------------------------------- 一括投影
class Projector:
    """1フレーム分のカメラ姿勢を固定して、点を安く投影する。

    fx.project() は呼ぶたびに三角関数を6回計算するので、リングや他機のように
    数十〜数百点を投影する用途ではこちらを使う。
    """

    __slots__ = ('sa', 'ca', 'ct', 'st', 'cp', 'sp', 'f', 'cx', 'cy',
                 'ox', 'oy', 'oz', 'x0', 'y0', 'w', 'h')

    def __init__(self, cam, pitch, hdg, roll, rect):
        self.x0, self.y0, self.w, self.h = rect
        self.f = (self.h * 0.5) / math.tan(math.radians(FOV * 0.5))
        self.cx = self.x0 + self.w * 0.5
        self.cy = self.y0 + self.h * 0.5
        a = math.radians(-hdg)
        self.sa, self.ca = math.sin(a), math.cos(a)
        t = math.radians(pitch)
        self.ct, self.st = math.cos(t), math.sin(t)
        p = math.radians(-roll)
        self.cp, self.sp = math.cos(p), math.sin(p)
        self.ox, self.oy, self.oz = cam

    def pt(self, wx, wy, wz):
        """画面座標 (x, y, 奥行き) を返す。カメラ後方なら None。"""
        dx = wx - self.ox
        dy = wy - self.oy
        dz = wz - self.oz
        depth = dx * self.sa + dy * self.ca
        z1 = dz * self.st + depth * self.ct
        if z1 <= 0.5:
            return None
        right = dx * self.ca - dy * self.sa
        y1 = dz * self.ct - depth * self.st
        return (self.cx + self.f * (right * self.cp + y1 * self.sp) / z1,
                self.cy - self.f * (-right * self.sp + y1 * self.cp) / z1,
                z1)

    def on_screen(self, p, margin=40):
        return (p is not None and self.x0 - margin < p[0] < self.x0 + self.w + margin
                and self.y0 - margin < p[1] < self.y0 + self.h + margin)
