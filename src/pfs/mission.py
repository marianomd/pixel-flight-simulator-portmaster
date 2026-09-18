"""仕事（ミッション）。空港ごとのジョブボードから受けて、こなすと稼げる。

種類ごとに「求められる飛び方」が違うのがねらい。貨物は速さ、旅客は滑らかさ、
測量は高度の正確さ、というように評価軸を変えてある。
"""
import math
import random

import fleet
import lang
import world

UNIT = 8.0                  # 1ユニット = 8m
KIND_FERRY = 'FERRY'
KIND_CARGO = 'CARGO'
KIND_PAX = 'PAX'
KIND_TOUR = 'TOUR'
KIND_SURVEY = 'SURVEY'
KIND_SEARCH = 'SEARCH'

TITLES = {KIND_FERRY: 'FERRY FLIGHT', KIND_CARGO: 'CARGO', KIND_PAX: 'PASSENGERS',
          KIND_TOUR: 'SIGHTSEEING', KIND_SURVEY: 'AERIAL SURVEY',
          KIND_SEARCH: 'SEARCH AND RESCUE'}

CRUISE_UPS = 5.6            # 見込みの対地速度[ユニット/秒]
# 実測で校正した見積り: 離着陸の固定費 + 経路長 / 巡航
# CENTRAL-NORTH 5.7km で6.0分、NORTH-WEST 11.7km で7.5分だった
FIXED_MIN = 4.3             # 離陸・上昇・進入・着陸にかかる分
KM_PER_MIN = 3.4            # 巡航での進み方[km/分]
MAX_MIN = 9.0               # 1回の仕事はここに収める
TOUR_ALT = 500.0            # 遊覧はこの高度[m]以下で通ること
# 測量の高度の許容差[m]。100ftだと横の追従と同時にこなすのが厳しく、
# 一度外すと入口から取り直しに見えて難度が跳ね上がっていた
SURVEY_TOL = 45.0           # 約150ft
SURVEY_LAT = 12.0           # 測線からの横の許容差[ユニット]（約96m）
SURVEY_SEG = 20             # 測線をこれだけの区画に分けて、通った区画を数える
SURVEY_MIN = 0.50           # これだけ撮れていないと持ち帰れない
# 測量の指定高度[m]。低空の写真測量なので高くしない
SURVEY_ALTS = (120.0, 160.0, 200.0, 240.0)
SEARCH_R = 4.0              # 目標に近づいたと見なす距離[ユニット]
# 救助者を目視できる高度[m]。測量と同じ150ftにすると地面が近すぎるので、
# 余裕を見て300ft。煙は巡航高度からでも見えるので「見つけて降りる」流れになる
SEARCH_ALT = 300.0 / 3.28084
SEARCH_AREA = 70.0          # 捜索範囲の半径[ユニット]（約560m）
# 煙が見えはじめる距離。捜索範囲の半径と同じにしてあるので、輪の中心まで
# 行けば必ず視界に入る（目標は中心から85%以内に置かれる）。輪の外からは見えない
SEARCH_SEE = 70.0
TOUR_R = 26.0               # 見どころに到達したと見なす距離[ユニット]
# 目印は白と赤の交互。単色だとどこかの時刻の空と同化する
MARK_A, MARK_B = 12, 13
# 発煙。直線だと輪の罫線と見分けがつかず「中心線」に見えてしまうので、
# 玉が立ちのぼって膨らみながら薄れる形にする。巡航高度からも見えるよう高く
SMOKE_H = 30.0              # 立ちのぼる高さ[ユニット]（約240m）
SMOKE_N = 9                 # 同時に見えている玉の数
SMOKE_DRIFT = 9.0           # 風下へ流れる量[ユニット]（無風なら0）
SMOKE_RISE = 0.20           # 1秒あたり何割ぶん昇るか
MARK_DONE = 11              # 済んだものは緑
BOARD_N = 4                 # ジョブボードに並ぶ件数
PAX_KG = 80                 # 乗客1人ぶんの重さ
TOUR_KG = 160               # 遊覧で乗せる客の重さ

# 仕事が出はじめるレベル。簡単なものから順に増えていく
UNLOCK_LV = {KIND_FERRY: 1, KIND_CARGO: 1, KIND_PAX: 3,
             KIND_TOUR: 5, KIND_SURVEY: 8, KIND_SEARCH: 12}
