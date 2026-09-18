"""自動操縦。巡航と ILS（自動着陸）の2モード。

巡航には行き先を追う「NAV」と、気ままに飛ぶ「遊覧」がある。仕事中に
あてもなく飛んでも意味がないので、キャリアでは常にNAVで働く。

舵とスロットルを直接動かすので、作動中は手動入力を受け付けない。
制御はすべて比例制御で、目標姿勢へ寄せる形にしてある。
"""
import math
import random

import world
from aircraft import clamp, UNIT

OFF, CRUISE, ILS = 0, 1, 2
NAMES = ('OFF', 'CRUISE', 'ILS')

MIN_ALT_FT = 300.0          # これ以上でないと巡航モードに入れない
CRUISE_FT = 1500.0          # 遊覧で目指す高度。景色を広く見渡せる高さ
# 行き先へ向かうときの高度。仕事の目標（測線は最高787ft、見どころ、
# 場周経路）はどれも低いので、1500ftだと毎回降ろし直すことになる
NAV_FT = 800.0
CRUISE_KT = 95.0
NAV_OVER = 25.0             # 目標の真上（ユニット）。方位が暴れるので直進で抜ける
TRIM_RATE = math.radians(3.0)   # オートトリムの動く速さ[rad/s]。実機の電動トリム相当
ILS_MAX_D = 700.0           # ILSに入れる最大距離（ユニット、約5.6km）
ILS_MAX_LAT = 100.0         # 延長線からの許容横ずれ（約800m）
ILS_MAX_HDG = 45.0          # 滑走路方位との許容差[deg]
# (滑走路端までの距離, 許容横ずれ) — これを超えていたら復行する
GA_GATES = ((90.0, 12.0), (45.0, 6.0))
REJOIN_D = 300.0            # やり直しの進入開始点（滑走路端から）
EDGE_MARGIN = 70.0          # 空域端から内側にこれだけ余裕を残す
GLIDE_DEG = 6.2
# 狙う接地点（滑走路端の何ユニット先か）。向かい風だと対地速度が落ちて
# フレアの浮きが短くなり、滑走路の手前へ落ちてしまうので、風のぶん奥を狙う。
AIM_BASE = 6.0
AIM_PER_KT = 0.45           # 向かい風1ktあたり奥へずらす量[ユニット]
AIM_MAX = 17.0
LOC_P = 2.0                 # 横ずれ[ユニット] -> 目標トラック角[deg]
LOC_I = 0.05                # 横風のクラブを作る積分
LOC_I_MAX = 20.0
FLARE_RUD = 0.10            # フレア中にラダーで機首を滑走路へ
APP_KT = 62.0               # 基準機での進入速度
APP_FACTOR = 1.40           # 失速速度の何倍で進入するか（フラップを下ろした状態）


def _app_kt(ac):
    """その機体での進入速度。重い機体ほど速く降りないと失速する。"""
    return max(45.0, ac.stall_kt * APP_FACTOR)


def _lateral(ap, end, x, y):
    """滑走路の中心線からの横ずれ。進行方向から見て右が正。

    東西の滑走路は「+y が右」ではないので、南北と同じ式では符号が逆になる。
    ここを間違えるとローカライザが中心線から離れる向きに舵を当ててしまう。
    """
    s = ap.sign(end)
    if ap.axis == 'NS':
        return (x - ap.c) * s
    return -(y - ap.c) * s


