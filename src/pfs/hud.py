"""全画面ビューのHUD。速度・高度テープ、方位テープ、ピッチラダー、飛行経路マーカー。"""
import math
import pyxel
import fx
import world

G = 11      # HUD緑
W_ = 12     # 白
A_ = 14     # 琥珀
R_ = 13     # 赤


def _tape_v(x, y, w, h, value, step, label, unit='', mark=None):
    pyxel.rect(x, y, w, h, 0)
    pyxel.rectb(x, y, w, h, G)
    cy = y + h // 2
    base = int(value / step) * step
    for k in range(-3, 4):
        v = base + k * step
        sy = cy - (v - value) / step * 9.0
        if y + 3 < sy < y + h - 3:
            pyxel.line(x + w - 5, sy, x + w - 1, sy, G)
            if v % (step * 2) == 0:
                pyxel.text(x + 2, sy - 2, '%4d' % v, G)
    if mark is not None:
        my = cy - (mark - value) / step * 9.0
        if y + 1 < my < y + h - 1:
            pyxel.line(x + 1, my, x + w - 1, my, R_)
    pyxel.tri(x + w, cy - 4, x + w, cy + 4, x + w - 5, cy, A_)
    pyxel.text(x, y - 7, label, G)
    if unit:
        pyxel.text(x, y + h + 1, unit, G)


def _heading_tape(cx, y, value):
    """方位テープ。右へ行くほど方位が増える（右旋回でテープは左へ流れる）。"""
    pyxel.rect(cx - 46, y, 92, 11, 0)
    pyxel.rectb(cx - 46, y, 92, 11, G)
    base = int(value / 10) * 10
    for k in range(-3, 4):
        v = base + k * 10
        sx = cx + (v - value) * 1.8
        if cx - 44 < sx < cx + 44:
            pyxel.line(sx, y + 1, sx, y + 4, G)
            if v % 30 == 0:
                pyxel.text(sx - 5, y + 5, '%03d' % (v % 360), G)
    pyxel.tri(cx, y + 12, cx - 3, y + 16, cx + 3, y + 16, A_)


def _ladder(rect, pitch, roll, gamma):
    """ピッチラダーと飛行経路マーカー。水平線と同じ座標系で描く。"""
    hx, hy, ux, uy, f = fx.horizon_frame(rect, pitch, roll)
    ax, ay = -uy, ux
    x, y, w, h = rect
    pyxel.clip(x + 1, y + 1, w - 2, h - 2)
    for deg in (-20, -10, -5, 5, 10, 20):
        t = f * math.tan(math.radians(deg))
        bx, by = hx + ux * t, hy + uy * t
        half = 26 if abs(deg) >= 10 else 18
        for s in (-1, 1):
            x0, y0 = bx + ax * half * s, by + ay * half * s
            x1, y1 = bx + ax * (half * 0.45) * s, by + ay * (half * 0.45) * s
            if deg > 0:
                pyxel.line(x0, y0, x1, y1, G)
            else:                                    # 機首下げ側は破線
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                pyxel.line(x0, y0, (x0 + mx) / 2, (y0 + my) / 2, G)
                pyxel.line(mx, my, x1, y1, G)
        pyxel.text(bx + ax * 33 - 3, by + ay * 33 - 2, '%d' % abs(deg), G)
    # 飛行経路マーカー: 実際に機体が向かっている先
    t = f * math.tan(math.radians(gamma))
    fx_, fy_ = hx + ux * t, hy + uy * t
    pyxel.circb(fx_, fy_, 4, W_)
    pyxel.line(fx_ - 10, fy_, fx_ - 5, fy_, W_)
    pyxel.line(fx_ + 5, fy_, fx_ + 10, fy_, W_)
    pyxel.line(fx_, fy_ - 9, fx_, fy_ - 5, W_)
    pyxel.clip()


def _bank_scale(cx, cy, roll):
    for m in (-30, -20, -10, 0, 10, 20, 30):
        a = math.radians(m - 90)
        r0, r1 = 52, (58 if m % 30 == 0 else 55)
        pyxel.line(cx + math.cos(a) * r0, cy + math.sin(a) * r0,
                   cx + math.cos(a) * r1, cy + math.sin(a) * r1, G)
    ar = math.radians(roll - 90)
    pyxel.tri(cx + math.cos(ar) * 50, cy + math.sin(ar) * 50,
              cx + math.cos(ar + 0.09) * 43, cy + math.sin(ar + 0.09) * 43,
              cx + math.cos(ar - 0.09) * 43, cy + math.sin(ar - 0.09) * 43, A_)


