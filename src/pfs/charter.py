"""チャーター便。空港から空港へ、制限時間内に運ぶ依頼。

依頼を受けると目的地と制限時間が決まる。目的地の滑走路に降りて停止すれば完了。
評価は「残り時間」と「着陸の点数」の合成で、空港の組み合わせごとに最高記録を残す。
"""
import math

import world

CRUISE_UPS = 5.6            # 巡航の想定対地速度[ユニット/秒]（約90kt）
MARGIN = 2.0                # 巡航にかかる時間の何倍もらえるか
SETUP = 120.0               # 離陸・上昇・進入のぶんの上乗せ[秒]


class Charter:
    def __init__(self):
        self.active = False
        self.origin = None
        self.dest = None
        self.limit = 0.0
        self.time = 0.0
        self.msg = ''
        self.msg_t = 0
        self.best = {}          # '出発>到着' -> 得点
        self.event = ''         # 'done' / 'fail'（読んだ側が消す）

    # ------------------------------------------------------------ 進行
    def _say(self, s, t=200):
        self.msg, self.msg_t = s, t

    def key(self):
        return '%s>%s' % (self.origin, self.dest.name) if self.dest else ''

    def start(self, ac):
        """いちばん近い空港を出発地にして、別の空港への依頼を作る。"""
        here = world.nearest_airport(ac.x, ac.y)
        others = [a for a in world.AIRPORTS if a is not here]
        if not others:
            self._say('NO DESTINATION')
            return
        # いちばん遠い空港のほうが依頼らしいので、遠いほうを選ぶ
        dest = max(others, key=lambda a: math.hypot(a.x - here.x, a.y - here.y))
        d = math.hypot(dest.x - here.x, dest.y - here.y)
        self.origin = here.name
        self.dest = dest
        self.limit = SETUP + d / CRUISE_UPS * MARGIN
        self.time = 0.0
        self.active = True
        self.event = 'start'
        self._say('CHARTER TO %s  %d MIN' % (dest.name, round(self.limit / 60.0)))

    def stop(self, msg='CHARTER CANCELLED'):
        self.active = False
        self.dest = None
        self._say(msg)

    def left(self):
        return max(0.0, self.limit - self.time)

    def update(self, ac, dt):
        if self.msg_t > 0:
            self.msg_t -= 1
        if not self.active:
            return
        self.time += dt
        if self.time > self.limit:
            self.stop('CHARTER FAILED - OUT OF TIME')
            self.event = 'fail'

    def arrive(self, result):
        """目的地に着陸したときに呼ぶ。得点を返す（対象外なら None）。"""
        if not self.active or not self.dest or result['apt'] != self.dest.name:
            return None
        if not result['on_rwy']:
            self.stop('CHARTER FAILED - MISSED THE RUNWAY')
            self.event = 'fail'
            return None
        spare = self.left() / self.limit                 # 0..1
        score = int(round(result['score'] * 0.6 + spare * 100.0 * 0.4))
        k = self.key()
        self.best[k] = max(self.best.get(k, 0), score)
        self.active = False
        self._say('CHARTER DONE  %d PTS  (%d MIN LEFT)'
                  % (score, round(self.left() / 60.0)), 300)
        self.dest = None
        self.event = 'done'
        return score

    # ------------------------------------------------------------ 保存
    def to_dict(self):
        return {'best': self.best}

    def from_dict(self, d):
        if d:
            self.best = {str(k): int(v) for k, v in (d.get('best') or {}).items()}
