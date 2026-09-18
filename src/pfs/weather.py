"""天候の演出。雨（風防を流れる水滴）。

速度が出ているときは風圧で画面中央から放射状に弾かれ、
低速（20kt未満）では重力で上から下へ流れ落ちる。両者は滑らかに混ざる。
旋回中はバンク角に応じて、水滴が旋回の外側へ流れる。
"""
import math
import random

import pyxel

HALF_W, HALF_H = 150.0, 104.0     # この範囲を出たら消える（画面中心からの距離）


def set_size(w, h):
    global HALF_W, HALF_H
    HALF_W, HALF_H = w * 0.586, h * 0.542
RADIAL_KT = 30.0                  # これ以上の速度で完全に放射状
GRAVITY_KT = 0.0                  # 停止時は完全に落下（間は連続的に混ざる）
BANK_FLOW = 0.5                   # バンクで横へ流れる量（速度に依らない分）
BANK_FLOW_V = 0.055               # 同上、対気速度[m/s]あたり


class Rain:
    def __init__(self, n=52, seed=7):
        self.rnd = random.Random(seed)
        self.drops = [self._spawn(1.0, spread=True) for _ in range(n)]

    def _spawn(self, w, spread=False):
        """w: 放射状の割合(0=落下, 1=放射)。x, y は画面中心からの相対位置。"""
        r = self.rnd
        if w > 0.5:
            if spread:
                a, d = r.uniform(0, math.tau), r.uniform(2.0, 110.0)
            else:
                a = r.uniform(0, math.tau)
                d = r.uniform(1.5, 16.0) if r.random() < 0.7 else r.uniform(16.0, 95.0)
            x, y = math.cos(a) * d, math.sin(a) * d
        else:                                     # 落下時は上のほうから降ってくる
            x = r.uniform(-HALF_W, HALF_W)
            y = r.uniform(-HALF_H, HALF_H) if spread else r.uniform(-HALF_H, -52.0)
        return [x, y, r.uniform(0.55, 1.6), 0.0, 1.0]

    def update(self, speed_ms, scale=1.0, roll=0.0):
        """speed_ms: 対気速度[m/s]。速いほど水滴が速く弾かれる。

        roll: バンク角[rad]（右が正）。左旋回なら水滴は右へ流れる。
        scale はフレームレート換算（30FPSなら2.0）。
        """
        kt = speed_ms * 1.94384
        w = (kt - GRAVITY_KT) / (RADIAL_KT - GRAVITY_KT)
        w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
        k = (0.031 + speed_ms * 0.0087) * scale   # 放射方向の基本速度
        # 旋回中は風防を斜めに横切る流れになる。左バンクなら右へ。
        sr, cr = math.sin(roll), math.cos(roll)
        side = -sr * (BANK_FLOW + speed_ms * BANK_FLOW_V) * scale
        # 低速時の落下方向も機体と一緒に傾く（コクピットから見た重力の向き）
        gx, gy = -sr * 0.90 + 0.07, cr * 0.90
        rnd = self.rnd
        for d in self.drops:
            r = math.hypot(d[0], d[1]) or 0.001
            rad = (1.6 + r * 0.17) * k
            vx = ((d[0] / r) * rad + side) * w + gx * scale * (1.0 - w)
            vy = (d[1] / r) * rad * w + gy * scale * (1.0 - w)
            d[0] += vx
            d[1] += vy
            d[3], d[4] = vx, vy
            # 風圧でちぎれて消えるのは高速時だけ。低速では素直に流れ落ちる
            if (abs(d[0]) > HALF_W or abs(d[1]) > HALF_H
                    or rnd.random() < 0.002 + 0.009 * w):
                d[0], d[1], d[2], d[3], d[4] = self._spawn(w)

    def wipe(self, cx, cy, px, py, ang, half):
        """ワイパーが通った帯にある水滴を消す。座標は画面中心からの相対。"""
        ox, oy = px - cx, py - cy
        for d in self.drops:
            dx, dy = d[0] - ox, d[1] - oy
            if dy > -1.0:
                continue
            a = math.atan2(dx, -dy)
            if abs(a - ang) < half:
                d[0], d[1], d[2], d[3], d[4] = self._spawn(0.0)
                d[1] = -HALF_H * 0.98

    def draw(self, rect, col):
        x, y, w, h = rect
        cx, cy = x + w * 0.5, y + h * 0.5
        pyxel.clip(x, y, w, h)
        for dx, dy, f, vx, vy in self.drops:
            v = math.hypot(vx, vy) or 0.001
            ln = (1.6 + math.hypot(dx, dy) * 0.09) * f
            ln = min(ln, 14.0)
            px, py = cx + dx, cy + dy
            pyxel.line(px, py, px + vx / v * ln, py + vy / v * ln, col)
        pyxel.clip()


