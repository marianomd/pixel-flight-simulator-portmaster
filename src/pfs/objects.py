"""投影を使った低ポリ物体。管制塔・ハンガー・吹き流し・他機。
ローカル座標は x=右 / y=前(+yがマップ+y) / z=上。単位はマップと同じ。"""
import math
import pyxel, fx

# ------------------------------------------------------------------ 形状ヘルパ
def box(w, d, h, z0, top, side, side2=None):
    s2 = side2 if side2 is not None else side
    v = [(-w/2, -d/2, z0), (w/2, -d/2, z0), (w/2, d/2, z0), (-w/2, d/2, z0),
         (-w/2, -d/2, z0+h), (w/2, -d/2, z0+h), (w/2, d/2, z0+h), (-w/2, d/2, z0+h)]
    f = [([4, 5, 6, 7], top), ([0, 1, 5, 4], side), ([1, 2, 6, 5], s2),
         ([2, 3, 7, 6], side), ([3, 0, 4, 7], s2)]
    return v, f

def merge(*parts):
    verts, faces = [], []
    for v, f in parts:
        o = len(verts)
        verts += v
        faces += [([i + o for i in idx], c) for idx, c in f]
    return verts, faces

def quad(p0, p1, p2, p3, col):
    return [p0, p1, p2, p3], [([0, 1, 2, 3], col)]

# ------------------------------------------------------------------ モデル定義
TOWER = merge(box(2.6, 2.6, 5.0, 0.0, 15, 15, 9),
              box(3.6, 3.6, 1.8, 5.0, 15, 12, 12),
              box(0.3, 0.3, 2.2, 6.8, 13, 13))
HANGAR = merge(box(9.0, 6.0, 2.6, 0.0, 5, 15, 15),
               box(9.4, 6.4, 0.9, 2.6, 15, 5, 5))
WINDSOCK = merge(box(0.3, 0.3, 3.0, 0.0, 15, 15),
                 quad((0.2, 0.0, 3.0), (2.6, 0.9, 2.5), (2.6, 0.9, 1.9), (0.2, 0.0, 2.4), 14),
                 quad((2.6, 0.9, 2.5), (4.4, 1.6, 2.4), (4.4, 1.6, 2.0), (2.6, 0.9, 1.9), 12))
PLANE = merge(
    quad((-0.30, -1.5, 0.0), (0.30, -1.5, 0.0), (0.30, 1.5, 0.0), (-0.30, 1.5, 0.0), 12),
    quad((-2.4, 0.15, 0.10), (2.4, 0.15, 0.10), (2.4, -0.55, 0.10), (-2.4, -0.55, 0.10), 12),
    quad((-1.0, -1.35, 0.14), (1.0, -1.35, 0.14), (1.0, -1.75, 0.14), (-1.0, -1.75, 0.14), 13),
    quad((0.0, -1.30, 0.16), (0.0, -1.78, 0.16), (0.0, -1.78, 0.90), (0.0, -1.45, 0.90), 13),
    quad((-0.30, 1.5, 0.0), (0.30, 1.5, 0.0), (0.22, 1.72, 0.06), (-0.22, 1.72, 0.06), 9))

# 舷灯: (ローカル座標, 色)
PLANE_LIGHTS = [((-2.4, 0.0, 0.12), 13), ((2.4, 0.0, 0.12), 11), ((0.0, -1.78, 0.9), 12)]

# ------------------------------------------------------------------ 描画
def _body(bank, nose):
    """機体の姿勢で局所座標を回す関数を返す。bank/nose が0なら何もしない。"""
    if not bank and not nose:
        return None
    cb, sb = math.cos(math.radians(bank)), math.sin(math.radians(bank))
    cn, sn = math.cos(math.radians(nose)), math.sin(math.radians(nose))

    def f(lx, ly, lz):
        x = lx * cb + lz * sb                 # バンク（機軸まわり）
        z = -lx * sb + lz * cb
        y = ly * cn - z * sn                  # ピッチ（翼の軸まわり）
        return x, y, ly * sn + z * cn
    return f


