"""接地の土煙・タイヤ痕・鳥の群れ。ワールド座標に置いて投影して描く。

土煙は接地の沈下率に比例した量が出る。雨天なら茶色い煙ではなく白い水しぶきになる。
タイヤ痕は滑走路に残り、次の着陸のときの目印になる。
"""
import math
import random

import pyxel

MAX_PUFF = 60
MAX_MARK = 12                 # 残すタイヤ痕の本数
# 色番号は fx.apply_tod で塗り替えたあとの並び（9=土, 12=白, 3=淡い青）
DUST = (9, 9, 12)             # 乾いた路面の土煙
SPRAY = (12, 12, 3)           # 濡れた路面の水しぶき
BIRD_N = 7                    # 1群の羽数
BIRD_HIT = 3.4                # この距離[ユニット]まで近づくと当たる
BIRD_SPD = 1.4                # 鳥の速度[ユニット/秒]


class Effects:
    def __init__(self, seed=12):
        self.rnd = random.Random(seed)
        self.puffs = []       # [x, y, z, vx, vy, vz, r, life, col]
        self.marks = []       # (x0, y0, x1, y1) 滑走路に残る接地痕
        self.roll_t = 0.0     # 滑走中に煙を出す間隔

    # ------------------------------------------------------------ 発生
    def _puff(self, x, y, z, vx, vy, vz, r, life, cols):
        if len(self.puffs) >= MAX_PUFF:
            del self.puffs[0]
        self.puffs.append([x, y, z, vx, vy, vz, r, life,
                           cols[self.rnd.randrange(len(cols))]])

    def touchdown(self, x, y, hdg, vs, speed, wet):
        """接地。沈下率が大きいほど煙が多く、遠くまで飛ぶ。"""
        rnd = self.rnd
        cols = SPRAY if wet else DUST
        n = int(min(22.0, 4.0 + abs(vs) * 6.0))
        sh, ch = math.sin(hdg), math.cos(hdg)
        for _ in range(n):
            side = rnd.uniform(-1.6, 1.6)          # 主脚の左右
            back = rnd.uniform(-1.8, 0.8)          # 負なら前方へ飛ぶ
            px = x + ch * side - sh * back
            py = y - sh * side - ch * back
            sp = (0.25 + abs(vs) * 0.11) * rnd.uniform(0.4, 1.5)
            self._puff(px, py, 0.05,
                       -sh * sp + rnd.uniform(-0.12, 0.12),
                       -ch * sp + rnd.uniform(-0.12, 0.12),
                       (0.05 + abs(vs) * 0.02) * rnd.uniform(0.5, 1.4),
                       rnd.uniform(0.5, 1.3), rnd.uniform(1.1, 2.2), cols)
        # 接地痕は進行方向へ伸ばす
        ln = min(9.0, 1.5 + speed * 0.12)
        for side in (-1.0, 1.0):
            self.marks.append((x + ch * side, y - sh * side,
                               x + ch * side + sh * ln, y - sh * side + ch * ln))
        del self.marks[:-MAX_MARK * 2]

    def rolling(self, x, y, hdg, speed, dt, wet):
        """濡れた路面を滑走中の水しぶき。"""
        if not wet or speed < 8.0:
            self.roll_t = 0.0
            return
        self.roll_t += dt
        if self.roll_t < 0.06:
            return
        self.roll_t = 0.0
        rnd = self.rnd
        sh, ch = math.sin(hdg), math.cos(hdg)
        for side in (-1.0, 1.0):
            self._puff(x + ch * side, y - sh * side, 0.05,
                       -sh * 0.10 + rnd.uniform(-0.05, 0.05),
                       -ch * 0.10 + rnd.uniform(-0.05, 0.05),
                       0.03 + speed * 0.001, rnd.uniform(0.3, 0.6),
                       rnd.uniform(0.5, 0.9), SPRAY)

    # ------------------------------------------------------------ 更新
    def update(self, dt):
        out = []
        for p in self.puffs:
            p[7] -= dt
            if p[7] <= 0.0:
                continue
            p[0] += p[3] * dt
            p[1] += p[4] * dt
            p[2] += p[5] * dt
            p[5] -= p[5] * 1.6 * dt              # 上昇はすぐ鈍る
            p[3] *= 1.0 - 1.1 * dt
            p[4] *= 1.0 - 1.1 * dt
            p[6] += dt * 0.22                    # だんだん広がる
            out.append(p)
        self.puffs = out

    def clear(self):
        self.puffs = []
        self.marks = []

    # ------------------------------------------------------------ 描画
    def draw(self, pr, night=False):
        col_mark = 5 if night else 0
        for x0, y0, x1, y1 in self.marks:
            a = pr.pt(x0, y0, 0.0)
            b = pr.pt(x1, y1, 0.0)
            if a and b and (pr.on_screen(a) or pr.on_screen(b)):
                pyxel.line(a[0], a[1], b[0], b[1], col_mark)
        pyxel.dither(0.5)
        for x, y, z, vx, vy, vz, r, life, col in self.puffs:
            p = pr.pt(x, y, z)
            if not pr.on_screen(p, 20):
                continue
            rad = pr.f * r / p[2]
            if rad < 0.8:
                pyxel.pset(p[0], p[1], col)
            else:
                pyxel.circ(p[0], p[1], min(rad, 10.0), col)
        pyxel.dither(1.0)


