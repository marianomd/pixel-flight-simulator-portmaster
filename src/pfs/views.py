"""Pyxel 実機描画によるフライトシム画面。HUDビューとコクピットビュー。"""
import math
import pyxel
import world

W, H = 256, 192
FOV = 60.0
BASE_ASPECT = 192.0 / 256.0        # この比率のときFOVは60度


def set_size(w, h):
    """画面サイズを決める。縦横比が変わっても横方向の視野角は保つ。"""
    global W, H, FOV
    W, H = w, h
    k = (h / w) / BASE_ASPECT
    FOV = math.degrees(2.0 * math.atan(math.tan(math.radians(30.0)) * k))
    import fx
    fx.FOV = FOV
LABEL = 5          # 計器の目盛り・ラベル色（夜間は琥珀に差し替わる）

# ---------- 出力 ----------
def grab(scale=3):
    """開発用: 画面をPIL Imageで取り出す（numpy/Pillowが要る）。"""
    import numpy as np
    from PIL import Image
    b = np.frombuffer(pyxel.screen.data_ptr(), np.uint8).reshape(H, W)
    rgb = np.zeros((H, W, 3), np.uint8)
    for i in range(16):
        c = int(pyxel.colors[i])          # 実行時のパレットを見る
        rgb[b == i] = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    return Image.fromarray(rgb).resize((W * scale, H * scale), Image.NEAREST)

# ---------- 空 ----------
def sky_band(hx, hy, ux, uy, t, col):
    """水平線から距離tより上（機体上方）を全部塗る回転矩形。三角形2枚。"""
    ax, ay = -uy, ux                      # 水平線に平行な方向
    L = 400.0; D = 400.0
    x0, y0 = hx + ux * t, hy + uy * t
    pyxel.tri(x0 - ax * L, y0 - ay * L, x0 + ax * L, y0 + ay * L,
              x0 + ax * L + ux * D, y0 + ay * L + uy * D, col)
    pyxel.tri(x0 - ax * L, y0 - ay * L, x0 + ax * L + ux * D, y0 + ay * L + uy * D,
              x0 - ax * L + ux * D, y0 - ay * L + uy * D, col)

def draw_sky(x, y, w, h, pitch=0.0, roll=0.0):
    """空のグラデーションを水平線と平行に描く。ロールで地表と一緒に傾く。"""
    f = (h / 2) / math.tan(math.radians(FOV / 2))
    # 地表は blt3d の反転を経て -roll だけ回って描かれるので、空もそれに合わせる
    a = math.radians(-roll)
    ux, uy = math.sin(a), -math.cos(a)    # 機体上方向（スクリーン座標、y下向き）
    cx, cy = x + w / 2, y + h / 2
    d = f * math.tan(math.radians(pitch))
    hx, hy = cx - ux * d, cy - uy * d     # 水平線上の一点
    pyxel.clip(x, y, w, h)
    pyxel.rect(x, y, w, h, 3)             # 水平線際のヘイズ（地図外もこの色になる）
    # 帯は画面比率ではなく仰角で決める（画角や風防の高さが変わっても見え方が一定）
    t1 = f * math.tan(math.radians(6.0))
    t2 = f * math.tan(math.radians(18.0))
    sky_band(hx, hy, ux, uy, t1, 2)
    pyxel.dither(0.5); sky_band(hx, hy, ux, uy, t1 * 0.55, 2); pyxel.dither(1.0)
    sky_band(hx, hy, ux, uy, t2, 1)
    pyxel.dither(0.5); sky_band(hx, hy, ux, uy, t2 * 0.78, 1); pyxel.dither(1.0)
    pyxel.clip()

# blt3d の出力は上下反転で返る。またrot_xは「真下=0」基準（水平飛行=-90）。
# オフスクリーンに描いて負のheightで反転ブリットし、通常のカメラ姿勢に直す。
_OFF = None

def draw_world(x, y, w, h, pos, pitch=0.0, hdg=0.0, roll=0.0, sky=True, tm=0):
    """pitch: 機首上げ正[deg] / hdg: 方位[deg] / roll: 右バンク正[deg]"""
    global _OFF
    if _OFF is None:
        _OFF = pyxel.Image(256, 256)
    if sky:
        draw_sky(x, y, w, h, pitch, roll)
    _OFF.cls(0)
    _OFF.bltm3d(0, 0, w, h, tm, pos, (-90.0 - pitch, hdg, -roll), FOV)
    pyxel.blt(x, y, _OFF, 0, 0, w, -h, 0)