def turbulence(speed_ms, alt_m, in_cloud, raining, t, tas_ms, on_ground):
    """乱気流の強さと揺れ。(ロール率[deg/s], ピッチ率[deg/s], 画面の揺れ) を返す。

    空気の流れが機体を叩くので、地上や低速ではほとんど効かない。
    揺れはずっと続くのではなく、風が強いほど頻繁で強い突風として来る。
    """
    if on_ground or tas_ms < 8.0 or speed_ms < 1.0:
        return 0.0, 0.0, 0.0
    k = speed_ms / 11.0
    k *= 0.45 + 0.85 * math.exp(-alt_m / 130.0)      # 低空ほど荒れる
    k *= min(1.2, tas_ms / 34.0)                     # 速いほど強く叩かれる
    if in_cloud:
        k *= 1.9
    if raining:
        k *= 1.35
    if k < 0.02:
        return 0.0, 0.0, 0.0
    # 突風の来かた。風が弱いほど閾値が高くなり、間隔があいて短くなる
    env = 0.5 + 0.5 * (0.62 * math.sin(t * 0.29 + 0.7)
                       + 0.38 * math.sin(t * 0.107 + 2.3))
    thr = 1.0 - min(0.92, k * 0.85)
    burst = max(0.0, env - thr) / max(0.08, 1.0 - thr)
    if burst <= 0.0:
        return 0.0, 0.0, 0.0
    g = k * burst
    # うねりの粗さが違う波を重ねて、規則性を感じさせない
    nr = (math.sin(t * 0.83 + 1.3) * 0.6 + math.sin(t * 2.17) * 0.3
          + math.sin(t * 5.3 + 2.2) * 0.1)
    np_ = (math.sin(t * 0.71 + 0.4) * 0.6 + math.sin(t * 1.93 + 2.7) * 0.4)
    return nr * g * 11.0, np_ * g * 5.4, min(0.7, g * 0.48)


class Wiper:
    """風防のワイパー。雨のときに往復して水滴を拭き取る。"""

    SWEEP = 0.92          # 振れ幅[rad]（片側）
    SPEED = 2.6           # 角速度[rad/s]
    REST = 0.7            # 端で止まっている時間[s]

    def __init__(self):
        self.on = True
        self._pivot_ref = (128.0, 96.0, 128.0, 196.0)
        self.a = -0.92
        self.dir = 1.0
        self.rest = 0.0

    def update(self, dt, rain, active):
        if not (self.on and active):
            self.rest = 0.0
            self.a = -self.SWEEP
            self.dir = 1.0
            return
        if self.rest > 0.0:
            self.rest -= dt
            return
        self.a += self.dir * self.SPEED * dt
        if abs(self.a) >= self.SWEEP:
            self.a = math.copysign(self.SWEEP, self.a)
            self.dir = -self.dir
            self.rest = self.REST
        if rain is not None:
            cx, cy, px, py = self._pivot_ref
            rain.wipe(cx, cy, px, py, self.a, 0.16)

    def draw(self, rect, col):
        x, y, w, h = rect
        px, py = x + w * 0.5, y + h + 4.0
        self._pivot_ref = (x + w * 0.5, y + h * 0.5, px, py)
        if not self.on:
            return
        ln = h * 1.02
        ex = px + math.sin(self.a) * ln
        ey = py - math.cos(self.a) * ln
        pyxel.clip(x, y, w, h)
        # 芯の左右にもう1本ずつ引いて、太いゴムに見せる
        for o in (-1, 0, 1):
            pyxel.line(px + o, py, ex + o, ey, col)
        pyxel.clip()