def draw(rect, ac, extra='', nav=None, wind=None, course=None, pilot=None,
         chase=False, charter=None, job=None, look=0.0):
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    if abs(look) > 4.0:
        # 横を向いている間は、どちらを見ているかを出す
        s = 'LOOK %d%s' % (round(abs(look)), 'R' if look > 0 else 'L')
        pyxel.rect(cx - 16, cy - 40, len(s) * 4 + 3, 8, 0)
        pyxel.text(cx - 14, cy - 39, s, A_)
    # 外部視点や横を向いているときは、ピッチラダーが視線と合わないので出さない
    if not chase:
        _ladder(rect, math.degrees(ac.pitch), math.degrees(ac.roll),
                math.degrees(ac.gamma))
        _bank_scale(cx, cy, math.degrees(ac.roll))
    _tape_v(4, cy - 30, 30, 60, int(ac.kias), 10, 'KIAS', mark=ac.stall_kt)
    _tape_v(w - 38, cy - 30, 34, 60, int(ac.alt_ft / 10) * 10, 100, 'ALT FT')
    _heading_tape(cx, 4, ac.hdg_deg)
    if wind and wind[1] > 0.5:
        # 風向・風速と、滑走路に対する成分（正面/横）
        wdir, wkt, head, cross = wind
        pyxel.rect(2, 20, 52, 15, 0)
        pyxel.text(4, 22, 'WIND %03d' % int(wdir), G)
        pyxel.text(4, 29, '%2dKT X%+3d' % (int(wkt), int(cross)),
                   A_ if abs(cross) > 10 else G)
        a = math.radians(wdir - ac.hdg_deg + 180.0)     # 機首基準で矢印を回す
        wx, wy = 46, 27
        pyxel.line(wx - math.sin(a) * 5, wy + math.cos(a) * 5,
                   wx + math.sin(a) * 5, wy - math.cos(a) * 5, W_)
        pyxel.tri(wx + math.sin(a) * 6, wy - math.cos(a) * 6,
                  wx + math.sin(a + 2.4) * 4, wy - math.cos(a + 2.4) * 4,
                  wx + math.sin(a - 2.4) * 4, wy - math.cos(a - 2.4) * 4, W_)
    if nav:
        name, km, brg = nav
        nm = world.apt_short(name)[:14]
        pyxel.rect(2, 3, max(52, len(nm) * 4 + 14), 15, 0)
        pyxel.text(4, 5, 'TO ' + nm, G)
        pyxel.text(4, 12, '%4.1fKM %03d' % (km, brg), W_)
        d = (brg - ac.hdg_deg + 540) % 360 - 180        # 相対方位
        if abs(d) < 25:
            pyxel.tri(cx + d * 1.8, 17, cx + d * 1.8 - 3, 22,
                      cx + d * 1.8 + 3, 22, 11)
    # 昇降計
    vx = w - 46
    pyxel.line(vx, cy - 26, vx, cy + 26, G)
    vy = cy - max(-26, min(26, ac.vs_fpm / 40.0))
    pyxel.line(vx - 4, vy, vx, vy, A_)
    pyxel.text(vx - 24, cy + 31, '%+5d' % int(ac.vs_fpm), G)
    # 下段
    pyxel.rect(0, h - 11, w, 11, 0)
    pyxel.text(4, h - 8, 'THR %3d%%' % int(ac.throttle * 100), G)
    pyxel.text(56, h - 8, 'FLAP %2d' % ac.flap, A_ if ac.flap else G)
    pyxel.text(104, h - 8, 'RPM %4d' % ac.rpm, G)
    pyxel.text(152, h - 8, 'BRK' if ac.brake else '   ', R_ if ac.brake else G)
    pyxel.text(176, h - 8, extra, G)
    if course is not None and (course.active or course.msg_t > 0):
        if course.active:
            t = course.target()
            d = math.hypot(t[0] - ac.x, t[1] - ac.y) * 8.0 / 1000.0 if t else 0.0
            s = 'RING %d/%d  %5.1fS  %4.1fKM' % (course.idx + 1, len(course.rings),
                                                 course.time, d)
            pyxel.rect(cx - 52, 20, 104, 9, 0)
            pyxel.text(cx - 49, 22, s, A_)
        if course.msg_t > 0:
            mw = len(course.msg) * 4
            pyxel.rect(cx - mw // 2 - 2, 32, mw + 3, 8, 0)
            pyxel.text(cx - mw // 2, 33, course.msg, W_)
    if charter is not None and (charter.active or charter.msg_t > 0):
        # リングコースと同時に出ることがあるので、その分だけ下へずらす
        yy = 41 if (course is not None and course.active) else 20
        if charter.active:
            t = charter.left()
            s = 'CHARTER %s  %d:%02d' % (charter.dest.name[:7], int(t) // 60,
                                         int(t) % 60)
            pyxel.rect(cx - 52, yy, 104, 9, 0)
            pyxel.text(cx - 49, yy + 2, s, R_ if t < 60.0 else A_)
        if charter.msg_t > 0:
            mw = len(charter.msg) * 4
            pyxel.rect(cx - mw // 2 - 2, yy + 12, mw + 3, 8, 0)
            pyxel.text(cx - mw // 2, yy + 13, charter.msg, A_)
    if job is not None and (job.active or job.msg_t > 0):
        j = job.active
        if j is not None:
            s = j.status_line()
            pyxel.rect(cx - 60, 20, 120, 9, 0)
            pyxel.text(cx - 57, 22, s[:29], R_ if j.urgent() else A_)
        if job.msg_t > 0:
            mw = min(len(job.msg), 60) * 4
            pyxel.rect(cx - mw // 2 - 2, 32, mw + 3, 8, 0)
            pyxel.text(cx - mw // 2, 33, job.msg[:60], A_)
    if pilot is not None and (pilot.on or pilot.msg_t > 0):
        s = pilot.status or pilot.msg
        if s:
            mw = len(s) * 4
            pyxel.rect(cx - mw // 2 - 2, h - 32, mw + 3, 8, 0)
            pyxel.text(cx - mw // 2, h - 31, s, A_ if pilot.on else W_)
    # 警報
    if ac.stalled and pyxel.frame_count % 20 < 13:
        pyxel.text(cx - 10, cy - 46, 'STALL', R_)
    if ac.near_edge < 1.0 and pyxel.frame_count % 30 < 20:
        pyxel.text(cx - 40, cy + 44, 'AREA EDGE - TURN %03d' % ac.edge_bearing(), A_)
    if ac.msg_t > 0:
        mw = len(ac.msg) * 4
        pyxel.rect(cx - mw // 2 - 2, h - 23, mw + 3, 8, 0)
        pyxel.text(cx - mw // 2, h - 22, ac.msg, A_)
