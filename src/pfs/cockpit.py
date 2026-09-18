"""コクピット視点の枠と計器盤。"""
import math
import pyxel, views, scene, world

W, H = 256, 192
PANEL_H = 82                       # 計器盤の高さ（画面比率が変わっても一定）
PANEL_Y = H - PANEL_H
GLASS = (0, 0, W, PANEL_Y - 2)


def set_size(w, h):
    global W, H, PANEL_Y, GLASS
    W, H = w, h
    PANEL_Y = h - PANEL_H
    GLASS = (0, 0, w, PANEL_Y - 2)

def chrome():
    pyxel.tri(0, 0, 26, 0, 0, GLASS[3], 0)
    pyxel.tri(0, 0, 14, 0, 0, 40, 15)
    pyxel.tri(W, 0, W - 26, 0, W, GLASS[3], 0)
    pyxel.tri(W, 0, W - 14, 0, W, 40, 15)
    pyxel.rect(0, 0, W, 7, 15)
    pyxel.rect(0, 7, W, 2, 0)
    pyxel.rect(0, GLASS[3] - 4, W, 4, 0)
    pyxel.rect(0, PANEL_Y - 6, W, 6, 15)
    pyxel.line(0, PANEL_Y - 6, W, PANEL_Y - 6, 5)

def moving_map(x, y, size, cam, tm=0, step=4, cell=2, label='GPS'):
    """タイルマップを直接読んで描く模式地図。1セル=step タイル。"""
    n = size // cell
    half = n * step // 2
    t0x = int(cam[0]) // world.TILE - half
    t0y = int(cam[1]) // world.TILE - half
    pyxel.rect(x - 1, y - 1, size + 2, size + 2, 0)
    tmo = pyxel.tilemaps[tm] if isinstance(tm, int) else tm
    for j in range(n):
        ty = t0y + j * step
        if not (0 <= ty < world.TW):
            continue
        sy = y + size - cell - j * cell          # 進行方向(+y)を上に
        for i in range(n):
            tx = t0x + i * step
            if not (0 <= tx < world.TW):
                continue
            col = world.tile_color(tmo.pget(tx, ty))
            if col:
                pyxel.rect(x + i * cell, sy, cell, cell, col)
    mx = x + size // 2
    my = y + size // 2
    pyxel.tri(mx, my - 4, mx - 3, my + 3, mx + 3, my + 3, 13)
    pyxel.rectb(x - 1, y - 1, size + 2, size + 2, views.LABEL)
    pyxel.text(x + 1, y + size - 7, label[:14], 11)
    pyxel.text(x + size - 16, y + 1, '%dKM' % round(n * step * world.TILE * 8 / 1000), 11)


def lamp(x, y, label, on, col=13):
    """点灯/消灯が分かる警報灯。"""
    w = len(label) * 4 + 3
    pyxel.rect(x, y - 1, w, 8, col if on else 0)
    pyxel.rectb(x, y - 1, w, 8, col if on else 5)
    pyxel.text(x + 2, y, label, 0 if on else 5)


def wind_gauge(x, y, wind, hdg, lbl):
    """風向風速計。矢印は機首基準で、風の吹いてくる向きを指す。

    地図の下の空きに収める。横風成分は着陸のたびに効くので数値でも出す。
    """
    cx, cy = x + 9, y + 9
    pyxel.circb(cx, cy, 8, lbl)
    pyxel.line(cx, cy - 8, cx, cy - 6, lbl)         # 円の内側に機首の目印
    if not wind or wind[1] < 0.5:
        pyxel.text(x + 21, y + 5, 'CALM', 11)
        return
    wkt, cross = wind[1], wind[3]
    a = math.radians(wind[0] - hdg + 180.0)         # 機首基準で矢印を回す
    sx, sy = math.sin(a), math.cos(a)
    pyxel.line(cx - sx * 5, cy + sy * 5, cx + sx * 4, cy - sy * 4, 12)
    pyxel.tri(cx + sx * 6, cy - sy * 6,
              cx + math.sin(a + 2.7) * 3, cy - math.cos(a + 2.7) * 3,
              cx + math.sin(a - 2.7) * 3, cy - math.cos(a - 2.7) * 3, 12)
    pyxel.text(x + 21, y + 1, 'W%3dKT' % int(wkt), 14 if wkt >= 20 else 11)
    pyxel.text(x + 21, y + 9, 'X%+4d' % int(cross),
               14 if abs(cross) > 10 else 11)