# ------------------------------------------------------------------ 風
# SEVEREは荒天運航のスキルを取ってから出る段。AUTOを4に留めるため後ろに足す
WIND_LEVELS = ('CALM', 'LIGHT', 'MODERATE', 'STRONG', 'AUTO', 'SEVERE')
WIND_SPEED = (0.0, 3.0, 6.5, 11.0, 0.0, 13.5)   # m/s（0/6/13/21/-/26kt相当）
AUTO = 4


class Wind:
    """一様な風。機体は空気の塊ごと流されるので、対気速度は変わらず対地の軌跡だけずれる。

    direction は「風が吹いてくる方位」[deg]。滑走路36に対して 270 なら左からの横風。
    """

    def __init__(self, level=1, direction=250.0):
        self.level = level
        self.direction = direction
        self.gust_t = 0.0
        self.shear_on = True
        self.sh_t = 0.0         # 残りの継続時間[秒]
        self.sh_dir = 0.0       # 目標の方位差[deg]
        self.sh_spd = 1.0       # 目標の速度倍率
        self.c_dir = 0.0        # いまの方位差（数秒かけて追従する）
        self.c_spd = 1.0
        self.warn = 0           # 警報を出すフレーム数
        self.rnd = random.Random(77)

    @property
    def level_name(self):
        return WIND_LEVELS[self.level]

    @property
    def base_speed(self):
        if self.level == AUTO:
            return max(0.0, getattr(self, '_auto', 3.0))
        return WIND_SPEED[self.level]

    def set_level(self, i):
        self.level = i % len(WIND_LEVELS)

    def turn(self, d):
        self.direction = (self.direction + d) % 360.0

    @property
    def eff_dir(self):
        """ウィンドシアを含めた、いま吹いている向き。"""
        return (self.direction + self.c_dir) % 360.0

    def _shear(self, dt, alt, airborne):
        """低空でときどき起きる風向・風速の急変。"""
        if self.warn > 0:
            self.warn -= 1
        active = (self.shear_on and airborne and self.level != 0
                  and alt is not None and alt < 320.0)
        if active and self.sh_t > 0.0:
            self.sh_t -= dt
            tgt_d, tgt_s = self.sh_dir, self.sh_spd
        else:
            tgt_d, tgt_s = 0.0, 1.0
            if not active:
                self.sh_t = 0.0
            elif self.rnd.random() < dt * 0.010:      # 平均100秒に1回
                self.sh_dir = self.rnd.uniform(-55.0, 55.0)
                self.sh_spd = self.rnd.uniform(0.35, 1.9)
                self.sh_t = self.rnd.uniform(6.0, 14.0)
                self.warn = 160
        k = min(1.0, dt * 0.7)                        # 数秒かけて入れ替わる
        self.c_dir += (tgt_d - self.c_dir) * k
        self.c_spd += (tgt_s - self.c_spd) * k

    def update(self, dt, alt=None, airborne=False):
        self._shear(dt, alt, airborne)
        self.gust_t += dt
        if self.level == AUTO:
            # 風向はゆっくり回り、風速も時間とともに変わる
            self.direction = (self.direction
                              + (0.9 * math.sin(self.gust_t * 0.031)
                                 + 0.4 * math.sin(self.gust_t * 0.011)) * dt * 6.0) % 360.0
            self._auto = 1.6 + 5.2 * (0.5 + 0.5 * math.sin(self.gust_t * 0.017)) \
                + 1.4 * math.sin(self.gust_t * 0.043)

    def speed(self):
        """突風込みの風速[m/s]。"""
        if self.level == 0:
            return 0.0
        if self.base_speed <= 0.05:
            return 0.0
        g = 1.0 + 0.18 * math.sin(self.gust_t * 0.7) + 0.09 * math.sin(self.gust_t * 1.9)
        return self.base_speed * g * self.c_spd

    def vector(self):
        """風が流していく向きの速度[m/s]を (東成分, 北成分) で返す。"""
        s = self.speed()
        if s <= 0.0:
            return 0.0, 0.0
        a = math.radians(self.eff_dir + 180.0)       # 吹いてくる方位 -> 流れる方位
        return s * math.sin(a), s * math.cos(a)

    def component(self, runway_hdg):
        """滑走路に対する (正面成分, 横成分)[kt]。正面が正なら向かい風。"""
        s = self.speed() * 1.94384
        d = math.radians(self.eff_dir - runway_hdg)
        return s * math.cos(d), s * math.sin(d)
