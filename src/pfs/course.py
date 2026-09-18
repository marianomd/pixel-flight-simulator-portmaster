"""チェックポイント飛行。空中のリングを順にくぐるタイムアタック。"""
import math

import pyxel
import world

R = 11.0            # リング半径（約88m）
SEG = 14            # リングの分割数


def _make_rings():
    """CENTRAL から NORTH へ向かう8個のコース。"""
    a, b = world.AIRPORTS[0], world.AIRPORTS[1]
    out = []
    for i in range(8):
        t = (i + 1) / 9.0
        x = a.x + (b.x - a.x) * t + math.sin(t * 7.0) * 130.0
        y = a.y + (b.y - a.y) * t + math.cos(t * 5.0) * 110.0
        alt = 26.0 + math.sin(t * 4.2) * 14.0 + t * 26.0
        out.append([x, y, alt])
    # 各リングの向きは次のリングへの方位
    rings = []
    for i, (x, y, alt) in enumerate(out):
        nx, ny = (out[i + 1][0], out[i + 1][1]) if i + 1 < len(out) else (b.x, b.y)
        rings.append((x, y, alt, math.atan2(nx - x, ny - y)))
    return rings


class Course:
    def __init__(self):
        self.rings = _make_rings()
        self.active = False
        self.idx = 0
        self.time = 0.0
        self.best = None
        self.msg = ''
        self.msg_t = 0
        self._prev = None
        self.passed = False   # このフレームでリングを抜けたか

    # ---------------------------------------------------------------- 進行
    def start(self):
        self.active = True
        self.idx = 0
        self.time = 0.0
        self._prev = None
        self.passed = False   # このフレームでリングを抜けたか
        self._say('COURSE START - RING 1/%d' % len(self.rings))

    def stop(self):
        self.active = False
        self._say('COURSE CANCELLED')

    def _say(self, s, t=150):
        self.msg, self.msg_t = s, t

    def target(self):
        if not self.active or self.idx >= len(self.rings):
            return None
        return self.rings[self.idx]

    def update(self, ac, dt):
        if self.msg_t > 0:
            self.msg_t -= 1
        if not self.active:
            return
        self.time += dt
        cur = (ac.x, ac.y, ac.alt / world.TILE)     # 高度もユニットに揃える
        if self._prev is not None and self.idx < len(self.rings):
            if self._passed(self._prev, cur, self.rings[self.idx]):
                self.idx += 1
                self.passed = True
                if self.idx >= len(self.rings):
                    self.active = False
                    if self.best is None or self.time < self.best:
                        self.best = self.time
                        self._say('COURSE CLEAR %.1fS  NEW BEST!' % self.time, 300)
                    else:
                        self._say('COURSE CLEAR %.1fS  (BEST %.1fS)'
                                  % (self.time, self.best), 300)
                else:
                    self._say('RING %d/%d  %.1fS'
                              % (self.idx + 1, len(self.rings), self.time), 90)
        self._prev = cur

    @staticmethod
    def _passed(p0, p1, ring):
        """リング面を進行方向に横切り、かつ円の内側だったか。"""
        rx, ry, ralt, rh = ring
        nx, ny = math.sin(rh), math.cos(rh)
        d0 = (p0[0] - rx) * nx + (p0[1] - ry) * ny
        d1 = (p1[0] - rx) * nx + (p1[1] - ry) * ny
        if not (d0 < 0.0 <= d1):
            return False
        t = -d0 / (d1 - d0) if d1 != d0 else 0.0
        cx = p0[0] + (p1[0] - p0[0]) * t
        cy = p0[1] + (p1[1] - p0[1]) * t
        cz = p0[2] + (p1[2] - p0[2]) * t
        return math.hypot(math.hypot(cx - rx, cy - ry), cz - ralt) <= R

    # ---------------------------------------------------------------- 描画
    def draw(self, pr, cam, far=700.0):
        if not self.active:
            return
        for i in range(self.idx, min(self.idx + 3, len(self.rings))):
            rx, ry, ralt, rh = self.rings[i]
            if abs(rx - cam[0]) > far or abs(ry - cam[1]) > far:
                continue
            col = None if i == self.idx else 11    # None は白赤の交互
            ux, uy = math.cos(rh), -math.sin(rh)     # 面内の水平方向
            pts = []
            for k in range(SEG):
                a = k / SEG * math.tau
                c, s = math.cos(a), math.sin(a)
                p = pr.pt(rx + ux * R * c, ry + uy * R * c, ralt + R * s)
                pts.append(p)
            for k in range(SEG):
                p, q = pts[k], pts[(k + 1) % SEG]
                if p and q:
                    pyxel.line(p[0], p[1], q[0], q[1],
                               col if col else (12 if (k // 2) % 2 == 0 else 13))
            # 円だけだと向きも高さも読み取れないので、
            # 上端に棒を立て、地面まで柱を下ろす
            t0 = pr.pt(rx, ry, ralt + R)
            t1 = pr.pt(rx, ry, ralt + R * 1.45)
            if t0 and t1:
                pyxel.line(t0[0], t0[1], t1[0], t1[1], col or 12)
            g0 = pr.pt(rx, ry, 0.05)
            g1 = pr.pt(rx, ry, ralt - R)
            if g0 and g1:
                pyxel.line(g0[0], g0[1], g1[0], g1[1], col or 12)