def landing_light(pr, ac, col=14):
    """機首前方の地面を照らす着陸灯。手前ほど明るく、遠くへ薄れていく。"""
    if ac.alt > 130.0:
        return
    sh, ch = math.sin(ac.hdg), math.cos(ac.hdg)
    fade = 1.0 - ac.alt / 130.0
    # 手前から順に台形を重ねて、円錐状の光にする
    bands = ((1.5, 0.7, 8.0, 2.6, 0.60), (8.0, 2.6, 20.0, 5.6, 0.42),
             (20.0, 5.6, 36.0, 9.4, 0.26), (36.0, 9.4, 58.0, 14.0, 0.13))
    for d0, w0, d1, w1, k in bands:
        q = []
        for d, wd in ((d0, w0), (d1, w1)):
            for side in (-1.0, 1.0):
                q.append(pr.pt(ac.x + sh * d + ch * wd * side,
                               ac.y + ch * d - sh * wd * side, 0.0))
        if any(p is None for p in q):
            continue
        pyxel.dither(k * fade)
        pyxel.tri(q[0][0], q[0][1], q[1][0], q[1][1], q[3][0], q[3][1], col)
        pyxel.tri(q[0][0], q[0][1], q[3][0], q[3][1], q[2][0], q[2][1], col)
    pyxel.dither(1.0)


class Birds:
    """低空を横切る鳥の群れ。ぶつかるとエンジンが不調になる。"""

    def __init__(self, seed=31):
        self.rnd = random.Random(seed)
        self.flock = None      # [x, y, alt, hdg, 個体のずれ...]
        self.t = 0.0

    def reset(self):
        self.flock = None

    def _spawn(self, ac):
        r = self.rnd
        a = r.uniform(0, math.tau)
        d = r.uniform(55.0, 90.0)
        bx, by = ac.x + math.sin(a) * d, ac.y + math.cos(a) * d
        # 機体の少し先を狙って飛ぶ。狙いはばらつくので、当たるのは時々。
        lead = d / (BIRD_SPD + ac.V / 8.0)
        tx = ac.x + math.sin(ac.hdg) * (ac.V / 8.0) * lead + r.uniform(-9.0, 9.0)
        ty = ac.y + math.cos(ac.hdg) * (ac.V / 8.0) * lead + r.uniform(-9.0, 9.0)
        self.flock = {
            'x': bx, 'y': by,
            'alt': max(12.0, ac.alt + r.uniform(-22.0, 22.0)),
            'hdg': math.atan2(tx - bx, ty - by), 'life': 40.0,
            'ofs': [(r.uniform(-2.2, 2.2), r.uniform(-1.6, 1.6),
                     r.uniform(-6.0, 6.0), r.uniform(0, math.tau))
                    for _ in range(BIRD_N)]}

    def update(self, ac, dt, enabled):
        """近づいたら True（バードストライク）を返す。"""
        if not enabled or ac.on_ground:
            self.flock = None
            return False
        self.t += dt
        if self.flock is None:
            # 低空ほど鳥が多い
            if ac.alt > 400.0 or self.t < 30.0:
                return False
            if self.rnd.random() > dt * 0.014:
                return False
            self.t = 0.0
            self._spawn(ac)
            return False
        f = self.flock
        f['life'] -= dt
        sp = BIRD_SPD * dt
        f['x'] += math.sin(f['hdg']) * sp
        f['y'] += math.cos(f['hdg']) * sp
        if f['life'] <= 0.0:
            self.flock = None
            return False
        if (math.hypot(f['x'] - ac.x, f['y'] - ac.y) < BIRD_HIT
                and abs(f['alt'] - ac.alt) < BIRD_HIT * 8.0):
            self.flock = None
            return True
        return False

    def draw(self, pr, phase):
        f = self.flock
        if f is None:
            return
        for dx, dy, dz, ph in f['ofs']:
            p = pr.pt(f['x'] + dx, f['y'] + dy, (f['alt'] + dz) / 8.0)
            if not pr.on_screen(p, 8):
                continue
            w = 1 + int(pr.f * 1.2 / p[2])
            if w > 12:
                w = 12
            # はばたき（上下する翼）
            k = math.sin(phase * 6.0 + ph)
            x, y = int(p[0]), int(p[1])
            pyxel.line(x - w, y - int(k * w * 0.6), x, y, 0)
            pyxel.line(x, y, x + w, y - int(k * w * 0.6), 0)