def _best_approach(ac):
    """いま進入できる滑走路端を探す。

    「延長線にどれだけ乗っているか」を最優先で選ぶ。距離を主にすると、
    近いだけで見当違いの向きにある滑走路を掴んでしまう。
    """
    best = None
    hdg = math.degrees(ac.hdg) % 360.0
    for ap in world.AIRPORTS:
        for end in ap.ends():
            d = ap.dist_to_threshold(end, ac.x, ac.y)
            if not (20.0 < d < ILS_MAX_D):
                continue
            lat = (ac.x - ap.c) if ap.axis == 'NS' else (ac.y - ap.c)
            # 遠いほど横ずれは許すが、近いのに大きくずれていたら入れない
            if abs(lat) > min(ILS_MAX_LAT, 12.0 + d * 0.45):
                continue
            hd = (end[1] - hdg + 540.0) % 360.0 - 180.0
            if abs(hd) > ILS_MAX_HDG:
                continue
            score = abs(lat) * 4.0 + abs(hd) * 2.0 + d * 0.15
            if best is None or score < best[0]:
                best = (score, ap, end)
    return best


class Autopilot:
    def __init__(self):
        self.mode = OFF
        self.msg = ''
        self.msg_t = 0
        self.phase = ''
        self.rnd = random.Random(5)
        self.wp = None
        self.wind = None        # 風（狙う接地点の補正に使う）
        self.loc_i = 0.0        # ローカライザの積分（横風の定常偏差を消す）
        self.ga_n = 0           # 復行した回数
        self.wps = []           # やり直し周回の経由点
        self.pat_alt = 300.0
        self.ap = None          # ILSの対象空港
        self.end = None
        self.target = None      # 巡航で向かう先 (x, y)

    # ---------------------------------------------------------------- 制御
    @property
    def on(self):
        return self.mode != OFF

    def _say(self, s, t=120):
        self.msg, self.msg_t = s, t

    @staticmethod
    def approach_ready(ac):
        """いまAPを入れたらILSに乗れる位置か。受信機が無い旨を出す判断に使う。"""
        return _best_approach(ac) is not None

    def toggle(self, ac, forced=None, allow_ils=True):
        """SELECTで送る。巡航中に滑走路の延長線へ乗ればILSへ移れる。

        押すたび OFF -> 巡航 -> (進入できるなら)ILS -> OFF と回る。
        巡航のまま滑走路へ近づいたとき、いちど切ってから入れ直さずに済む。
        """
        if self.mode == CRUISE and forced is None and allow_ils:
            best = _best_approach(ac)
            if best is not None:
                self._engage_ils(best, ac)
                return
        if self.on:
            self.mode = OFF
            self.phase = ''
            self._say('AUTOPILOT OFF')
            return
        if ac.on_ground:
            self._say('AUTOPILOT NEEDS AIRBORNE')
            return
        best = _best_approach(ac) if allow_ils else None
        mode = forced or (ILS if best else CRUISE)
        if mode == ILS:
            if best is None:
                self._say('NO RUNWAY IN LINE')
                return
            self._engage_ils(best, ac)
        elif ac.alt_ft >= MIN_ALT_FT:
            self.mode = CRUISE
            self.wp = None
            self._say('AUTOPILOT CRUISE')
        else:
            self._say('NEED %d FT' % MIN_ALT_FT)

    def _engage_ils(self, best, ac=None):
        _, self.ap, self.end = best
        self.mode = ILS
        self.loc_i = 0.0
        self.ga_n = 0
        self.wps = []
        self.phase = 'INTERCEPT'
        name = 'ILS %s RWY %s' % (self.ap.name, self.end[2])
        # 進入路よりずっと高い位置で入れたら、降ろしきれないので周回から入る
        if ac is not None:
            d = self.ap.dist_to_threshold(self.end, ac.x, ac.y)
            path = max(0.0, d * UNIT * math.tan(math.radians(GLIDE_DEG)))
            if ac.alt > path + 150.0:
                self.phase = 'REPOS'
                self._pattern(ac)
                self._say(name + ' - HIGH, REPOSITIONING', 200)
                return
        self._say(name)

    def update(self, ac, dt, wind=None, target=None):
        self.wind = wind
        self.target = target        # (x, y) なら巡航でそこへ向かう
        if self.msg_t > 0:
            self.msg_t -= 1
        if self.mode == CRUISE:
            self._cruise(ac, dt)
        elif self.mode == ILS:
            self._ils(ac, dt)
        if self.mode != OFF and not ac.on_ground:
            self._autotrim(ac, dt)

    @staticmethod
    def _autotrim(ac, dt):
        """作動中はトリムも合わせる。実機の自動操縦と同じ。

        静安定は pitch を gamma+trim へ引き戻すので、trim を迎角に合わせれば
        舵の力が抜ける。合わせないと、機首上げいっぱいのままAPを入れたときに
        フレアで浮いて着陸が20点ほど落ちていた。切ったあともその姿勢に
        トリムが合っているので、手に戻したときも落ち着いている。
        """
        want = clamp(ac.pitch - ac.gamma, ac.TRIM_LO, ac.TRIM_HI)
        ac.trim += clamp(want - ac.trim, -TRIM_RATE * dt, TRIM_RATE * dt)

    # ---------------------------------------------------------------- 共通
    # 慣性を入れたあと、舵の当て方を振って測った結果、元の値がいちばん良かった。
    # 角速度を引く減衰項（平均65->45点、滑走路外4件）も、
    # ゲインを上げる方向（同50点、3件）も、強風で突風に負けて悪化した。
    KP_PITCH = 3.0
    KP_ROLL = 2.2

    @staticmethod
    def _fly(ac, pitch_deg, roll_deg, kt, rudder=0.0):
        ac.elevator = clamp((math.radians(pitch_deg) - ac.pitch)
                            * Autopilot.KP_PITCH, -1, 1)
        ac.aileron = clamp((math.radians(roll_deg) - ac.roll)
                           * Autopilot.KP_ROLL, -1, 1)
        ac.rudder = clamp(rudder, -1, 1)
        ac.throttle = clamp(ac.throttle + clamp((kt - ac.kias) * 0.006, -0.02, 0.02),
                            0.0, 1.0)

    @staticmethod
    def _hold_alt(ac, target_m, max_vs=4.0):
        """目標高度から目標ピッチを作る。"""
        err = target_m - ac.alt
        tgt_vs = clamp(err * 0.10, -max_vs, max_vs)          # m/s
        vs = ac.V * math.sin(ac.gamma)
        return clamp(math.degrees(ac.pitch) + clamp((tgt_vs - vs) * 2.0, -3.0, 3.0),
                     -8.0, 12.0)

    @staticmethod
    def _turn_to(ac, bearing_deg, limit=22.0):
        hdg = math.degrees(ac.hdg) % 360.0
        err = (bearing_deg - hdg + 540.0) % 360.0 - 180.0
        return clamp(err * 1.2, -limit, limit)

    # ---------------------------------------------------------------- 巡航
    def _cruise(self, ac, dt):
        if self.target is not None:
            roll, ft = self._nav(ac), NAV_FT
        else:
            roll, ft = self._wander(ac), CRUISE_FT
        pitch = self._hold_alt(ac, ft / 3.28084)
        if ac.flap:
            ac.set_flap(-1)
        ac.brake = False
        self._fly(ac, pitch, roll, CRUISE_KT)

    def _nav(self, ac):
        """行き先へ向かう。真上まで来たら直進で抜け、離れてからまた向き直る。"""
        tx, ty = self.target
        d = math.hypot(tx - ac.x, ty - ac.y)
        if d < NAV_OVER:
            self.phase = 'OVER'
            return 0.0
        self.phase = 'NAV'
        return self._turn_to(ac, math.degrees(math.atan2(tx - ac.x,
                                                         ty - ac.y)) % 360.0)

    def _wander(self, ac):
        """遊覧。空域のあちこちへ気ままに飛ぶ。"""
        if self.wp is None or math.hypot(self.wp[0] - ac.x, self.wp[1] - ac.y) < 120.0:
            m = 320.0
            self.wp = (self.rnd.uniform(m, world.WORLD - m),
                       self.rnd.uniform(m, world.WORLD - m))
        self.phase = 'ALT %d' % int(CRUISE_FT)
        return self._turn_to(ac, math.degrees(math.atan2(self.wp[0] - ac.x,
                                                         self.wp[1] - ac.y)) % 360.0)

    # ---------------------------------------------------------------- ILS
    def _ils(self, ac, dt):
        ap, end = self.ap, self.end
        d = ap.dist_to_threshold(end, ac.x, ac.y)          # ユニット
        lateral = _lateral(ap, end, ac.x, ac.y)             # 進行方向から見た右が正
        rw_hdg = end[1]

        if ac.on_ground:
            self._rollout(ac)
            return
        if self.phase == 'GOAROUND':
            self._goaround(ac, dt)
            return
        if self.phase == 'REPOS':
            self._repos(ac, dt, d, lateral)
            return
        # 近距離で中心線に乗れていないなら、無理に降りずにやり直す
        if ac.alt > 6.0 and self.ga_n < 2:
            for gd, gl in GA_GATES:
                if d < gd and abs(lateral) > gl:
                    self.phase = 'GOAROUND'
                    self.loc_i = 0.0
                    self.ga_n += 1
                    self._say('GO AROUND - NOT ALIGNED', 180)
                    return

        # ローカライザ。比例だけだと横風で一定量ずれたままになるので、
        # 積分項を足して機首を風上へ振らせる（クラブ）。
        self.loc_i = clamp(self.loc_i - lateral * dt * LOC_I, -LOC_I_MAX, LOC_I_MAX)
        # 同じトラック角でも速い機体ほど横ずれが速く詰まるので、速度で割る
        gain = LOC_P * (APP_KT / max(40.0, ac.kias))
        track = clamp(-lateral * gain + self.loc_i, -30.0, 30.0)
        roll = self._turn_to(ac, (rw_hdg + track) % 360.0, 25.0)

        # グライドパス: 滑走路端の少し先を狙う
        # フレアで多少伸びるぶん、狙いは滑走路端寄りにしておく
        tgt_alt = max(0.0, (d + self._aim(rw_hdg)) * UNIT
                      * math.tan(math.radians(GLIDE_DEG)))
        if d > 320.0:                                       # 遠いうちは高度を保つ
            self.phase = 'INTERCEPT'
            tgt_alt = max(tgt_alt, min(ac.alt, 460.0))
            kt = _app_kt(ac) * 1.37
            flap_want = 0
        elif ac.alt > 13.0:
            self.phase = 'GLIDE'
            kt = _app_kt(ac)
            flap_want = 3 if d < 150.0 else 2
        else:
            self.phase = 'FLARE'
            kt = _app_kt(ac)
            flap_want = 3
        while ac.flap_i < flap_want:
            ac.set_flap(1)
        while ac.flap_i > flap_want:
            ac.set_flap(-1)

        if self.phase == 'FLARE':
            # 接地に向けて沈下率を絞り込む（高度に比例した目標沈下率を追う）
            tgt_vs = -0.25 - ac.alt * 0.07
            vs = ac.V * math.sin(ac.gamma)
            pitch = clamp(math.degrees(ac.pitch) + clamp((tgt_vs - vs) * 3.0, -2.0, 2.0),
                          -2.0, 10.0)
            # アイドルにすると風車ブレーキで揚力が落ちて沈むので、
            # 接地直前まで少しだけ出力を残す。
            keep = 0.18 if ac.alt > 4.0 else 0.0
            ac.throttle += clamp(keep - ac.throttle, -1.2 * dt, 1.2 * dt)
            ac.elevator = clamp((math.radians(pitch) - ac.pitch) * 3.5, -1, 1)
            ac.aileron = clamp((0.0 - ac.roll) * 3.0, -1, 1)   # 翼を水平に戻す
            ac.rudder = clamp(-lateral * FLARE_RUD, -0.7, 0.7)  # 機首を滑走路へ
            return
        err = ac.alt - tgt_alt
        tgt_vs = -(ac.V * math.sin(math.radians(GLIDE_DEG))) - clamp(err * 0.12, -3.0, 3.0)
        vs = ac.V * math.sin(ac.gamma)
        pitch = clamp(math.degrees(ac.pitch) + clamp((tgt_vs - vs) * 2.2, -3.0, 3.0),
                      -9.0, 8.0)
        self._fly(ac, pitch, roll, kt)

    def _aim(self, rw_hdg):
        """狙う接地点。向かい風が強いほど奥を狙う。"""
        head = 0.0
        if self.wind is not None:
            head = self.wind.component(rw_hdg)[0]
        return min(AIM_MAX, AIM_BASE + max(0.0, head) * AIM_PER_KT)

    def _goaround(self, ac, dt):
        """復行。全開で上昇し、高度が取れたらやり直しの位置へ向かう。"""
        while ac.flap_i > 1:
            ac.set_flap(-1)
        ac.brake = False
        pitch = self._hold_alt(ac, 190.0, 5.0)
        roll = self._turn_to(ac, self.end[1], 20.0)
        self._fly(ac, clamp(pitch, 2.0, 11.0), roll, 75.0)
        ac.throttle = 1.0
        if ac.alt > 170.0:
            self.phase = 'REPOS'
            self._pattern(ac)
            self._say('REPOSITIONING', 120)

    def _pattern(self, ac):
        """やり直し用の周回経路。滑走路の手前側へ回り込み、45度で会合する。"""
        ap, end = self.ap, self.end
        s = ap.sign(end)
        lat = (ac.x - ap.c) if ap.axis == 'NS' else (ac.y - ap.c)
        side = 80.0 if lat >= 0.0 else -80.0
        # 空域の外に経由点を置くと、端で止められて永久にたどり着けない
        m = EDGE_MARGIN
        lim = world.WORLD - m

        def inside(p):
            return (min(max(p[0], m), lim), min(max(p[1], m), lim))

        self.wps = [inside(ap._pt(end[0] - s * 390.0, side)),
                    inside(ap._pt(end[0] - s * REJOIN_D, 0.0))]
        self.pat_alt = REJOIN_D * UNIT * math.tan(math.radians(GLIDE_DEG))

    def _repos(self, ac, dt, d, lateral):
        """周回経路をたどる。最後の点まで来たら通常の進入に戻す。"""
        if not self.wps:
            self.phase = 'INTERCEPT'
            self.loc_i = 0.0
            self._say('ILS %s RWY %s' % (self.ap.name, self.end[2]), 120)
            return
        wx, wy = self.wps[0]
        if math.hypot(wx - ac.x, wy - ac.y) < 30.0:
            self.wps.pop(0)
            return
        brg = math.degrees(math.atan2(wx - ac.x, wy - ac.y)) % 360.0
        while ac.flap_i > 0:
            ac.set_flap(-1)
        self._fly(ac, self._hold_alt(ac, max(self.pat_alt, 200.0)),
                  self._turn_to(ac, brg, 24.0), 90.0)

    def _rollout(self, ac):
        self.phase = 'ROLLOUT'
        ac.throttle = 0.0
        ac.elevator = 0.0
        ac.aileron = 0.0
        ap, end = self.ap, self.end
        lateral = _lateral(ap, end, ac.x, ac.y)
        ac.rudder = clamp(-lateral * 0.10, -0.8, 0.8)
        ac.brake = ac.kias < 55.0
        if ac.kias < 1.0:
            self.mode = OFF
            self.phase = ''
            ac.brake = True
            self._say('LANDED - AUTOPILOT OFF', 240)

    @property
    def status(self):
        if not self.on:
            return ''
        return 'AP %s %s' % (NAMES[self.mode], self.phase)
