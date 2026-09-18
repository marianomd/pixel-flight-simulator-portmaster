"""演出をまとめたシーン合成。"""
import math
import pyxel, fx, views, world, objects, effects

PAPI_NOMINAL = 6.2   # 標準進入角[deg]（この世界のスケールに合わせた値）

def _dot(rect, sx, sy, z, col, big=34.0):
    x, y, w, h = rect
    if not (x <= sx < x + w and y <= sy < y + h):
        return
    if z < big:
        pyxel.rect(sx - 1, sy - 1, 2, 2, col)
    else:
        pyxel.pset(sx, sy, col)

def draw_lights(rect, cam, pitch, hdg, roll, glow=False):
    edge, thr, papi = world.runway_lights()
    dist = max(1.0, world.RW_Y0 - cam[1])
    ang = math.degrees(math.atan2(cam[2], dist))
    for i, (lx, ly) in enumerate(papi):
        th = PAPI_NOMINAL + (i - 1.5) * 0.9
        col = 12 if ang > th else 13
        p = fx.project(lx, ly, 0.6, cam, pitch, hdg, roll, rect)
        if p:
            if glow:
                pyxel.dither(0.4); pyxel.circ(p[0], p[1], 2, col); pyxel.dither(1.0)
            _dot(rect, p[0], p[1], p[2], col, big=1e9)
    for lx, ly in edge:
        p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
        if p:
            _dot(rect, p[0], p[1], p[2], 14)
    for lx, ly in thr:
        p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
        if p:
            _dot(rect, p[0], p[1], p[2], 11)

_OBJ_CACHE = {}


def airport_objects(ap=None, plane_yaw=250):
    """空港の地上物。滑走路の向きに合わせて配置する。"""
    ap = ap or world.HOME
    key = (ap.name, plane_yaw)
    if key in _OBJ_CACHE:
        return _OBJ_CACHE[key]
    base = 0.0 if ap.axis == 'NS' else 90.0
    a0 = ap.a0
    objs = [
        dict(model=objects.HANGAR, pos=ap._pt(a0 + 56, 34) + (0,), yaw=base,
             scale=1.6, shadow=6.4),
        dict(model=objects.TOWER, pos=ap._pt(a0 + 88, 32) + (0,), yaw=base,
             scale=2.0, shadow=3.0),
        dict(model=objects.WINDSOCK, pos=ap._pt(a0 + 26, -20) + (0,),
             yaw=base + 205, scale=1.8, windsock=True),
        dict(model=objects.PLANE, pos=ap._pt(a0 + 70, 22) + (0,),
             yaw=base + plane_yaw, scale=1.7, shadow=2.4,
             lights=objects.PLANE_LIGHTS),
    ]
    _OBJ_CACHE[key] = objs
    return objs


def draw_lights(rect, cam, pitch, hdg, roll, ap, end, glow=False):
    dist = max(1.0, ap.dist_to_threshold(end, cam[0], cam[1]))
    ang = math.degrees(math.atan2(cam[2], dist))
    for i, (lx, ly) in enumerate(ap.papi(end)):
        th = PAPI_NOMINAL + (i - 1.5) * 0.9
        col = 12 if ang > th else 13
        p = fx.project(lx, ly, 0.6, cam, pitch, hdg, roll, rect)
        if p:
            if glow:
                pyxel.dither(0.4); pyxel.circ(p[0], p[1], 2, col); pyxel.dither(1.0)
            _dot(rect, p[0], p[1], p[2], col, big=1e9)
    for lx, ly in ap.edge_lights():
        p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
        if p:
            _dot(rect, p[0], p[1], p[2], 14)
    for lx, ly in ap.threshold_lights(end):
        p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
        if p:
            _dot(rect, p[0], p[1], p[2], 11)


APPROACH_D = (300.0, 240.0, 180.0, 120.0, 60.0)   # 輪を置く滑走路端からの距離
APPROACH_R = 7.0                                  # 輪の半径[ユニット]
# 目印は白と赤の交互で描く。単色だと必ずどこかの時刻の空と同化する
# （琥珀は夕焼け、白は雲、緑はHUD）。交互なら背景が何色でも片方が残る。
MARK_A, MARK_B = 12, 13