def panel(st):
    roll, cam = st['roll'], st['cam']
    night = st.get('tod') in ('night', 'dusk')
    views.LABEL = 14 if night else 5          # 夜間は計器照明を琥珀に
    lbl = views.LABEL
    # 滑走路の路面も15番なので、そのまま塗ると風防の下端と同化して見える。
    # 15と0の市松にして質感を変え、境目がはっきり分かるようにする。
    pyxel.rect(0, PANEL_Y, W, H - PANEL_Y, 0)
    pyxel.dither(0.5)
    pyxel.rect(0, PANEL_Y, W, H - PANEL_Y, 15)
    pyxel.dither(1.0)
    pyxel.line(0, PANEL_Y, W, PANEL_Y, lbl)
    for x in range(4, W, 16):
        pyxel.pset(x, PANEL_Y + 2, lbl)
    nv = st.get('nav')
    r = 17
    views.asi(24, PANEL_Y + 23, r, st['kt'], st.get('vs0'))
    views.attitude_indicator(62, PANEL_Y + 23, r, roll, st['pitch'])
    views.altimeter(100, PANEL_Y + 23, r, st['ft'])
    views.turn_coord(24, PANEL_Y + 61, r, roll * 0.8,
                     int(st.get('rudder', 0.0) * 5.0))
    views.heading_ind(62, PANEL_Y + 61, r, st.get('hdg_disp', st['hdg']))
    views.vsi(100, PANEL_Y + 61, r, st['fpm'])
    # 行き先は航法計器である地図の中に置く。右の欄は幅が足りない
    moving_map(126, PANEL_Y + 4, 58, cam, st.get('ground', 0),
               label=('%s' % world.apt_short(nv[0])) if nv else 'GPS')
    wind_gauge(126, PANEL_Y + 63, st.get('wind'),
               st.get('hdg_disp', 0.0), lbl)
    if nv:
        pyxel.rect(127, PANEL_Y + 5, 42, 7, 0)
        pyxel.text(128, PANEL_Y + 6, '%.1fKM %03d' % (nv[1], nv[2]), 11)
    bx = 192
    pyxel.rect(bx - 4, PANEL_Y + 2, W - bx + 4, PANEL_H - 4, 0)
    pyxel.text(bx, PANEL_Y + 6, 'RPM  %d' % st['rpm'], 11)
    pyxel.text(bx, PANEL_Y + 14, 'FUEL  %d' % st['fuel'],
               13 if st['fuel'] < 20 else 11)
    pyxel.text(bx, PANEL_Y + 22, 'FLAP  %d' % st['flap'], 14)
    lamp(bx, PANEL_Y + 30, 'BRK', st.get('brake'))
    lamp(bx + 24, PANEL_Y + 30, 'STL', st.get('stall') and pyxel.frame_count % 20 < 13)
    if st.get('eng_bad'):
        lamp(bx + 48, PANEL_Y + 30, 'ENG', True)
    pl = st.get('pilot')
    if pl is not None and pl.on:
        pyxel.text(bx, PANEL_Y + 38, 'AP %s' % pl.phase[:6], 14)
    else:
        pyxel.text(bx, PANEL_Y + 38, 'LAND  %s' % ('ON' if st.get('lights') else 'OFF'),
                   14 if st.get('lights') else 5)
    for i, (lb, v, col) in enumerate((('THR', st['thr'], 14), ('MIX', 0.9, 13),
                                      ('PRP', 0.8, 12))):
        x = bx + i * 15
        pyxel.rect(x, PANEL_Y + 48, 8, 24, 15 if night else 5)
        pyxel.rect(x, PANEL_Y + 48 + int(24 * (1 - v)), 8, 3, col)
        pyxel.text(x - 1, PANEL_Y + 74, lb, lbl)
    # トリム指示（中立が中央）
    tx = bx + 47
    pyxel.rect(tx, PANEL_Y + 48, 8, 24, 15 if night else 5)
    # 機首上げトリムでバー下降、機首下げトリムで上昇（操縦桿の押し引きと同じ向き）
    tv = min(1.0, max(0.0, (st.get('trim', 0.0) + 8.0) / 20.0))
    pyxel.rect(tx, PANEL_Y + 48 + int(21 * tv), 8, 3, 11)
    ny = PANEL_Y + 48 + int(21 * (8.0 / 20.0))
    pyxel.line(tx - 1, ny + 1, tx + 8, ny + 1, lbl)
    # ラベルはバーの上へ移し、下には数値を出す（他のレバーと同じ位置）
    pyxel.text(tx - 1, PANEL_Y + 41, 'TRM', lbl)
    pyxel.text(W - 17, PANEL_Y + 74, '%+4.1f' % st.get('trim', 0.0), 11)

def view(st):
    scene.draw_scene(GLASS, st)
    rain = st.get('rain')
    if rain:
        rain[0].draw(GLASS, rain[1])
        wp = st.get('wiper')
        if wp:
            wp[0].draw(GLASS, wp[1])
    scene.prop_disc(W // 2, GLASS[3] + 46, 92, st.get('prop', 0))
    chrome()
    look = st.get('look', 0.0)
    if abs(look) > 4.0:
        # どちらを向いているか。仕事の表示と重ならないよう右上に置く
        t = 'LOOK %d%s' % (round(abs(look)), 'R' if look > 0 else 'L')
        pyxel.rect(W - len(t) * 4 - 6, 11, len(t) * 4 + 3, 8, 0)
        pyxel.text(W - len(t) * 4 - 4, 12, t, 14)
    job = st.get('job')
    if job is not None:
        # 仕事の進み具合。全画面HUDと同じ内容を風防の上に出す
        s = job.status_line()[:30]
        pyxel.rect(3, 11, len(s) * 4 + 3, 8, 0)
        pyxel.text(5, 12, s, 13 if job.urgent() else 14)
    panel(st)
    msg = st.get('msg')
    if msg:
        mw = len(msg) * 4
        pyxel.rect(W // 2 - mw // 2 - 2, GLASS[3] - 13, mw + 3, 8, 0)
        pyxel.text(W // 2 - mw // 2, GLASS[3] - 12, msg, 14)