def draw_model(model, wx, wy, wz, yaw, scale, cam, pitch, hdg, roll, rect,
               shadow=0.0, dither_far=True, bank=0.0, nose=0.0):
    verts, faces = model
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)
    att = _body(bank, nose)
    pts = []
    for lx, ly, lz in verts:
        if att:
            lx, ly, lz = att(lx, ly, lz)
        rx = lx * ca + ly * sa
        ry = -lx * sa + ly * ca
        p = fx.project(wx + rx * scale, wy + ry * scale, wz + lz * scale,
                       cam, pitch, hdg, roll, rect)
        if p is None:
            return None
        pts.append(p)
    x, y, w, h = rect
    if all(p[0] < x - 30 or p[0] > x + w + 30 or p[1] < y - 30 or p[1] > y + h + 30
           for p in pts):
        return None
    if shadow > 0:
        sq = []
        for dx, dy in ((-shadow, -shadow), (shadow, -shadow), (shadow, shadow), (-shadow, shadow)):
            p = fx.project(wx + dx * scale, wy + dy * scale, 0.02, cam, pitch, hdg, roll, rect)
            if p is None:
                sq = None; break
            sq.append(p)
        if sq:
            pyxel.dither(0.5)
            pyxel.tri(sq[0][0], sq[0][1], sq[1][0], sq[1][1], sq[2][0], sq[2][1], 4)
            pyxel.tri(sq[0][0], sq[0][1], sq[2][0], sq[2][1], sq[3][0], sq[3][1], 4)
            pyxel.dither(1.0)
    order = sorted(range(len(faces)),
                   key=lambda i: -sum(pts[k][2] for k in faces[i][0]) / len(faces[i][0]))
    for i in order:
        idx, col = faces[i]
        p = [pts[k] for k in idx]
        pyxel.tri(p[0][0], p[0][1], p[1][0], p[1][1], p[2][0], p[2][1], col)
        if len(p) == 4:
            pyxel.tri(p[0][0], p[0][1], p[2][0], p[2][1], p[3][0], p[3][1], col)
    return sum(p[2] for p in pts) / len(pts)

def draw_lights(lights, wx, wy, wz, yaw, scale, cam, pitch, hdg, roll, rect,
                blink=True, bank=0.0, nose=0.0):
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)
    att = _body(bank, nose)
    x, y, w, h = rect
    for (lx, ly, lz), col in lights:
        if att:
            lx, ly, lz = att(lx, ly, lz)
        rx = lx * ca + ly * sa
        ry = -lx * sa + ly * ca
        p = fx.project(wx + rx * scale, wy + ry * scale, wz + lz * scale,
                       cam, pitch, hdg, roll, rect)
        if p and x <= p[0] < x + w and y <= p[1] < y + h:
            pyxel.pset(p[0], p[1], col)
            if blink and p[2] < 60:
                pyxel.dither(0.4); pyxel.circ(p[0], p[1], 1, col); pyxel.dither(1.0)

FAR = 520.0        # これより遠い物体は数ピクセルなので描かない


def draw_all(objs, cam, pitch, hdg, roll, rect, night=False):
    """objs: list of dict(model=, pos=(x,y,z), yaw=, scale=, shadow=, lights=)"""
    drawn = []
    for o in objs:
        px, py, pz = o['pos']
        d = math.hypot(px - cam[0], py - cam[1])
        if d > FAR:
            continue
        drawn.append((d, o))
    for d, o in sorted(drawn, key=lambda t: -t[0]):
        px, py, pz = o['pos']
        bank, nose = o.get('bank', 0.0), o.get('nose', 0.0)
        z = draw_model(o['model'], px, py, pz, o.get('yaw', 0), o.get('scale', 1.0),
                       cam, pitch, hdg, roll, rect, shadow=o.get('shadow', 0.0),
                       bank=bank, nose=nose)
        if z is not None and o.get('lights') and night:
            draw_lights(o['lights'], px, py, pz, o.get('yaw', 0), o.get('scale', 1.0),
                        cam, pitch, hdg, roll, rect, bank=bank, nose=nose)