def draw_clouds(x, y, w, h, pos, pitch=0.0, hdg=0.0, roll=0.0, dz=40.0, img=1):
    """頭上の雲層。地表と同じ反転で、zに「雲底までの高度差の負値」を渡す。"""
    global _OFF
    if _OFF is None:
        _OFF = pyxel.Image(256, 256)
    _OFF.cls(0)
    _OFF.blt3d(0, 0, w, h, img, (pos[0], pos[1], -abs(dz)),
               (-90.0 - pitch, hdg, -roll), FOV)
    pyxel.blt(x, y, _OFF, 0, 0, w, -h, 0)

def horizon_y(y, h, pitch):
    """水平線のスクリーンY。f=(h/2)/tan(fov/2)。"""
    f = (h / 2) / math.tan(math.radians(FOV / 2))
    return y + h / 2 + f * math.tan(math.radians(pitch))

# ---------- 計器 ----------
def gauge_face(cx, cy, r, label):
    pyxel.circ(cx, cy, r + 1, 15)
    pyxel.circ(cx, cy, r, 0)
    pyxel.circb(cx, cy, r, 15)
    pyxel.text(cx - len(label) * 2, cy + r - 11, label, LABEL)

def needle(cx, cy, r, deg, col, tail=0.0):
    a = math.radians(deg - 90)
    pyxel.line(cx - math.cos(a) * r * tail, cy - math.sin(a) * r * tail,
               cx + math.cos(a) * r, cy + math.sin(a) * r, col)

def ticks(cx, cy, r, n, col=12, start=0, span=360):
    for i in range(n):
        a = math.radians(start + span * i / n - 90)
        pyxel.line(cx + math.cos(a) * (r - 3), cy + math.sin(a) * (r - 3),
                   cx + math.cos(a) * (r - 1), cy + math.sin(a) * (r - 1), col)

def attitude_indicator(cx, cy, r, roll_deg, pitch_deg):
    """姿勢指示器。roll_degは右バンク正。人工水平線は外の景色と同じ傾きになる。"""
    pyxel.circ(cx, cy, r + 1, 15)
    rd = -roll_deg
    phi = math.radians(rd)
    po = pitch_deg * 0.55
    s, c = math.sin(phi), math.cos(phi)
    # 1行ずつ塗ると描画呼び出しが多くなるので2行まとめて矩形で塗る
    for dy in range(-r, r + 1, 2):
        half = int(math.sqrt(max(0, r * r - dy * dy)))
        if half == 0:
            continue
        hh = 2 if dy + 1 <= r else 1
        yy = cy + dy
        if abs(s) < 1e-4:
            pyxel.rect(cx - half, yy, half * 2 + 1, hh, 9 if dy > po else 2)
            continue
        xb = (dy * c - po) / s
        xb = max(-half, min(half, xb))
        left, right = (9, 2) if s > 0 else (2, 9)
        w1 = int(xb + half)
        if w1 > 0:
            pyxel.rect(cx - half, yy, w1, hh, left)
        w2 = int(half - xb)
        if w2 > 0:
            pyxel.rect(cx + xb, yy, w2 + 1, hh, right)
    # 水平線。中心から po だけ離れた位置にあるので、円と交わる弦の長さで描く
    # （r のまま引くとピッチが付いたときに枠からはみ出す）
    a = math.radians(rd)
    half = math.sqrt(max(0.0, r * r - po * po))
    hx, hy = math.cos(a) * half, -math.sin(a) * half
    ox, oy = math.sin(a) * po, math.cos(a) * po
    pyxel.line(cx - hx + ox, cy - hy + oy, cx + hx + ox, cy + hy + oy, 12)
    # 固定の機体シンボル
    pyxel.line(cx - 7, cy, cx - 3, cy, 14)
    pyxel.line(cx + 3, cy, cx + 7, cy, 14)
    pyxel.pset(cx, cy, 14)
    # ロールポインタ
    for m in (-60, -30, -20, 0, 20, 30, 60):
        aa = math.radians(m - 90)
        ln, cl = (3, 12) if m % 30 == 0 else (2, LABEL)
        pyxel.line(cx + math.cos(aa) * (r - 1), cy + math.sin(aa) * (r - 1),
                   cx + math.cos(aa) * (r - 1 - ln), cy + math.sin(aa) * (r - 1 - ln), cl)
    ar = math.radians(roll_deg - 90)
    pyxel.tri(cx + math.cos(ar) * (r - 6), cy + math.sin(ar) * (r - 6),
              cx + math.cos(ar + 0.20) * (r - 11), cy + math.sin(ar + 0.20) * (r - 11),
              cx + math.cos(ar - 0.20) * (r - 11), cy + math.sin(ar - 0.20) * (r - 11), 14)
    pyxel.circb(cx, cy, r, 15)

