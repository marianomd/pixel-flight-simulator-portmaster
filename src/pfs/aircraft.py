"""飛行力学。3自由度の質点モデル（迎角・失速・バンク旋回・地上滑走を含む）。

単位系: 速度と高度はSI(m/s, m)、水平位置はマップ単位(1ユニット=8m)。
方位 hdg はコンパス基準のラジアン（0 = マップ+y方向 = 北、右旋回で増加）。
"""
import math
import random
import world

G = 9.81
RHO = 1.225
UNIT = 8.0          # 1マップユニット = 8 m
EYE = 2.6           # 目線の地上高 [m]
KT = 1.94384        # m/s -> kt
FT = 3.28084        # m -> ft
FPM = 196.85        # m/s -> ft/min

FLAP_STEPS = (0, 10, 20, 30)
PITCH_RATE = 17.0     # 舵いっぱいでのピッチ角速度[deg/s]。26だと敏感すぎた
ROLL_RATE = 45.0      # 同じくロール
YAW_RATE = 9.0        # 同じくヨー
# 慣性。舵を切っても角速度がこの時定数[秒]で遅れて立ち上がり、
# 戻しても同じだけ遅れて止まる。機体の重さが手に伝わる。
TAU_PITCH = 0.32
TAU_ROLL = 0.22       # 補助翼はよく効くので短め
TAU_YAW = 0.40        # 方向舵はいちばん鈍い


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


IDEAL_TD = 150.0        # 理想の接地点（滑走路端から何m）


def _score_landing(apt, grade, vs, zone, lateral, on_rwy, wing):
    """接地を100点満点で採点する。沈下率40点・接地点30点・センターライン30点。"""
    if not on_rwy or wing:
        score = 0
    else:
        sink = clamp(1.0 - (abs(vs) - 0.6) / 2.4, 0.0, 1.0) * 40.0
        zpt = clamp(1.0 - abs(zone - IDEAL_TD) / 400.0, 0.0, 1.0) * 30.0
        lat = clamp(1.0 - abs(lateral) / 60.0, 0.0, 1.0) * 30.0
        score = int(round(sink + zpt + lat))
    return {'apt': apt, 'grade': grade, 'vs': round(vs, 2),
            'zone': int(zone), 'lateral': int(lateral),
            'on_rwy': bool(on_rwy), 'score': score}


def score_parts(r):
    """採点の内訳 [(名前, 実測値, 得点, 満点)]。リザルト画面で内訳を出すため。"""
    ok = r['on_rwy'] and r['grade'] != 'WINGTIP STRIKE'
    sink = clamp(1.0 - (abs(r['vs']) - 0.6) / 2.4, 0.0, 1.0) * 40.0 if ok else 0.0
    zpt = (clamp(1.0 - abs(r['zone'] - IDEAL_TD) / 400.0, 0.0, 1.0) * 30.0
           if ok else 0.0)
    lat = clamp(1.0 - abs(r['lateral']) / 60.0, 0.0, 1.0) * 30.0 if ok else 0.0
    return [('SINK RATE', '%d FPM' % round(abs(r['vs']) * FPM),
             int(round(sink)), 40),
            ('TOUCHDOWN', '%d M' % r['zone'], int(round(zpt)), 30),
            ('CENTRELINE', '%d M' % abs(r['lateral']), int(round(lat)), 30)]