def draw_approach_guide(pr, ap, end, cam, col=MARK_A):
    """進入経路を輪のトンネルで示す。

    輪は6.2度の降下路の高さに並ぶので、順にくぐれば自然に高度が合う。
    1個だけだと2Dの円が空中に浮いているようにしか見えず、向きも高さも
    読み取れない。並べて奥行きを出すことで「ここを通る道」に見える。
    """
    sgn = ap.sign(end)
    tan_g = math.tan(math.radians(PAPI_NOMINAL))
    seg = 16
    for i, d in enumerate(APPROACH_D):
        cx, cy = ap._pt(end[0] - sgn * d, 0.0)
        cz = d * tan_g
        if math.hypot(cx - cam[0], cy - cam[1]) > 900.0:
            continue
        a = math.radians(end[1])
        ux, uy = math.cos(a), -math.sin(a)        # 滑走路に直交する水平方向
        pts = []
        for k in range(seg):
            t = k / seg * math.tau
            pts.append(pr.pt(cx + ux * APPROACH_R * math.cos(t),
                             cy + uy * APPROACH_R * math.cos(t),
                             cz + APPROACH_R * math.sin(t)))
        for k in range(seg):
            p, q = pts[k], pts[(k + 1) % seg]
            if p and q and (pr.on_screen(p) or pr.on_screen(q)):
                pyxel.line(p[0], p[1], q[0], q[1],
                           MARK_A if (k // 2) % 2 == 0 else MARK_B)
        # 上端に短い棒を立てて、輪の「上」が分かるようにする
        a0 = pr.pt(cx, cy, cz + APPROACH_R)
        a1 = pr.pt(cx, cy, cz + APPROACH_R * 1.5)
        if a0 and a1 and pr.on_screen(a0):
            pyxel.line(a0[0], a0[1], a1[0], a1[1], MARK_A)
        if i == 0:                                 # 入口だけ地面まで柱を下ろす
            g0 = pr.pt(cx, cy, 0.05)
            g1 = pr.pt(cx, cy, cz - APPROACH_R)
            if g0 and g1 and (pr.on_screen(g0) or pr.on_screen(g1)):
                pyxel.line(g0[0], g0[1], g1[0], g1[1], col)


def draw_als(rect, cam, pitch, hdg, roll, ap, end, phase=0, glow=True):
    bars, cross = ap.als(end)
    rabbit = phase % (len(bars) + 6)
    for i, bar in enumerate(bars):
        flash = (len(bars) - 1 - i) == rabbit
        for lx, ly in bar:
            p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
            if not p:
                continue
            if flash:
                pyxel.dither(0.6); pyxel.circ(p[0], p[1], 2, 12); pyxel.dither(1.0)
            elif glow and p[2] < 45:
                pyxel.dither(0.3); pyxel.circ(p[0], p[1], 1, 12); pyxel.dither(1.0)
            _dot(rect, p[0], p[1], p[2], 12, big=1e9 if flash else 26.0)
    for lx, ly in cross:
        p = fx.project(lx, ly, 0.5, cam, pitch, hdg, roll, rect)
        if p:
            _dot(rect, p[0], p[1], p[2], 12)


DASH_STEP = 2.4        # 破線の周期 [ユニット] = 19m
DASH_LEN = 1.3         # 白い部分 = 10m
DASH_W = 0.20          # 半幅 = 1.6m


def draw_centerline(rect, cam, pitch, hdg, roll, ap, far=430.0):
    """滑走路のセンターラインを投影ポリゴンで描く。

    タイルに焼くと 1テクセル=8m のせいで地上視点では巨大な白塊になる。
    ポリゴンならテクセル以下の幅で描けるので、滑走中に細い破線が流れる。

    毎フレーム数百回の投影になるので、三角関数はここで1度だけ計算して
    内側のループは掛け算だけで回す（非力な機器で効く）。
    """
    along = cam[1] if ap.axis == 'NS' else cam[0]
    if abs(along - (ap.a0 + ap.a1) * 0.5) > far:
        return
    lat = abs((cam[0] if ap.axis == 'NS' else cam[1]) - ap.c)
    if lat > 160.0 or cam[2] > 120.0:      # 高いところからは線が潰れるso描かない
        return
    x, y, w, h = rect
    f = (h * 0.5) / math.tan(math.radians(fx.FOV * 0.5))
    cx0, cy0 = x + w * 0.5, y + h * 0.5
    a = math.radians(-hdg)
    sa, ca = math.sin(a), math.cos(a)
    t = math.radians(pitch)
    ct, st = math.cos(t), math.sin(t)
    pr = math.radians(-roll)
    cp, sp = math.cos(pr), math.sin(pr)
    camx, camy, camz = cam
    ns = ap.axis == 'NS'
    c = ap.c
    pts = []

    def proj(px, py):
        dx, dy, dz = px - camx, py - camy, 0.05 - camz
        depth = dx * sa + dy * ca
        z1 = dz * st + depth * ct
        if z1 <= 0.5:
            return None
        right = dx * ca - dy * sa
        y1 = dz * ct - depth * st
        return (cx0 + f * (right * cp + y1 * sp) / z1,
                cy0 - f * (-right * sp + y1 * cp) / z1)

    a0 = ap.a0 + 5.0
    end = ap.a1 - 3.0
    i = 0
    pos = a0
    while pos < end:
        d = abs(pos - along)
        # 遠いものは間引く（画面上ではどうせ潰れる）
        if d < far and not (d > 60.0 and i % 2) and not (d > 130.0 and i % 3):
            if ns:
                q = ((c - DASH_W, pos), (c + DASH_W, pos),
                     (c + DASH_W, pos + DASH_LEN), (c - DASH_W, pos + DASH_LEN))
            else:
                q = ((pos, c - DASH_W), (pos, c + DASH_W),
                     (pos + DASH_LEN, c + DASH_W), (pos + DASH_LEN, c - DASH_W))
            pts = [proj(px, py) for px, py in q]
            if None not in pts:
                p0, p1, p2, p3 = pts
                pyxel.tri(p0[0], p0[1], p1[0], p1[1], p2[0], p2[1], 12)
                pyxel.tri(p0[0], p0[1], p2[0], p2[1], p3[0], p3[1], 12)
        pos += DASH_STEP
        i += 1


def draw_scene(rect, S):
    cam, pitch, hdg, roll = S['cam'], S['pitch'], S['hdg'], S['roll']
    alt, base, top = cam[2], S['base'], S['top']
    ground = S.get('ground', 0)      # タイルマップ番号
    night = S.get('tod') == 'night'
    ap = S.get('ap') or world.nearest_airport(cam[0], cam[1])
    end = S.get('end') or ap.approach_end(cam[0], cam[1])
    detail = S.get('detail', 2)          # 0=LOW 1=MEDIUM 2=HIGH
    fx.apply_tod(S['tod'], S.get('tod_blend'), S.get('tod_t', 0.0), alt=alt)
    fx.draw_sky(rect, pitch, roll)
    if S.get('stars'):
        fx.draw_stars(rect, pitch, hdg, roll, S['stars'], S.get('star_phase', 0.0))
    if S.get('sun'):
        az, el = S['sun']
        fx.draw_sun(rect, pitch, hdg, roll, az, el,
                    disc=S.get('sun_disc', 5), col=S.get('sun_col', 14),
                    halo=S.get('sun_halo', 3))
    if alt <= base:                                  # 雲の下
        if detail >= 1:
            fx.draw_cloud_plane(rect, cam, pitch, hdg, roll, base - alt,
                                S.get('cloud_tm', 1))
        views.draw_world(*rect, cam, pitch, hdg, roll, sky=False, tm=ground)
        # 太陽が低いときは影が長く拡散するので落とさない
        if (detail >= 2 and S.get('shadows', True)
                and S.get('sun') and S['sun'][1] > 15):
            fx.draw_cloud_shadows(rect, cam, pitch, hdg, roll, base - alt,
                                  S.get('sun', (-40, 20))[0])
        pyxel.clip(*rect)
        draw_centerline(rect, cam, pitch, hdg, roll, ap)
        pyxel.clip()
        fx.draw_haze(rect, pitch, roll, alt, S.get('haze', 1.0),
                     S.get('haze_scale', 1.0))
        if S.get('objects'):
            objs = list(airport_objects(ap)) + (S.get('traffic') or [])
            wd = S.get('wind_dir')
            if wd is not None:
                for o in objs:
                    if o.get('windsock'):
                        o['yaw'] = wd + 90.0      # 風下を向く
            objects.draw_all(objs, cam, pitch, hdg, roll, rect, night)
        efx = S.get('effects')
        if efx is not None:
            pyxel.clip(*rect)
            pr = fx.Projector(cam, pitch, hdg, roll, rect)
            if S.get('land_light'):
                effects.landing_light(pr, S['land_light'])
            efx[0].draw(pr, night)
            efx[1].draw(pr, S.get('bird_phase', 0.0))
            pyxel.clip()
        # 霧は地形と建物の後、灯火の前。灯火だけ霧を突き抜けて見える。
        fx.fog(rect, S.get('fog', 0.0))
        if S.get('als'):
            draw_als(rect, cam, pitch, hdg, roll, ap, end, S.get('als_phase', 0))
        if S.get('lights'):
            draw_lights(rect, cam, pitch, hdg, roll, ap, end, S.get('glow', False))
        cs = S.get('course')
        jb = S.get('job')
        ag = S.get('approach_guide')
        if (cs is not None and cs.active) or jb is not None or ag is not None:
            pyxel.clip(*rect)
            pr = fx.Projector(cam, pitch, hdg, roll, rect)
            if cs is not None and cs.active:
                cs.draw(pr, cam)
            if jb is not None:
                jb.draw(pr, cam, S.get('wind'), S.get('bird_phase', 0.0))
            if ag is not None:
                draw_approach_guide(pr, ag[0], ag[1], cam)
            pyxel.clip()
    elif alt >= top:                                 # 雲の上
        views.draw_world(*rect, cam, pitch, hdg, roll, sky=False, tm=ground)
        fx.draw_haze(rect, pitch, roll, alt, 1.6)
        if detail >= 1:
            fx.draw_cloud_plane(rect, cam, pitch, hdg, roll, base - alt,
                                S.get('cloud_tm', 1))
    else:                                            # 雲の中
        views.draw_world(*rect, cam, pitch, hdg, roll, sky=False, tm=ground)
        k = 1.0 - abs((alt - base) / max(1.0, top - base) - 0.5) * 2.0
        fx.draw_cloud_plane(rect, cam, pitch, hdg, roll, (top - alt) * 0.35,
                            S.get('cloud_tm', 1))
        # 雨雲の中は白ではなく灰色に沈む
        fx.whiteout(rect, 0.30 + 0.55 * k, 15 if S.get('cloud_tm', 1) == 4 else 12)
    # 自機（外部視点）はカメラのすぐ前にいる。霧・着陸灯・灯火より手前に、
    # そして雲の上でも中でも必ず描く（雲の分岐の中に置くと消えてしまう）
    me = S.get('self_plane')
    if me:
        pyxel.clip(*rect)
        objects.draw_all([me], cam, pitch, hdg, roll, rect, night)
        pyxel.clip()

def prop_disc(cx, cy, r, phase):
    """コクピット視点のプロペラ円盤。縁のぼやけと通過するブレードだけ見せる。"""
    for k in range(2):                      # 通過中のブレード
        a = math.radians(phase + k * 180)
        pyxel.dither(0.3)
        pyxel.line(cx + math.cos(a) * r * 0.25, cy + math.sin(a) * r * 0.25,
                   cx + math.cos(a) * r, cy + math.sin(a) * r, 15)
        pyxel.dither(1.0)
