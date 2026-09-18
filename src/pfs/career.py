"""キャリアモード。機体のダメージ・クレジット・ランクを持つ。

アーケードは今までどおり何でも設定できる遊び方。キャリアでは天候と時刻を
選べず、燃料と修理に金がかかる。ここが「点を貯めて使う」の土台になる。

セーブはアーケードの設定（pfs_config.json）とは別ファイルに置く。
天候をいじっただけでキャリアの状態に触れてしまわないようにするため。
"""
import random

import fleet
import input_map as im

ARCADE, CAREER = 0, 1
NAMES = ('ARCADE', 'CAREER')
SAVE = 'pfs_career.json'

# 部位ごとの修理単価（ダメージ1%あたりのクレジット）
PARTS = ('GEAR', 'WING', 'ENGINE', 'AIRFRAME')
REPAIR = {'GEAR': 7, 'WING': 11, 'ENGINE': 14, 'AIRFRAME': 6}
QUICK_COST = 0.45          # 応急修理の費用は正規の45%
QUICK_LEFT = 20.0          # ただしダメージが20%残る
FUEL_COST = 2.5            # 燃料1%あたり
PAY_LANDING = 2.5          # 着陸1点あたりの報酬
HAND_PAY = 0.8             # 手で降ろしたときに着陸報酬へ上乗せする割合
RECOVER_FEE = 450          # 滑走路外からの機体回収費
START_CREDITS = 800

RANKS = ((0, 'STUDENT'), (500, 'PRIVATE'), (1600, 'COMMERCIAL'),
         (4000, 'AIRLINE'))

# レベル。資格が「飛べる条件」を決めるのに対し、レベルは「世界がどれだけ
# 厳しくなるか」を決める。XPから求まり、上限は15。
XP_PER_LV = 12.0
MAX_LV = 100
# 仮想の上限。ここに達するとXPが入らなくなり、レベルは止まる。金だけは稼げる。
# v1.1.0でヘリ・ジェットを解禁するとき、ここを外してLV51以降を開ける。
# 内部で貯め続けない理由: 更新した瞬間に何レベルも飛ぶと、
# 新しい解禁を1段ずつ味わう楽しみが消えるため
SOFT_MAX_LV = 50

# レベルごとに引ける風。20ktを超える風は操縦がかなり難しいので、
# 慣れるまで出てこないようにする。数字は weather.WIND_LEVELS の添字。
WIND_POOL = (
    (3, (1,)),                       # LV1-3:  弱風だけ
    (6, (1, 1, 2)),                  # LV4-6:  中風まで
    (10, (1, 2, 2, 4)),              # LV7-10: 変動風(AUTO)が混じる
    (999, (1, 2, 2, 3, 4)),          # LV11-:  強風も出る
)
# 荒天運航を取ると混じる段。段が上がるほど荒れた日の割合が増える
STORM_POOL = (3, 5, 3, 5, 5)
SHEAR_LV = 10                        # ウィンドシアが出はじめるレベル

# 資格: (ID, 表示名, 必要レベル, 費用, 説明)
# レベルで「何が許されるか」を決め、費用は別に払う。
RATINGS = (
    ('NIGHT', 'NIGHT RATING', 6, 900, 'FLY AT DUSK AND NIGHT'),
    ('IFR', 'INSTRUMENT RATING', 11, 2600, 'FLY IN RAIN AND LOW VIS'),
    ('TWIN', 'MULTI-ENGINE', 15, 3400, 'FLY THE TWIN'),
)
RAT = {r[0]: r for r in RATINGS}

# 装備: 機体ごとに積む。(ID, 表示名, 費用, 説明)
# 強力なので高い。新規キャリアから貯めて、2つそろうのに約1時間30分。
# 安いと最初の数便で手に入り、以後ほとんどの着陸が自動で済んでしまう
EQUIP = (
    ('AP', 'AUTOPILOT', 2800, 'CRUISE HOLD'),
    ('ILS', 'ILS RECEIVER', 4700, 'AUTOLAND ON THE GLIDESLOPE'),
)
EQ = {e[0]: e for e in EQUIP}