class Aircraft:
    # セスナ172相当
    MASS = 1100.0
    WING = 16.2
    CL0, CLA = 0.30, 5.0
    A_STALL = math.radians(15.0)
    CD0, K = 0.032, 0.045
    THRUST = 3050.0
    VNE = 82.0

    def __init__(self):
        self.msg = ''
        self.msg_t = 0
        self.reset_runway()

    # ------------------------------------------------------------ 初期配置
    def reset_runway(self):
        """滑走路の末端に駐機。"""
        self.engine = 1.0
        self.x = float(world.RW_X)
        self.y = float(world.RW_Y0 + 10)
        self.alt = 0.0
        self.V = 0.0
        self.gamma = 0.0
        self.hdg = 0.0                  # 滑走路36（真北）
        self.pitch = 0.0
        self.roll = 0.0
        self.throttle = 0.0
        self.trim = math.radians(2.0)
        self.flap_i = 0
        self.brake = True
        self.on_ground = True
        self.elevator = self.aileron = self.rudder = 0.0
        self.engine = 1.0         # 出力の倍率。0で停止、0.5などで不調
        # 機体の傷み（キャリアモードで career.apply が書き込む）
        self.dmg_drag = 0.0       # 抗力の上乗せ
        self.dmg_lift = 1.0       # 揚力係数の倍率
        self.dmg_power = 1.0      # 出力の倍率
        self.dmg_brake = 1.0      # ブレーキの効きの倍率
        self.touchdown_vs = 0.0
        self.last_landing = None  # 直近の着陸記録
        self.q_rate = 0.0         # ピッチ角速度[rad/s]（慣性で遅れる）
        self.p_rate = 0.0         # ロール角速度
        self.r_rate = 0.0         # ヨー角速度
        self.accel = 0.0          # 前後加速度 [m/s^2]
        self.dip = 0.0            # 制動による機首の沈み込み [deg]
        self._say('READY  RWY 36')

    def reset_final(self):
        """最終進入のやり直し位置。"""
        self.engine = 1.0
        self.reset_runway()
        d = 340.0                                 # 滑走路端まで340ユニット=2.7km
        off = random.uniform(-26.0, 26.0)          # 横のずれ ±208m
        self.x = float(world.RW_X) + off
        self.y = world.RW_Y0 - d
        self.hdg = math.radians(random.uniform(-5.0, 5.0))
        self.alt = d * UNIT * math.tan(math.radians(6.2))   # PAPI標準経路の上
        self.V = 31.0
        self.gamma = math.radians(-6.2)
        self.pitch = math.radians(-1.5)
        self.throttle = 0.30
        self.flap_i = 2
        self.brake = False
        self.on_ground = False
        self._say('ON FINAL  RWY 36  %s%dM' %
                  ('R' if off > 0 else 'L', abs(off) * UNIT), 200)

    def place_at(self, ap, end=None):
        """指定した空港の滑走路末端に置き直す（不時着からの回収など）。"""
        end = end or ap.ends()[0]
        sgn = ap.sign(end)
        self.x, self.y = ap._pt(end[0] + sgn * 10.0, 0.0)
        self.alt = 0.0
        self.V = 0.0
        self.gamma = 0.0
        self.hdg = math.radians(end[1])
        self.pitch = 0.0
        self.roll = 0.0
        self.throttle = 0.0
        self.flap_i = 0
        self.brake = True
        self.on_ground = True
        self.elevator = self.aileron = self.rudder = 0.0
        self.engine = 1.0
        self.last_landing = None

    def reset_cruise(self):
        self.engine = 1.0
        self.reset_runway()
        self.x = world.RW_X - 260.0
        self.y = world.RW_Y0 - 520.0
        self.alt = 520.0
        self.V = 55.0
        self.hdg = math.radians(20.0)
        self.pitch = math.radians(2.0)
        self.throttle = 0.7
        self.brake = False
        self.on_ground = False
        self._say('CRUISE')

    # ------------------------------------------------------------ 表示用
    @property
    def flap(self):
        return FLAP_STEPS[self.flap_i]

    @property
    def kias(self):
        return self.V * KT

    @property
    def alt_ft(self):
        return self.alt * FT

    @property
    def vs_fpm(self):
        return self.V * math.sin(self.gamma) * FPM

    @property
    def alt_units(self):
        return (self.alt + EYE) / UNIT

    @property
    def hdg_deg(self):
        return math.degrees(self.hdg) % 360.0

    @property
    def alpha(self):
        return self.pitch if self.on_ground else self.pitch - self.gamma

    @property
    def flap_cl(self):
        return self.flap * 0.022

    @property
    def stall_alpha(self):
        """フラップを下ろすほど失速迎角はわずかに浅くなる。"""
        return self.A_STALL - math.radians(self.flap * 0.055)

    @property
    def cl_max(self):
        return self.CL0 + self.CLA * self.stall_alpha + self.flap_cl

    @property
    def stall_speed(self):
        """1G水平飛行での失速速度[m/s]。フラップで下がり、翼が傷むと上がる。"""
        return math.sqrt(2.0 * self.MASS * G
                         / (RHO * self.WING * self.cl_max * self.dmg_lift))

    @property
    def stall_kt(self):
        return self.stall_speed * KT

    @property
    def stalled(self):
        return self.alpha > self.stall_alpha and not self.on_ground

    @property
    def rpm(self):
        if self.engine <= 0.01:
            return int(self.V * 6.0)          # 停止後は風車のように空転する
        return int((700 + self.throttle * 1900) * (0.45 + 0.55 * self.engine))

    def _say(self, s, t=150):
        self.msg, self.msg_t = s, t

    # ------------------------------------------------------------ 空力
    IDLE_CD = 0.15         # アイドル時の風車ブレーキ（プロペラの空転抗力）
    #  0.15 なら 60kt/-900fpm でも -0.60 m/s^2 で減速する（0.058 だと +0.19 で加速）

    def _aero(self):
        flap_cd = self.flap * 0.0012
        a = self.alpha
        a_st = self.stall_alpha
        cl = (self.CL0 + self.CLA * a + self.flap_cl) * self.dmg_lift
        if a > a_st:                               # 失速: 揚力が崩れる
            cl = max(0.34, cl - (a - a_st) * 7.0)
        cl = clamp(cl, -1.2, 2.1)
        # 失速後は流れが剥離して抗力が急増する（これが無いと降下で加速し続ける）
        sep = max(0.0, a - a_st) * 1.15
        # スロットルを絞るとプロペラが空転してブレーキになる
        idle = self.IDLE_CD * max(0.0, 1.0 - self.throttle * self.engine * 6.0)
        if self.engine <= 0.01:
            idle *= 0.28        # 止まったプロペラは空転するより抵抗が小さい
        q = 0.5 * RHO * self.V * self.V
        lift = q * self.WING * cl
        drag = q * self.WING * (self.CD0 + self.dmg_drag
                                + self.K * cl * cl + flap_cd + sep + idle)
        thrust = (self.THRUST * self.throttle * self.engine * self.dmg_power
                  * max(0.25, 1.0 - self.V / 115.0))
        return lift, drag, thrust

    # ------------------------------------------------------------ 更新
    def step(self, dt, wind=(0.0, 0.0)):
        if self.msg_t > 0:
            self.msg_t -= 1
        v0 = self.V
        lift, drag, thrust = self._aero()
        if self.on_ground:
            self._step_ground(dt, lift, drag, thrust)
        else:
            self._step_air(dt, lift, drag, thrust)
        self._move(dt, (0.0, 0.0) if self.on_ground else wind)
        # 減速すると前のめりになり、止まると水平に戻る（脚の沈み込み）
        self.accel = (self.V - v0) / dt
        tgt = 0.0
        if self.on_ground and self.V > 0.3:
            tgt = clamp(self.accel * 0.55, -4.0, 0.9)
        self.dip += (tgt - self.dip) * min(1.0, 7.0 * dt)

    def _rate(self, dt, auth):
        """舵の指示へ角速度を一次遅れで寄せる。これが慣性の手ざわりになる。"""
        tq = self.elevator * math.radians(PITCH_RATE) * auth
        tp = self.aileron * math.radians(ROLL_RATE) * auth
        tr = self.rudder * math.radians(YAW_RATE) * auth
        self.q_rate += (tq - self.q_rate) * min(1.0, dt / TAU_PITCH)
        self.p_rate += (tp - self.p_rate) * min(1.0, dt / TAU_ROLL)
        self.r_rate += (tr - self.r_rate) * min(1.0, dt / TAU_YAW)

    def _step_ground(self, dt, lift, drag, thrust):
        load = max(0.0, self.MASS * G - lift)
        fric = (0.42 * self.dmg_brake if self.brake else 0.025) * load
        self.V = max(0.0, self.V + ((thrust - drag - fric) / self.MASS) * dt)
        # 機首上げは尾部接触の手前で止める
        self.pitch += self.elevator * math.radians(PITCH_RATE * 0.85) * dt \
            * min(1.0, self.V / 18.0)
        self.pitch = clamp(self.pitch, math.radians(-1), math.radians(11))
        self.roll += (0.0 - self.roll) * 8.0 * dt
        self.gamma = 0.0
        # 地上操向（低速は前輪、高速は方向舵）
        self.hdg += self.rudder * clamp(self.V / 22.0, 0.0, 1.4) * 0.55 * dt
        if lift > self.MASS * G and self.V > 16.0:
            self.on_ground = False
            self.gamma = math.radians(0.5)
            self._say('AIRBORNE')

    def _step_air(self, dt, lift, drag, thrust):
        v = max(6.0, self.V)
        auth = min(1.0, v / 34.0)                  # 低速では舵が効かない
        # 舵は「目標の角速度」を決めるだけ。実際の角速度は慣性で遅れて追う
        self._rate(dt, auth)
        self.pitch += self.q_rate * dt
        self.roll += self.p_rate * dt
        self.hdg += self.r_rate * dt
        # 失速すると機首が自然に落ちる（ストールブレイク）。
        # これが無いと舵を引いたまま深い迎角で落ち続けて回復できない。
        over = self.alpha - self.stall_alpha
        if over > 0.0:
            self.pitch -= min(over, 0.35) * 2.2 * dt
        # 静安定: 舵を放すとトリム迎角へ戻る
        if abs(self.elevator) < 0.01:
            target = self.gamma + self.trim
            self.pitch += (target - self.pitch) * 0.9 * dt
        if abs(self.aileron) < 0.01:
            self.roll += (0.0 - self.roll) * 0.117 * dt
        self.pitch = clamp(self.pitch, math.radians(-35), math.radians(35))
        self.roll = clamp(self.roll, math.radians(-70), math.radians(70))

        self.V += ((thrust - drag) / self.MASS - G * math.sin(self.gamma)) * dt
        self.V = clamp(self.V, 8.0, self.VNE * 1.25)
        # 経路角と旋回（揚力の鉛直成分と水平成分）
        dgam = (lift * math.cos(self.roll) - self.MASS * G * math.cos(self.gamma)) \
            / (self.MASS * v)
        self.gamma = clamp(self.gamma + dgam * dt, math.radians(-45), math.radians(45))
        self.hdg += (lift * math.sin(self.roll)
                     / (self.MASS * v * max(0.25, math.cos(self.gamma)))) * dt
        self.alt += self.V * math.sin(self.gamma) * dt
        if self.alt <= 0.0:
            self._touchdown()

    def _touchdown(self):
        vs = self.V * math.sin(self.gamma)
        self.touchdown_vs = vs
        self.alt = 0.0
        self.gamma = 0.0
        self.on_ground = True
        self.pitch = clamp(self.pitch, math.radians(-1), math.radians(11))
        wing = abs(math.degrees(self.roll)) > 14.0
        grade = ('WINGTIP STRIKE' if wing else
                 'HARD' if vs < -3.0 else 'FIRM' if vs < -1.5 else 'SMOOTH')
        ap = world.nearest_airport(self.x, self.y)
        if ap.axis == 'NS':
            lateral, along = self.x - ap.c, self.y
        else:
            lateral, along = self.y - ap.c, self.x
        on_rwy = abs(lateral) <= ap.HALF and ap.a0 <= along <= ap.a1
        zone = min(along - ap.a0, ap.a1 - along) * UNIT if on_rwy else 0.0
        self.last_landing = _score_landing(ap.name, grade, vs, zone,
                                           lateral * UNIT, on_rwy, wing)
        if on_rwy:
            self._say('%s %.1f M/S  %s TD %dM  %d PTS'
                      % (grade, vs, ap.name, zone, self.last_landing['score']), 260)
        else:
            self._say('%s %.1f M/S  OFF RUNWAY' % (grade, vs), 260)
        self.roll = 0.0

    EDGE_WARN = 260.0       # この距離まで近づくと警告
    EDGE_HARD = 40.0

    def _move(self, dt, wind=(0.0, 0.0)):
        # 機体は空気の塊ごと流される。対気速度は変わらず、対地の軌跡だけずれる。
        gs = self.V * math.cos(self.gamma)              # m/s
        vx = gs * math.sin(self.hdg) + wind[0]
        vy = gs * math.cos(self.hdg) + wind[1]
        self.x += vx / UNIT * dt
        self.y += vy / UNIT * dt
        W = float(world.WORLD)
        self.x = clamp(self.x, self.EDGE_HARD, W - self.EDGE_HARD)
        self.y = clamp(self.y, self.EDGE_HARD, W - self.EDGE_HARD)
        self.edge = min(self.x, self.y, W - self.x, W - self.y)

    @property
    def near_edge(self):
        """空域端までの余裕 0..1（0が端）。地図が256ユニット四方しかないため。"""
        e = getattr(self, 'edge', 1e4)
        return clamp((e - self.EDGE_HARD) / self.EDGE_WARN, 0.0, 1.0)

    def edge_bearing(self):
        """空域中心へ戻る方位[deg]。"""
        c = world.WORLD * 0.5
        return math.degrees(math.atan2(c - self.x, c - self.y)) % 360.0

    # ------------------------------------------------------------ 操作
    def set_flap(self, d):
        i = clamp(self.flap_i + d, 0, len(FLAP_STEPS) - 1)
        if i != self.flap_i:
            self.flap_i = int(i)
            self._say('FLAP %d' % self.flap, 80)

    def add_throttle(self, d):
        self.throttle = clamp(self.throttle + d, 0.0, 1.0)

    TRIM_LO = math.radians(-8)
    TRIM_HI = math.radians(12)

    def add_trim(self, d):
        self.trim = clamp(self.trim + d, self.TRIM_LO, self.TRIM_HI)
