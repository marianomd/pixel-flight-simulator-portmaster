"""空を飛ぶ他機。空港間を行き来するだけの簡単なAI。"""
import math
import random

import objects
import world

UNIT = 8.0


class Plane:
    def __init__(self, rnd):
        self.rnd = rnd
        a = rnd.choice(world.AIRPORTS)
        self.x, self.y = a.x + rnd.uniform(-300, 300), a.y + rnd.uniform(-300, 300)
        self.alt = rnd.uniform(35.0, 95.0)          # ユニット
        self.speed = rnd.uniform(4.2, 6.4)          # ユニット/秒（約34〜51m/s）
        self.hdg = rnd.uniform(0, math.tau)
        self.roll = 0.0
        self._pick_target()

    def _pick_target(self):
        a = self.rnd.choice(world.AIRPORTS)
        self.tx = a.x + self.rnd.uniform(-240, 240)
        self.ty = a.y + self.rnd.uniform(-240, 240)
        self.talt = self.rnd.uniform(35.0, 95.0)

    def update(self, dt):
        dx, dy = self.tx - self.x, self.ty - self.y
        dist = math.hypot(dx, dy)
        if dist < 40.0:
            self._pick_target()
            return
        want = math.atan2(dx, dy)
        err = (want - self.hdg + math.pi) % math.tau - math.pi
        rate = max(-0.35, min(0.35, err * 0.8))     # 旋回率[rad/s]
        self.hdg = (self.hdg + rate * dt) % math.tau
        self.roll += (math.degrees(rate) * 2.2 - self.roll) * min(1.0, dt * 2.0)
        self.alt += max(-2.0, min(2.0, self.talt - self.alt)) * dt * 0.25
        self.x += math.sin(self.hdg) * self.speed * dt
        self.y += math.cos(self.hdg) * self.speed * dt


class Traffic:
    """他機の群れ。描画用の辞書リストを返すだけで、当たり判定は持たない。"""

    def __init__(self, n=4, seed=17):
        rnd = random.Random(seed)
        self.planes = [Plane(rnd) for _ in range(n)]

    def update(self, dt):
        for p in self.planes:
            p.update(dt)

    def objects(self, cam, far=520.0):
        out = []
        for p in self.planes:
            if abs(p.x - cam[0]) > far or abs(p.y - cam[1]) > far:
                continue
            out.append(dict(model=objects.PLANE, pos=(p.x, p.y, p.alt),
                            yaw=math.degrees(p.hdg), scale=2.4,
                            lights=objects.PLANE_LIGHTS))
        return out