# 機体の強化。部位ごとに5段。売ると一緒に消えるので、乗り換えは重い決断になる。
# 耐久だけだと「壊れない部位を強化する意味が無い」ので、性能も一緒に上がる。
UPGRADE = (
    ('GEAR',     'REINFORCED GEAR',  'TOUGHER, BETTER BRAKES'),
    ('WING',     'WING SPAR KIT',    'TOUGHER, LOWER STALL SPEED'),
    ('ENGINE',   'ENGINE OVERHAUL',  'LESS WEAR, BETTER ECONOMY'),
    ('AIRFRAME', 'AIRFRAME BRACING', 'TOUGHER, LESS DRAG'),
)
UP_MAX = 5                 # 段数
UP_TOUGH = 0.10            # 1段ごとに受けるダメージがこれだけ減る（5段で半分）
UP_GAIN = {                # 1段ごとの性能の伸び
    'GEAR': 0.04,          # ブレーキ（5段で+20%）
    'WING': 0.016,         # 失速速度（5段で-8%）
    'ENGINE': 0.03,        # 燃費（5段で-15%）
    'AIRFRAME': 0.016,     # 抗力（5段で-8%）
}
# 段ごとの費用。後半ほど重くして、全部盛りより得意分野を選ばせる
UP_COST = (700, 1200, 1900, 2800, 4000)

# 操縦者のスキル。機体を乗り換えても残る。レベルで解禁し、金で段を買う。
# 飛び方そのものを楽にするものは入れない（横風着陸の面白さが消えるため）。
# 経済とメタに限ることで、腕の差はそのまま残る。
# (id, 表示名, 解禁レベル, 5段での効き, 説明)
SKILL = (
    ('DEAL',   'NEGOTIATION',   5,  0.25, 'JOBS PAY MORE'),
    ('LOG',    'LOGBOOK',       8,  0.40, 'JOBS GIVE MORE XP'),
    ('TRUST',  'CLIENT TRUST',  12, 0.50, 'HARDER JOBS APPEAR MORE OFTEN'),
    ('SHOP',   'PROCUREMENT',   16, 0.20, 'CHEAPER IN THE SHOP'),
    ('MAINT',  'MAINTENANCE',   20, 0.35, 'CHEAPER REPAIRS AND FUEL'),
    ('STORM',  'HEAVY WEATHER', 24, 1.00, 'ROUGHER DAYS, BETTER PAY'),
    ('BASE',   'HOME CONTRACT', 28, 0.15, 'MORE WORK FROM YOUR BASE'),
)
SK = {x[0]: x for x in SKILL}
SK_MAX = 5
# 段ごとの費用。解禁レベルが高いスキルほど下地も高い
SK_COST = (800, 1500, 2600, 4200, 6400)
SK_LV_STEP = 3             # 1段上げるごとに必要レベルがこれだけ上がる

# クラブ機の装備。自動操縦は付くがILSは付かない
RENT_EQUIP = ('AP',)

# 着陸でダメージが出はじめる沈下率[m/s]。これ以下なら無傷
SOFT_VS = 1.6
# エンジンは事故でしか傷まず、実測で400回着陸しても0%のままだった。
# 高出力ほど早く減る運転摩耗を入れて、4部位すべてに自然な発生源を作る
ENGINE_WEAR = 5.0          # 全開1時間あたりの摩耗[%]。約180フライトで100%

# クラブの貸出機。自機が飛べなくても借りられるので、詰みが起きない。
# 報酬の取り分は減るので、直して自機に戻りたくなる。
RENT_CUT = 0.40            # クラブの取り分
RENT_DMG = {'GEAR': 20.0, 'WING': 0.0, 'ENGINE': 25.0, 'AIRFRAME': 10.0}