def asi(cx, cy, r, kt, vs0=None):
    """vs0 に現在の失速速度[kt]を渡すと、赤帯がフラップに応じて動く。"""
    gauge_face(cx, cy, r, 'KT')
    ticks(cx, cy, r, 12)
    lo = vs0 if vs0 else 48.0
    for v in range(25, 156, 5):
        col = 13 if v < lo else (11 if v < 120 else 14)
        a = math.radians(30 + v * 1.6 - 90)
        pyxel.line(cx + math.cos(a) * (r - 4), cy + math.sin(a) * (r - 4),
                   cx + math.cos(a) * (r - 2), cy + math.sin(a) * (r - 2), col)
    needle(cx, cy, r - 4, 30 + kt * 1.6, 12, 0.25)
    pyxel.text(cx - 7, cy - 9, str(kt), 11)

def altimeter(cx, cy, r, ft):
    gauge_face(cx, cy, r, 'ALT')
    ticks(cx, cy, r, 10)
    needle(cx, cy, r - 9, (ft % 10000) / 10000 * 360, 12, 0.25)   # 千ft
    needle(cx, cy, r - 4, (ft % 1000) / 1000 * 360, 12, 0.25)     # 百ft
    pyxel.text(cx - 9, cy - 9, str(ft), 11)

def vsi(cx, cy, r, fpm):
    gauge_face(cx, cy, r, 'VS')
    ticks(cx, cy, r, 8)
    needle(cx, cy, r - 4, 90 + max(-100, min(100, fpm / 20.0)) * 1.5, 12, 0.25)
    pyxel.text(cx - 9, cy - 9, ('+' if fpm >= 0 else '') + str(fpm), 11)

def heading_ind(cx, cy, r, hdg):
    gauge_face(cx, cy, r, 'HDG')
    for i, s in enumerate(('N', 'E', 'S', 'W')):
        a = math.radians(i * 90 - hdg - 90)
        pyxel.text(cx + math.cos(a) * (r - 6) - 1, cy + math.sin(a) * (r - 6) - 2, s, 12)
    for i in range(12):
        a = math.radians(i * 30 - hdg - 90)
        pyxel.line(cx + math.cos(a) * (r - 3), cy + math.sin(a) * (r - 3),
                   cx + math.cos(a) * (r - 1), cy + math.sin(a) * (r - 1), LABEL)
    pyxel.tri(cx, cy - r + 1, cx - 3, cy - r + 6, cx + 3, cy - r + 6, 14)
    pyxel.line(cx, cy - 5, cx, cy + 5, 14)
    pyxel.line(cx - 4, cy + 2, cx + 4, cy + 2, 14)
    # 目盛りだけでは読み取りにくいので、数値も出す
    pyxel.rect(cx - 7, cy + 6, 14, 7, 0)
    pyxel.rectb(cx - 7, cy + 6, 14, 7, LABEL)
    pyxel.text(cx - 5, cy + 7, '%03d' % (round(hdg) % 360), 12)

def turn_coord(cx, cy, r, rate, slip):
    """旋回計。rate は右旋回が正。実機と同じく機体シンボルは旋回方向へ傾く。"""
    gauge_face(cx, cy, r, 'TRN')
    a = math.radians(-rate * 2.2)      # 右旋回で右翼が下がる
    pyxel.line(cx - math.cos(a) * (r - 5), cy + math.sin(a) * (r - 5),
               cx + math.cos(a) * (r - 5), cy - math.sin(a) * (r - 5), 12)
    pyxel.circ(cx, cy, 2, 12)
    pyxel.line(cx - 10, cy + r - 7, cx + 10, cy + r - 7, LABEL)
    pyxel.circ(cx + slip, cy + r - 9, 2, 0)
    pyxel.circb(cx + slip, cy + r - 9, 2, 12)
    for dx in (-4, 4):
        pyxel.line(cx + dx, cy + r - 11, cx + dx, cy + r - 6, LABEL)