# 難度。上の段ほど報酬が上がり、制限時間が厳しく、積荷が重くなる
TIER_NAME = ('', 'STANDARD', 'RUSH', 'CRITICAL')
TIER_PAY = (0.0, 1.0, 1.45, 2.0)
TIER_TIME = (0.0, 1.0, 0.55, 0.30)   # 見込みに対する「余裕」の残し方
TIER_LOAD = (0.0, 1.0, 1.25, 1.55)
# 報酬の全体倍率。1フライトあたり約1000CRは稼ぎすぎだったので絞る
PAY_SCALE = 0.70
# 経験値。1分あたり4に、種類ごとの上乗せを足す。
# 回送(FERRY)は報酬が安いかわりに経験値が飛び抜けて高い＝飛行時間を稼ぐ仕事。
XP_PER_MIN = 4.0
XP_BONUS = {KIND_FERRY: 42, KIND_CARGO: 4, KIND_PAX: 8,
            KIND_TOUR: 10, KIND_SURVEY: 14, KIND_SEARCH: 18}


def _km(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]) * UNIT / 1000.0


class Job:
    """1件の仕事。受注してから完了までの状態も持つ。"""

    def __init__(self, kind, origin, dest, pay, limit, payload=0,
                 targets=(), alt=0.0, note='', area=None):
        self.kind = kind
        self.origin = origin        # 出発空港の名前
        self.dest = dest            # 到着空港（world.Airport）。Noneなら出発地へ戻る
        self.pay = int(pay)
        self.limit = float(limit)   # 0なら制限なし
        self.payload = int(payload)
        self.targets = list(targets)   # 遊覧・捜索の目標 [(x, y, 名前)]
        self.alt = alt              # 測量の指定高度[m]
        self.note = note
        self.area = area            # 捜索範囲 (x, y, 半径)
        self.est = 0.0              # 離陸から着陸までの見込み[分]
        self.tier = 1               # 難度 1..3
        self.xp = 0                 # 完了時にもらえる経験値
        # 進行
        self.t = 0.0
        self.hit = [False] * len(self.targets)
        self.quality = 1.0          # 出来ばえ（旅客の滑らかさ、測量の精度）
        self.rough = 0.0
        self.cover = [False] * SURVEY_SEG   # 測れた区画。進み具合そのもの
        self.on_line = False        # いま測線の上か（表示に使う）
        self.alt_err = 0.0          # 指定高度からのずれ[m]
        self.high = False           # 捜索: 煙は見えているが高すぎる

    # ------------------------------------------------------------ 表示
    def title(self):
        if self.tier > 1:
            return '%s %s' % (TIER_NAME[self.tier], TITLES[self.kind])
        return TITLES[self.kind]

    def title_t(self):
        """訳した題名。「RUSH CARGO」のまま引くと辞書に無いので、分けて訳す。"""
        t = lang.T(TITLES[self.kind])
        if self.tier > 1:
            return '%s %s' % (lang.T(TIER_NAME[self.tier]), t)
        return t

    def where(self):
        if self.dest is not None:
            return self.dest.name
        return self.origin

    @staticmethod
    def _place(name, short=False):
        """行き先の表示名。空港は「空港」と分かる形にして方角と区別する。"""
        if not world.is_airport(name):
            return name
        if short and lang.lang == lang.EN:
            return world.apt_short(name)          # 英語は幅が足りないので略す
        return lang.T('%s AIRPORT') % name

    def summary(self):
        if self.kind == KIND_TOUR:
            return '%d SIGHTS, TO %s' % (len(self.targets),
                                         world.apt_short(self.origin))
        if self.kind == KIND_SURVEY:
            return 'LINE AT %d FT' % round(self.alt * 3.28084)
        if self.kind == KIND_SEARCH:
            return 'SEARCH, LAND %s' % world.apt_short(self.where())
        if self.payload:
            return 'TO %s  %d KG' % (world.apt_short(self.where()), self.payload)
        return 'TO %s' % world.apt_short(self.where())

    def summary_t(self):
        """訳した概要。空港名は固有名詞なのでそのまま残す。"""
        if self.kind == KIND_TOUR:
            return lang.T('%d SIGHTS, TO %s') % (
                len(self.targets), self._place(self.origin, True))
        if self.kind == KIND_SURVEY:
            return lang.T('LINE AT %d FT') % round(self.alt * 3.28084)
        if self.kind == KIND_SEARCH:
            return lang.T('SEARCH, LAND %s') % self._place(self.where(), True)
        if self.payload:
            return lang.T('TO %s  %d KG') % (self._place(self.where()),
                                             self.payload)
        return lang.T('TO %s') % self._place(self.where())

    def left(self):
        return max(0.0, self.limit - self.t) if self.limit else 0.0

    def status_line(self, with_time=True):
        """HUDと計器盤で共通に使う一行。進み具合と残り時間。"""
        if self.kind == KIND_TOUR:
            s = 'TOUR %d/%d' % (self.done_count(), len(self.targets))
        elif self.kind == KIND_SURVEY:
            s = 'SURVEY %d%%' % round(self.progress() * 100)
            if self.on_line:
                # 測線の上に居るあいだは、目標高度ではなく「ずれ」を出す
                s += ('  ON ALT' if abs(self.alt_err) <= SURVEY_TOL
                      else '  %+d FT' % round(self.alt_err * 3.28084))
            else:
                s += '  %d FT' % round(self.alt * 3.28084)
        elif self.kind == KIND_SEARCH:
            if self.hit[0]:
                s = 'FOUND - LAND %s' % world.apt_short(self.where())
            elif self.high:
                # 何をすればいいか出さないと、旋回し続けることになる
                s = 'SEARCH  DESCEND %d FT' % round(SEARCH_ALT * 3.28084)
            else:
                s = 'SEARCH'
        elif self.kind == KIND_PAX:
            s = 'PAX  RIDE %d%%' % round(self.quality * 100)
        else:
            s = '%s %s' % (self.kind, world.apt_short(self.where()))
        if with_time and self.limit:
            t = self.left()
            s += '  %d:%02d' % (int(t) // 60, int(t) % 60)
        return s

    def urgent(self):
        return bool(self.limit) and self.left() < 45.0

    def done_count(self):
        return sum(1 for h in self.hit if h)

    # ------------------------------------------------------------ 進行
    def update(self, ac, dt):
        self.t += dt
        if self.kind == KIND_PAX:
            self._comfort(ac, dt)
        elif self.kind == KIND_TOUR:
            self._sights(ac)
        elif self.kind == KIND_SURVEY:
            self._survey(ac, dt)
        elif self.kind == KIND_SEARCH:
            self._search(ac)

    def _comfort(self, ac, dt):
        """旅客は滑らかさが商品。深いバンクと荒い上下動で乗り心地が落ちる。"""
        if ac.on_ground:
            return
        bank = abs(math.degrees(ac.roll))
        vs = abs(ac.vs_fpm)
        self.rough += max(0.0, bank - 22.0) * 0.010 * dt
        self.rough += max(0.0, vs - 900.0) * 0.0009 * dt
        self.quality = max(0.35, 1.0 - self.rough * 0.02)

    def _sights(self, ac):
        if ac.on_ground or ac.alt > TOUR_ALT:
            return
        for i, (tx, ty, _n) in enumerate(self.targets):
            if not self.hit[i] and math.hypot(tx - ac.x, ty - ac.y) < TOUR_R:
                self.hit[i] = True
                return

    def _survey(self, ac, dt):
        """測線を区画に分け、正しい高度で通れた区画を数える。

        以前は「線の上に居た時間のうち、高度が合っていた割合」だった。
        表示が100%から始まって減るだけなので進み具合が分からず、しかも
        一度も飛ばずに着陸すると満額もらえてしまっていた。
        通った区画を数える形にすると、0%から積み上がる素直な進み具合になる。
        向きはどちらからでもよく、抜けた区画だけ飛び直せる。
        """
        self.on_line = False
        if ac.on_ground or len(self.targets) < 2:
            return
        (ax, ay, _), (bx, by, _) = self.targets[0], self.targets[1]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy) or 1.0
        t = ((ac.x - ax) * dx + (ac.y - ay) * dy) / (ln * ln)
        if not (0.0 <= t <= 1.0):
            return
        if abs((ac.x - ax) * dy - (ac.y - ay) * dx) / ln > SURVEY_LAT:
            return                           # 線から離れすぎ
        # 線の上に居ることと、高度が合っていることは分けて持つ。
        # 「いま何ft外している」を出せないと、直しようがない
        self.on_line = True
        self.alt_err = ac.alt - self.alt
        if abs(self.alt_err) > SURVEY_TOL:
            return
        self.cover[min(SURVEY_SEG - 1, int(t * SURVEY_SEG))] = True
        self.quality = self.progress()

    def progress(self):
        """測量の進み具合 0..1。"""
        return sum(1.0 for c in self.cover if c) / float(SURVEY_SEG)

    def seg_pt(self, i):
        """区画 i の中点。まだ撮れていない場所を指すのに使う。"""
        (ax, ay, _), (bx, by, _) = self.targets[0], self.targets[1]
        f = (i + 0.5) / SURVEY_SEG
        return ax + (bx - ax) * f, ay + (by - ay) * f

    def _search(self, ac):
        """煙まで寄って、目視できる高度まで降りたら発見。"""
        self.high = False
        if ac.on_ground or not self.targets or self.hit[0]:
            return
        tx, ty, _n = self.targets[0]
        d = math.hypot(tx - ac.x, ty - ac.y)
        low = ac.alt <= SEARCH_ALT
        if d < SEARCH_SEE and not low:
            self.high = True            # 煙は見えているのに高すぎる
        if d < SEARCH_R and low:
            self.hit[0] = True

    # ------------------------------------------------------------ 航法と目印
    def nav_target(self):
        """いま向かうべき場所。(名前, x, y) か None。"""
        if self.kind == KIND_TOUR:
            for i, (tx, ty, nm) in enumerate(self.targets):
                if not self.hit[i]:
                    return (nm, tx, ty)
            return (self.origin, None, None)
        if self.kind == KIND_SEARCH:
            if not self.hit[0] and self.area:
                return ('SEARCH', self.area[0], self.area[1])
            return (self.where(), None, None)
        if self.kind == KIND_SURVEY:
            if self.targets and not all(self.cover):
                i = next(k for k, c in enumerate(self.cover) if not c)
                tx, ty = self.seg_pt(i)
                return ('SURVEY', tx, ty)
            return (self.where(), None, None)
        return (self.where(), None, None)

    def draw(self, pr, cam, wind=None, t=0.0):
        """ワールドに目印を描く。まだの目標は琥珀、済んだものは緑。"""
        import pyxel
        if self.kind == KIND_SEARCH and self.area and not self.hit[0]:
            self._ring(pr, self.area[0], self.area[1], self.area[2], None, 22)
            tx, ty, _n = self.targets[0]
            if math.hypot(tx - cam[0], ty - cam[1]) < SEARCH_SEE:
                self._smoke(pr, tx, ty, t, wind)        # 目標の発煙
            return
        if self.kind == KIND_SURVEY and len(self.targets) >= 2:
            (ax, ay, _), (bx, by, _) = self.targets[0], self.targets[1]
            n = SURVEY_SEG
            for k in range(n):
                p = pr.pt(ax + (bx - ax) * k / n, ay + (by - ay) * k / n,
                          self.alt / UNIT)
                q = pr.pt(ax + (bx - ax) * (k + 1) / n,
                          ay + (by - ay) * (k + 1) / n, self.alt / UNIT)
                if p and q and (pr.on_screen(p) or pr.on_screen(q)):
                    # 撮れた区画は緑。残りがそのまま見えるので飛び直しやすい
                    col = (MARK_DONE if self.cover[k]
                           else (MARK_A if k % 2 == 0 else MARK_B))
                    pyxel.line(p[0], p[1], q[0], q[1], col)
            # 両端に門を立てる。大きさは採点の許容範囲そのものなので、
            # くぐれていれば点が入っている
            hdg = math.atan2(bx - ax, by - ay)
            done = self.ready()
            self._gate(pr, ax, ay, self.alt / UNIT, hdg,
                       MARK_DONE if done else None)
            self._gate(pr, bx, by, self.alt / UNIT, hdg,
                       MARK_DONE if done else None)
            return
        if self.kind == KIND_TOUR:
            for i, (tx, ty, _n) in enumerate(self.targets):
                col = MARK_DONE if self.hit[i] else None
                self._ring(pr, tx, ty, TOUR_R, col, 16)
                self._pillar(pr, tx, ty, col or MARK_A, 14.0)

    @staticmethod
    def _seg_col(col, k):
        """col が None なら白と赤の交互。指定があればその色。"""
        if col is not None:
            return col
        return MARK_A if (k // 2) % 2 == 0 else MARK_B

    @staticmethod
    def _gate(pr, cx, cy, cz, hdg, col, seg=18):
        """測線に直交する門。横12ユニット・上下は高度の許容差ぶん。"""
        import pyxel
        ux, uy = math.cos(hdg), -math.sin(hdg)          # 測線に直交する水平方向
        hw, hh = 12.0, SURVEY_TOL / UNIT
        pts = []
        for k in range(seg):
            a = k / seg * math.tau
            pts.append(pr.pt(cx + ux * hw * math.cos(a),
                             cy + uy * hw * math.cos(a),
                             cz + hh * math.sin(a)))
        for k in range(seg):
            p, q = pts[k], pts[(k + 1) % seg]
            if p and q and (pr.on_screen(p) or pr.on_screen(q)):
                pyxel.line(p[0], p[1], q[0], q[1], Job._seg_col(col, k))
        # 地面まで柱を下ろして、遠くからでも位置が分かるようにする
        a = pr.pt(cx, cy, 0.05)
        b = pr.pt(cx, cy, cz - hh)
        if a and b and (pr.on_screen(a) or pr.on_screen(b)):
            pyxel.line(a[0], a[1], b[0], b[1], col or MARK_A)

    @staticmethod
    def _ring(pr, cx, cy, r, col, seg):
        import pyxel
        pts = []
        for k in range(seg):
            a = k / seg * math.tau
            pts.append(pr.pt(cx + math.cos(a) * r, cy + math.sin(a) * r, 0.05))
        for k in range(seg):
            p, q = pts[k], pts[(k + 1) % seg]
            if p and q and (pr.on_screen(p) or pr.on_screen(q)):
                pyxel.line(p[0], p[1], q[0], q[1], Job._seg_col(col, k))

    @staticmethod
    def _smoke(pr, x, y, t, wind=None):
        """発煙。根元は炎の色、昇るほど白く薄くなる。

        風があれば風下へ寝る。動くものは地形の模様に紛れないので、
        「そこだけ別物」だとひと目で分かる。
        """
        import pyxel
        drift = 0.0
        sd, cd = 0.0, 1.0
        if wind and wind[1] > 0.5:
            a = math.radians(wind[0] + 180.0)      # 吹いてくる向き -> 流れる向き
            sd, cd = math.sin(a), math.cos(a)
            drift = min(1.0, wind[1] / 25.0) * SMOKE_DRIFT
        for i in range(SMOKE_N):
            f = (t * SMOKE_RISE + i / float(SMOKE_N)) % 1.0   # 0=根元 1=消える
            d = f * f * drift
            p = pr.pt(x + sd * d, y + cd * d, 0.05 + f * SMOKE_H)
            if not pr.on_screen(p, 20):
                continue
            rad = pr.f * (0.7 + f * 3.6) / p[2]
            if f < 0.12:
                pyxel.dither(1.0)
                col = MARK_B                       # 根元は炎
            else:
                pyxel.dither(max(0.25, 1.0 - f))   # 昇るほど薄れる
                col = MARK_A
            if rad < 0.9:
                pyxel.pset(p[0], p[1], col)
            else:
                pyxel.circ(p[0], p[1], min(rad, 14.0), col)
        pyxel.dither(1.0)

    @staticmethod
    def _pillar(pr, x, y, col, h):
        import pyxel
        a = pr.pt(x, y, 0.05)
        b = pr.pt(x, y, h)
        if a and b and (pr.on_screen(a) or pr.on_screen(b)):
            pyxel.line(a[0], a[1], b[0], b[1], col)

    # ------------------------------------------------------------ 判定
    def ready(self):
        """着陸すれば完了になる状態か。"""
        if self.kind in (KIND_TOUR, KIND_SEARCH):
            return all(self.hit)
        if self.kind == KIND_SURVEY:
            return self.progress() >= SURVEY_MIN
        return True

    def timed_out(self):
        return bool(self.limit) and self.t > self.limit

    def check_landing(self, result):
        """着陸したときの判定。(完了したか, 報酬, 一言) を返す。"""
        if not result['on_rwy']:
            return False, 0, 'MISSED THE RUNWAY'
        if self.dest is not None and result['apt'] != self.dest.name:
            return False, 0, ''            # 目的地ではない。まだ続く
        if self.dest is None and result['apt'] != self.origin:
            return False, 0, ''
        if not self.ready():
            return False, 0, 'NOT FINISHED YET'
        q = self.quality
        if self.kind == KIND_PAX:
            # 接地の衝撃も乗り心地のうち
            q *= max(0.4, 1.0 - max(0.0, abs(result['vs']) - 1.5) * 0.22)
        if self.kind == KIND_TOUR:
            q = self.done_count() / max(1, len(self.targets))
        if self.kind == KIND_SURVEY:
            q = self.progress()          # 撮れた区画のぶんだけ払う
        pay = int(self.pay * q)
        if self.limit and self.t > self.limit:
            pay = int(pay * 0.5)
            return True, pay, 'LATE - HALF PAY'
        note = ''
        if self.kind in (KIND_PAX, KIND_SURVEY):
            note = '  QUALITY %d%%' % round(q * 100)
        return True, pay, note


def job_to_dict(j):
    return {'kind': j.kind, 'origin': j.origin,
            'dest': j.dest.name if j.dest is not None else None,
            'pay': j.pay, 'limit': j.limit, 'payload': j.payload,
            'targets': [list(t) for t in j.targets], 'alt': j.alt, 'xp': j.xp,
            'area': list(j.area) if j.area else None, 'est': j.est,
            't': j.t, 'hit': j.hit, 'quality': j.quality, 'rough': j.rough,
            'cover': [1 if c else 0 for c in j.cover]}


def job_from_dict(d):
    if not d:
        return None
    dest = next((a for a in world.AIRPORTS if a.name == d.get('dest')), None)
    j = Job(d['kind'], d['origin'], dest, d['pay'], d['limit'],
            payload=d.get('payload', 0),
            targets=[tuple(t) for t in (d.get('targets') or [])],
            alt=d.get('alt', 0.0),
            area=tuple(d['area']) if d.get('area') else None)
    j.est = d.get('est', 0.0)
    j.xp = d.get('xp', 0)
    j.t = d.get('t', 0.0)
    hit = d.get('hit') or []
    j.hit = [bool(h) for h in hit] + [False] * (len(j.targets) - len(hit))
    j.quality = d.get('quality', 1.0)
    j.rough = d.get('rough', 0.0)
    cov = d.get('cover') or []
    j.cover = [bool(cov[i]) if i < len(cov) else False for i in range(SURVEY_SEG)]
    return j


# ------------------------------------------------------------------ 生成
def est_minutes(route_units):
    """経路長[ユニット]から、離陸から着陸までの見込み時間[分]。"""
    return FIXED_MIN + route_units * UNIT / 1000.0 / KM_PER_MIN


def _max_route():
    """9分に収まる経路長[ユニット]。"""
    return (MAX_MIN - FIXED_MIN) * KM_PER_MIN * 1000.0 / UNIT


def _route_len(start, targets):
    """近い順にたどったときの経路長[ユニット]。最後は出発地へ戻る。"""
    left = [(t[0], t[1]) for t in targets]
    x, y = start
    total = 0.0
    while left:
        i = min(range(len(left)),
                key=lambda k: (left[k][0] - x) ** 2 + (left[k][1] - y) ** 2)
        tx, ty = left.pop(i)
        total += math.hypot(tx - x, ty - y)
        x, y = tx, ty
    return total + math.hypot(start[0] - x, start[1] - y)


def _airports_from(here):
    return [a for a in world.AIRPORTS if a.name != here.name]


def _with_est(job, route, tier=1, cap=None):
    """見込み時間を入れ、難度に応じて報酬・制限・積荷を調整する。"""
    job.est = est_minutes(route)
    job.tier = tier
    job.pay = int(job.pay * PAY_SCALE)
    job.xp = int(round(job.est * XP_PER_MIN + XP_BONUS.get(job.kind, 0)))
    if tier > 1:
        job.pay = int(job.pay * TIER_PAY[tier])
        job.xp = int(job.xp * TIER_PAY[tier])
        if job.limit:
            # 制限を単純に短くすると見込みを下回って達成不能になる。
            # 見込みからの「余裕」だけを削る
            base = job.est * 60.0
            job.limit = base + max(0.0, job.limit - base) * TIER_TIME[tier]
        if job.payload:
            job.payload = int(job.payload * TIER_LOAD[tier])
            if cap:
                job.payload = min(job.payload, int(cap))
    return job


def pick_tier(level, rnd, trust=0.0):
    """レベルが上がるほど難しい仕事が混じる。LV9でRUSH、LV18でCRITICAL。

    trust は顧客信頼のスキル 0..1。上の難度へ寄せる確率になる。
    腕を買われて重い仕事を任される、という筋になる。
    """
    top = 1 + (level >= 9) + (level >= 18)
    t = rnd.randrange(1, top + 1)
    while t < top and rnd.random() < trust:
        t += 1
    return t


def make_job(kind, here, cap, rnd, tier=1, dest=None):
    """指定の種類の仕事を1件作る。cap は機体の積載量[kg]。"""
    others = _airports_from(here)
    if dest is None:
        dest = rnd.choice(others) if others else here
    d = _km((here.x, here.y), (dest.x, dest.y))
    fly = d * 1000.0 / UNIT / CRUISE_UPS          # 巡航にかかる秒
    route = d * 1000.0 / UNIT
    if kind == KIND_FERRY:
        return _with_est(Job(kind, here.name, dest, d * 38.0, 0.0), route, 1, cap)
    if kind == KIND_CARGO:
        load = rnd.randrange(40, max(60, cap), 20)
        return _with_est(Job(kind, here.name, dest, d * 38.0 + load * 1.2,
                             est_minutes(route) * 60.0 * 1.35, payload=load), route, tier, cap)
    if kind == KIND_PAX:
        # 乗せられる人数は積載量で決まる。超える仕事を出すと受けられない
        room = max(1, min(3, int(cap // PAX_KG)))
        pax = rnd.randrange(1, room + 1)
        return _with_est(Job(kind, here.name, dest, d * 42.0 + pax * 160.0,
                             est_minutes(route) * 60.0 * 1.45,
                             payload=pax * PAX_KG), route, tier, cap)
    if kind == KIND_TOUR:
        # 出発地に近い見どころから選び、経路が長すぎたら減らす。
        # 遠くを引くと1回の飛行が10分を超えて、遊ぶテンポが悪くなる。
        near = sorted(world.LANDMARKS,
                      key=lambda l: (l.x - here.x) ** 2 + (l.y - here.y) ** 2)[:5]
        n = min(rnd.randrange(2, 4), len(near))
        lm = rnd.sample(near, n)
        tg = [(l.x, l.y, l.name) for l in lm]
        route = _route_len((here.x, here.y), tg)
        while len(tg) > 1 and route > _max_route():
            far = max(range(len(tg)),
                      key=lambda i: (tg[i][0] - here.x) ** 2 + (tg[i][1] - here.y) ** 2)
            tg.pop(far)
            route = _route_len((here.x, here.y), tg)
        return _with_est(Job(kind, here.name, None, 150.0 + route * 0.47,
                             est_minutes(route) * 60.0 * 1.35,
                             payload=min(TOUR_KG, max(PAX_KG,
                                         int(cap // PAX_KG) * PAX_KG),),
                             targets=tg), route, tier, cap)
    if kind == KIND_SURVEY:
        # 測線は出発地の近くに引く。見どころ基準にすると空港から遠いことがあり、
        # 往復だけで時間を使ってしまう。
        # ただし近すぎると指定高度まで上がりきれないので、
        # 高度に応じて距離をとる（滑走233m + 上昇勾配0.118 + 余裕30%）。
        alt = rnd.choice(SURVEY_ALTS)
        a0 = rnd.uniform(0.0, math.tau)
        # 勾配は0.09で見る（最良上昇率0.118はぴったり飛べたときの値なので、
        # 実際に操縦する余裕を見て緩めにとる）
        need = (233.0 + alt / 0.09) / UNIT * 1.5
        r0 = min(560.0, max(110.0, need)) * rnd.uniform(1.0, 1.15)
        ax = min(max(here.x + math.sin(a0) * r0, 80.0), world.WORLD - 80.0)
        ay = min(max(here.y + math.cos(a0) * r0, 80.0), world.WORLD - 80.0)
        near = min(world.LANDMARKS,
                   key=lambda l: (l.x - ax) ** 2 + (l.y - ay) ** 2)
        a = type('P', (), {'x': ax, 'y': ay, 'name': near.name})
        ang = rnd.uniform(0.0, math.tau)
        ln = rnd.uniform(120.0, 200.0)
        bx = min(max(a.x + math.sin(ang) * ln, 80.0), world.WORLD - 80.0)
        by = min(max(a.y + math.cos(ang) * ln, 80.0), world.WORLD - 80.0)
        route = (math.hypot(a.x - here.x, a.y - here.y) + ln
                 + math.hypot(bx - here.x, by - here.y))
        return _with_est(Job(kind, here.name, here, 950.0,
                             est_minutes(route) * 60.0 * 1.4,
                             targets=[(a.x, a.y, a.name), (bx, by, 'END')],
                             alt=alt), route, tier, cap)
    if kind == KIND_SEARCH:
        ang = rnd.uniform(0.0, math.tau)
        r = rnd.uniform(150.0, 320.0)
        cx = min(max(here.x + math.sin(ang) * r, 90.0), world.WORLD - 90.0)
        cy = min(max(here.y + math.cos(ang) * r, 90.0), world.WORLD - 90.0)
        # 目標は捜索範囲のどこか。近づかないと煙は見えない
        a2 = rnd.uniform(0.0, math.tau)
        r2 = rnd.uniform(0.0, SEARCH_AREA * 0.85)
        tx, ty = cx + math.sin(a2) * r2, cy + math.cos(a2) * r2
        route = math.hypot(cx - here.x, cy - here.y) * 2.0 + 120.0
        return _with_est(Job(kind, here.name, here, 1150.0,
                             est_minutes(route) * 60.0 * 1.5,
                             targets=[(tx, ty, 'TARGET')],
                             area=(cx, cy, SEARCH_AREA)), route, tier, cap)
    return None


class Board:
    """空港ごとの仕事の一覧。その空港にいるときだけ受けられる。"""

    POOL = (KIND_FERRY, KIND_CARGO, KIND_CARGO, KIND_PAX, KIND_PAX,
            KIND_TOUR, KIND_SURVEY, KIND_SEARCH)

    def pool_for(self, level):
        """そのレベルで出る仕事の種類。"""
        return tuple(k for k in self.POOL if UNLOCK_LV.get(k, 1) <= level)

    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.at = ''
        self.jobs = []
        self.active = None
        self.msg = ''
        self.msg_t = 0
        self.free_fuel = False      # 回送を終えたら無料で満タンにする

    def _say(self, s, t=240):
        self.msg, self.msg_t = s, t

    def refresh(self, here, cap, level=1, trust=0.0):
        """その空港の仕事を並べ直す。

        毎回ランダムに引くと、4件とも同じ種類・同じ行き先になることがある
        （実測で種類そろいが4%、行き先そろいが12%）。種類は重複を避けて選び、
        行き先は順番に配って散らす。
        """
        self.at = here.name
        pool = [k for k in dict.fromkeys(self.pool_for(level)) if k != KIND_FERRY]
        self.rnd.shuffle(pool)
        kinds = [KIND_FERRY]
        while len(kinds) < BOARD_N:
            if pool:
                kinds.append(pool.pop())
            else:                       # 種類が足りなければ繰り返す
                rest = [k for k in self.pool_for(level) if k != KIND_FERRY]
                kinds.append(self.rnd.choice(rest) if rest else KIND_FERRY)
        others = _airports_from(here) or [here]
        self.rnd.shuffle(others)
        out = []
        for i, k in enumerate(kinds):
            j = make_job(k, here, cap, self.rnd,
                         pick_tier(level, self.rnd, trust),
                         dest=others[i % len(others)])
            if j is not None:
                out.append(j)
        self.jobs = out

    def ensure(self, here, cap, level=1, trust=0.0):
        if self.at != here.name or not self.jobs:
            self.refresh(here, cap, level, trust)

    def accept(self, i, cap):
        if self.active is not None:
            self._say('ALREADY ON A JOB')
            return False
        if not (0 <= i < len(self.jobs)):
            return False
        j = self.jobs[i]
        if j.payload > cap:
            self._say('TOO HEAVY FOR THIS AIRCRAFT')
            return False
        self.active = j
        del self.jobs[i]
        self._say('%s  %s  %d CR' % (j.title(), j.summary(), j.pay))
        return True

    def abandon(self):
        if self.active is None:
            return False
        self.active = None
        self._say('JOB ABANDONED')
        return True

    def payload(self):
        return self.active.payload if self.active else 0

    def update(self, ac, dt):
        if self.msg_t > 0:
            self.msg_t -= 1
        j = self.active
        if j is None:
            return
        j.update(ac, dt)
        if j.timed_out() and j.limit:
            pass          # 時間切れでも降ろせば半額。すぐには失敗にしない

    def landed(self, result):
        """着陸したときに呼ぶ。完了なら報酬を返す。"""
        j = self.active
        if j is None:
            return 0, ''
        ok, pay, note = j.check_landing(result)
        if not ok:
            if note:
                self._say(note)
            return 0, note
        kind = j.kind
        self.active = None
        self.at = ''            # 次に地上で止まったら新しい仕事が並ぶ
        self._say('JOB DONE  +%d CR%s' % (pay, note))
        self.free_fuel = (kind == KIND_FERRY)   # 回送は燃料込み
        return pay, note