class Career:
    def __init__(self):
        self.mode = ARCADE
        self.credits = float(START_CREDITS)
        self.xp = 0
        # 機体ごとにダメージを持つ。新しく買った機体が古い傷を引き継がないように
        self.plane = fleet.FIRST
        self.hangar = {fleet.FIRST: {p: 0.0 for p in PARTS}}
        self.flights = 0
        self.ratings = set()
        self.equip = {fleet.FIRST: set()}
        self.up = {}            # 機体ごとの強化 {機体: {部位: 段}}
        self.skill = {}         # 操縦者のスキル {id: 段}
        self.base = ''          # 拠点にした空港。そこ発の仕事が増える
        self.rented = False     # クラブ機を借りているか
        self.level_up = 0       # レベルが上がったら新しいレベルが入る
        self.msg = ''
        self.msg_t = 0
        self.rnd = random.Random()
        self.load()

    # ------------------------------------------------------------ 状態
    @property
    def dmg(self):
        """いま選んでいる機体のダメージ。"""
        return self.hangar.setdefault(self.plane, {p: 0.0 for p in PARTS})

    # ------------------------------------------------------------ 資格と装備
    def has_rating(self, rid):
        return rid in self.ratings

    def rating_ready(self, rid):
        """受けられるか。(可否, 理由) を返す。"""
        r = RAT[rid]
        if rid in self.ratings:
            return False, 'ALREADY HELD'
        if self.level < r[2]:
            return False, 'NEEDS LV %d' % r[2]
        if self.price(r[3]) > int(self.credits):
            return False, 'NEEDS %d CR' % self.price(r[3])
        return True, ''

    def buy_rating(self, rid):
        ok, why = self.rating_ready(rid)
        if not ok:
            self._say(why)
            return False
        self.credits -= self.price(RAT[rid][3])
        self.ratings.add(rid)
        self._say('%s EARNED' % RAT[rid][1])
        self.save()
        return True

    def recover(self):
        """滑走路の外から機体を運んでもらう。有料。"""
        if not self.on or self.rented:
            return 0                     # アーケードとクラブ機は無料
        fee = min(RECOVER_FEE, max(0, int(self.credits)))
        self.credits -= fee
        self.save()
        return fee

    def fitted(self, eid, pid=None):
        pid = pid or self.plane_id()
        if self.rented:
            return eid in RENT_EQUIP
        return eid in self.equip.get(pid, ())

    # ------------------------------------------------------------ スキル
    def sk_rank(self, sid):
        return self.skill.get(sid, 0) if self.on else 0

    def sk(self, sid):
        """そのスキルの効き 0..1。5段で満額。"""
        return SK[sid][3] * self.sk_rank(sid) / float(SK_MAX)

    def sk_need_lv(self, sid):
        """次の1段に要るレベル。段が上がるほど遠くなる。"""
        return SK[sid][2] + self.sk_rank(sid) * SK_LV_STEP

    def sk_cost(self, sid):
        r = self.sk_rank(sid)
        return 0 if r >= SK_MAX else SK_COST[r]

    def buy_skill(self, sid):
        r = self.sk_rank(sid)
        if r >= SK_MAX:
            self._say('ALREADY AT MAXIMUM')
            return False
        need = self.sk_need_lv(sid)
        if self.level < need:
            self._say('NEEDS LV%d' % need)
            return False
        cost = self.sk_cost(sid)
        if cost > int(self.credits):
            self._say('NEEDS %d CR' % cost)
            return False
        self.credits -= cost
        self.skill[sid] = r + 1
        self._say('%s  LV%d  -%d CR' % (SK[sid][1], r + 1, cost))
        self.save()
        return True

    def storm_pay(self, kt, shear):
        """荒れた日の割増。段の名前ではなく、実際に吹いた風速で払う。

        荒天運航は「風の効きを弱める」のではなく「荒れた日を引けるようにして、
        その日は高く払う」形にしてある。横風着陸の難しさは腕の見せ所として
        そのまま残したいため。
        """
        if not self.on:
            return 1.0
        return (1.0 + min(0.50, max(0.0, (kt - 8.0) / 40.0))
                + (0.10 if shear else 0.0))

    def base_pay(self, origin):
        """拠点発の仕事の割増。"""
        return 1.0 + (self.sk('BASE') if origin and origin == self.base else 0.0)

    def price(self, cr):
        """買い物の値引きを効かせた金額。"""
        return int(round(cr * (1.0 - self.sk('SHOP'))))

    # ------------------------------------------------------------ 機体強化
    def up_rank(self, part, pid=None):
        """その部位の強化段数。貸出機は素のまま。"""
        if self.rented or not self.on:
            return 0
        return self.up.get(pid or self.plane, {}).get(part, 0)

    def up_cost(self, part):
        """次の1段の費用。高い機体ほど部品も高い。"""
        r = self.up_rank(part)
        if r >= UP_MAX:
            return 0
        return self.price(UP_COST[r]
                          * fleet.spec(self.plane_id())['repair'])

    def buy_upgrade(self, part):
        if self.rented:
            self._say('CANNOT UPGRADE A CLUB AIRCRAFT')
            return False
        if self.up_rank(part) >= UP_MAX:
            self._say('ALREADY AT MAXIMUM')
            return False
        cost = self.up_cost(part)
        if cost > int(self.credits):
            self._say('NEEDS %d CR' % cost)
            return False
        self.credits -= cost
        d = self.up.setdefault(self.plane, {})
        d[part] = d.get(part, 0) + 1
        self._say('%s  LV%d  -%d CR' % (part, d[part], cost))
        self.save()
        return True

    def tough(self, part):
        """強化ぶん、受けるダメージが減る係数。"""
        return 1.0 - UP_TOUGH * self.up_rank(part)

    def buy_equip(self, eid):
        if self.rented:
            self._say('CANNOT FIT TO A CLUB AIRCRAFT')
            return False
        if self.fitted(eid):
            self._say('ALREADY FITTED')
            return False
        cost = self.price(EQ[eid][2])
        if cost > int(self.credits):
            self._say('NEEDS %d CR' % cost)
            return False
        self.credits -= cost
        self.equip.setdefault(self.plane, set()).add(eid)
        self._say('%s FITTED  -%d CR' % (EQ[eid][1], cost))
        self.save()
        return True

    def can_autopilot(self):
        """自動操縦が使えるか。アーケードでは常に使える。"""
        return not self.on or self.fitted('AP')

    def can_ils(self):
        """ILS自動着陸が使えるか。受信機を積んでいればよい。

        以前はIFR資格も要ったが、資格はLV11まで取れないのに受信機は先に
        買えてしまい、2200CRを払っても使えない期間ができていた。
        IFRは雨や低視程を引けるようにする資格として役目が残っている。
        """
        return not self.on or self.fitted('ILS')

    def can_buy_plane(self, pid):
        if pid == 'TWIN' and not self.has_rating('TWIN'):
            return False, 'NEEDS MULTI-ENGINE RATING'
        return True, ''

    def plane_id(self):
        """実際に飛んでいる機体。借りているならクラブのトレーナー。"""
        if not self.on:
            return fleet.FIRST
        return fleet.FIRST if self.rented else self.plane

    @property
    def spec(self):
        return fleet.spec(self.plane_id())

    @property
    def on(self):
        return self.mode == CAREER

    @property
    def worst(self):
        return max(self.dmg.values())

    @property
    def airworthy(self):
        """自機が飛べる状態か。どこか1部位でも100%なら不可。"""
        return self.worst < 100.0

    @property
    def grounded(self):
        """飛べない状態。クラブ機を借りていれば自機が壊れていても飛べる。"""
        return not self.rented and not self.airworthy

    def rent(self, on):
        """クラブ機の貸出を切り替える。地上でのみ。"""
        if on:
            self.rented = True
            self._say('CLUB AIRCRAFT - PAY IS %d PERCENT'
                      % round((1.0 - RENT_CUT) * 100))
        else:
            if not self.airworthy:
                self._say('YOUR AIRCRAFT IS UNAIRWORTHY')
                return False
            self.rented = False
            self._say('BACK TO YOUR OWN AIRCRAFT')
        self.save()
        return True

    @property
    def level(self):
        """XPから決まるレベル。仮想の上限 SOFT_MAX_LV で止まる。

        表示だけ止めてXPを貯め続けると、上限を開けた瞬間に何レベルも飛んで
        新しい解禁を1段ずつ味わえなくなる。add_xp 側でも止めてある。
        """
        return min(SOFT_MAX_LV, MAX_LV, 1 + int((self.xp / XP_PER_LV) ** 0.5))

    def xp_for(self, lv):
        return int(((lv - 1) ** 2) * XP_PER_LV)

    def next_level(self):
        """次のレベルまでの残りXP。上限なら None。"""
        lv = self.level
        if lv >= SOFT_MAX_LV:
            return None
        return self.xp_for(lv + 1) - self.xp

    def wind_pool(self):
        """いまのレベルで引ける風の一覧。

        荒天運航を取ると、レベルだけでは出ない段（強風とSEVERE）が混じる。
        """
        lv = self.level
        base = WIND_POOL[-1][1]
        for cap, pool in WIND_POOL:
            if lv <= cap:
                base = pool
                break
        r = self.sk_rank('STORM')
        return tuple(base) + tuple(STORM_POOL[:r]) if r else base

    def shear_ok(self):
        return self.level >= SHEAR_LV

    def rank_name(self):
        name = RANKS[0][1]
        for need, n in RANKS:
            if self.xp >= need:
                name = n
        return name

    def next_rank(self):
        for need, n in RANKS:
            if self.xp < need:
                return need - self.xp, n
        return None, None

    def _say(self, s, t=220):
        self.msg, self.msg_t = s, t

    def update(self, dt, throttle=0.0, running=False):
        if self.msg_t > 0:
            self.msg_t -= 1
        if running and self.on:
            # 回した時間だけエンジンが減る。全開ほど早い
            self.hurt('ENGINE', ENGINE_WEAR * (0.35 + throttle)
                      * dt / 3600.0)

    # ------------------------------------------------------------ ダメージ
    def at_cap(self):
        """仮想の上限に達しているか。以後はXPが入らない。"""
        return self.level >= SOFT_MAX_LV

    def add_xp(self, n):
        """XPを足す。レベルが上がったら level_up に新しいレベルを入れる。"""
        if n <= 0 or self.at_cap():
            return
        before = self.level
        self.xp += int(n)
        if self.level > before:
            self.level_up = self.level
            if self.at_cap():
                self._say('LEVEL %d - RATING MAXED' % SOFT_MAX_LV)

    def hurt(self, part, amount):
        # クラブ機の傷はクラブ持ち。自機には付かない
        if not self.on or self.rented or amount <= 0.0:
            return
        self.dmg[part] = min(100.0, self.dmg[part] + amount * self.tough(part))

    def touchdown(self, result):
        """接地したときのダメージだけを入れる。報酬は停止してから。

        接地の瞬間はまだ50ktで転がっているので、金額やレベルの文字を読めない。
        金銭のやりとりは settle() で完全停止してから行う。
        """
        if not self.on:
            return 0.0
        vs = abs(result['vs'])
        before = sum(self.dmg.values())
        # 沈下率は脚に、はみ出しや翼端接触は翼と機体に効く。
        # 線形にすると少し固い程度でも一気に壊れるので、指数で寝かせる。
        over = max(0.0, vs - SOFT_VS) ** 1.8
        self.hurt('GEAR', over * 7.0 * self.spec['gear'])
        self.hurt('AIRFRAME', over * 2.2)
        # 硬い接地の荷重は主翼の取り付けにも来る。翼が事故専用だと
        # 整備も強化も脚だけの話になってしまう
        self.hurt('WING', over * 1.6)
        if result['grade'] == 'WINGTIP STRIKE':
            self.hurt('WING', 45.0)
            self.hurt('AIRFRAME', 20.0)
        if not result['on_rwy']:
            self.hurt('WING', 12.0)
            self.hurt('AIRFRAME', 22.0)
        hurt = sum(self.dmg.values()) - before
        self.save()
        return hurt

    def settle(self, result, hand=0.0, tough=1.0):
        """完全停止したときの精算。(着陸報酬, 手動ボーナス, レベル) を返す。

        hand は着陸行程をどれだけ手で飛ばしたか 0..1。tough は悪天候の係数。
        自動着陸に罰は与えず、手で降ろしたぶんだけ上乗せする。ILSは現実でも
        安全のための装備なので、使ったことを咎める作りにはしない。
        """
        if not self.on:
            return 0, 0, 0
        pay = PAY_LANDING * ((1.0 - RENT_CUT) if self.rented else 1.0)
        got = int(result['score'] * pay) if result['on_rwy'] else 0
        bonus = int(got * HAND_PAY * hand * tough)
        self.credits += got + bonus
        self.level_up = 0
        self.add_xp(result['score'] * 0.5 * (1.0 + hand))   # 手動は経験値も倍
        self.flights += 1
        self.save()
        return got, bonus, self.level_up

    # ------------------------------------------------------------ 支払い
    def repair_cost(self, part, quick=False):
        c = self.dmg[part] * REPAIR[part] * fleet.spec(self.plane)['repair']
        c *= 1.0 - self.sk('MAINT')          # 整備の手配がうまいほど安い
        return int(c * (QUICK_COST if quick else 1.0))

    def repair(self, part, quick=False):
        if self.dmg[part] <= 0.0:
            self._say('%s IS FINE' % part)
            return False
        cost = self.repair_cost(part, quick)
        if cost > int(self.credits):
            self._say('NOT ENOUGH CREDITS (%d CR)' % cost)
            return False
        self.credits -= cost
        self.dmg[part] = QUICK_LEFT if quick else 0.0
        self._say('%s %s  -%d CR' % (part, 'PATCHED' if quick else 'REPAIRED', cost))
        self.save()
        return True

    def patch_all_cost(self):
        return sum(self.repair_cost(p, True) for p in PARTS
                   if self.dmg[p] > QUICK_LEFT)

    def patch_all(self):
        """全部位を応急修理。安いがダメージが20%残る。"""
        parts = [p for p in PARTS if self.dmg[p] > QUICK_LEFT]
        if not parts:
            self._say('NOTHING TO PATCH')
            return False
        cost = self.patch_all_cost()
        if cost > int(self.credits):
            self._say('NOT ENOUGH CREDITS (%d CR)' % cost)
            return False
        self.credits -= cost
        for p in parts:
            self.dmg[p] = QUICK_LEFT
        self._say('PATCHED %d PARTS  -%d CR  (20%% LEFT)' % (len(parts), cost))
        self.save()
        return True

    # ------------------------------------------------------------ 機体
    def owns(self, pid):
        return pid in self.hangar

    def value(self, pid):
        """下取り価格。買値の55%から傷んだぶんを引く。"""
        base = fleet.spec(pid)['price'] * 0.55
        d = self.hangar.get(pid) or {}
        wear = sum(d.values()) / (100.0 * len(PARTS))
        return int(max(0.0, base * (1.0 - wear * 0.7)))

    def buy(self, pid):
        if self.owns(pid):
            self._say('ALREADY OWNED')
            return False
        ok, why = self.can_buy_plane(pid)
        if not ok:
            self._say(why)
            return False
        price = self.price(fleet.spec(pid)['price'])
        if price > int(self.credits):
            self._say('NOT ENOUGH CREDITS (%d CR)' % price)
            return False
        self.credits -= price
        self.hangar[pid] = {p: 0.0 for p in PARTS}
        self.equip.setdefault(pid, set())
        self.plane = pid
        self.rented = False
        self._say('BOUGHT %s  -%d CR' % (fleet.spec(pid)['name'], price))
        self.save()
        return True

    def sell(self, pid):
        if not self.owns(pid):
            return False
        if len(self.hangar) <= 1:
            self._say('CANNOT SELL YOUR ONLY AIRCRAFT')
            return False
        got = self.value(pid)
        del self.hangar[pid]
        self.equip.pop(pid, None)
        self.up.pop(pid, None)          # 強化も一緒に消える
        self.credits += got
        if self.plane == pid:
            self.plane = sorted(self.hangar)[0]
        self._say('SOLD %s  +%d CR' % (fleet.spec(pid)['name'], got))
        self.save()
        return True

    def select(self, pid):
        if not self.owns(pid):
            self._say('NOT OWNED')
            return False
        self.plane = pid
        self.rented = False
        self._say('FLYING %s' % fleet.spec(pid)['name'])
        self.save()
        return True

    def fuel_rate(self):
        """燃料1%あたりの値段。整備の手配がうまいほど安い。"""
        return FUEL_COST * (1.0 - self.sk('MAINT'))

    def fuel_cost(self, missing):
        return int(round(missing * self.fuel_rate()))

    def buy_fuel(self, missing):
        """入れられた量[%]を返す。金が足りなければ入る分だけ。

        給油は毎フレーム少しずつ呼ばれるので、代金は端数のまま引く
        （整数に丸めると1回あたり0円になってタダで入ってしまう）。
        """
        if missing <= 0.0:
            return 0.0
        rate = self.fuel_rate()
        cost = missing * rate
        if cost <= self.credits:
            self.credits -= cost
            return missing
        can = max(0.0, self.credits / rate) if rate > 1e-6 else missing
        self.credits -= can * rate
        return can

    # ------------------------------------------------------------ 飛行特性
    def apply(self, ac):
        """機体の諸元とダメージを飛行特性に反映する。毎フレーム呼ぶ。"""
        pid = self.plane_id()
        if getattr(ac, 'spec_id', None) != pid:
            fleet.apply_spec(ac, pid)
        if not self.on:
            ac.dmg_drag = 0.0
            ac.dmg_lift = 1.0
            ac.dmg_power = 1.0
            ac.dmg_brake = 1.0
            return
        d = RENT_DMG if self.rented else self.dmg
        # 強化は損耗の逆向きに効く。脚はブレーキ、翼は揚力（＝失速速度）、
        # 機体は抗力。エンジンの燃費は burn_rate 側で見る
        ac.dmg_drag = (d['WING'] * 0.00035 + d['AIRFRAME'] * 0.00018
                       - ac.CD0 * UP_GAIN['AIRFRAME'] * self.up_rank('AIRFRAME'))
        ac.dmg_lift = (1.0 - d['WING'] * 0.0016
                       + UP_GAIN['WING'] * 2.0 * self.up_rank('WING'))
        ac.dmg_power = 1.0 - d['ENGINE'] * 0.005
        ac.dmg_brake = (1.0 - d['GEAR'] * 0.006
                        + UP_GAIN['GEAR'] * self.up_rank('GEAR'))

    def reset(self):
        """最初からやり直す。モードだけは今のまま残す。"""
        mode = self.mode
        self.credits = float(START_CREDITS)
        self.xp = 0
        self.flights = 0
        self.ratings = set()
        self.equip = {fleet.FIRST: set()}
        self.up = {}            # 機体ごとの強化 {機体: {部位: 段}}
        self.skill = {}         # 操縦者のスキル {id: 段}
        self.base = ''          # 拠点にした空港。そこ発の仕事が増える
        self.plane = fleet.FIRST
        self.hangar = {fleet.FIRST: {p: 0.0 for p in PARTS}}
        self.rented = False
        self.mode = mode
        self._say('CAREER RESET - %d CR' % START_CREDITS)
        self.save()

    # ------------------------------------------------------------ 保存
    def to_dict(self):
        return {'mode': self.mode, 'credits': round(self.credits, 1), 'xp': self.xp,
                'plane': self.plane, 'hangar': self.hangar,
                'ratings': sorted(self.ratings),
                'equip': {k: sorted(v) for k, v in self.equip.items()},
                'up': self.up, 'skill': self.skill, 'base': self.base,
                'flights': self.flights, 'rented': self.rented}

    def save(self):
        im.save_json(SAVE, self.to_dict())

    def load(self):
        d = im.load_json(SAVE)
        if not d:
            return
        self.mode = ARCADE if int(d.get('mode', 0)) == 0 else CAREER
        self.credits = float(d.get('credits', START_CREDITS))
        self.xp = int(d.get('xp', 0))
        self.flights = int(d.get('flights', 0))
        self.rented = bool(d.get('rented', False))
        hangar = d.get('hangar') or {}
        if hangar:
            self.hangar = {}
            for pid, dm in hangar.items():
                if pid in fleet.BY_ID:
                    self.hangar[pid] = {p: float(dm.get(p, 0.0)) for p in PARTS}
        if not self.hangar:
            self.hangar = {fleet.FIRST: {p: 0.0 for p in PARTS}}
        self.ratings = set(x for x in (d.get('ratings') or []) if x in RAT)
        self.equip = {k: set(x for x in v if x in EQ)
                      for k, v in (d.get('equip') or {}).items()}
        self.base = str(d.get('base', ''))
        self.skill = {k: max(0, min(SK_MAX, int(v)))
                      for k, v in (d.get('skill') or {}).items() if k in SK}
        self.up = {}
        for pid, ups in (d.get('up') or {}).items():
            if pid in fleet.BY_ID:
                self.up[pid] = {p: max(0, min(UP_MAX, int(v)))
                                for p, v in ups.items() if p in PARTS}
        self.plane = d.get('plane', fleet.FIRST)
        if self.plane not in self.hangar:
            self.plane = sorted(self.hangar)[0]
