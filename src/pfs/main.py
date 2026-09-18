# title: PFS - Pixel Flight Simulator
# author: pfs
# desc: Fly, sightsee and land a light aircraft over a 16km world
# version: 1.0

"""PFS - Pixel Flight Simulator

小型機で離陸し、遊覧して、着陸するだけのゲーム。
実行:  python3 main.py   /   pyxel play pfs.pyxapp
"""
import gc
import math
import os
import random
import time
import pyxel
import world, fx, scene, views, cockpit, hud, audio, weather, bgm, menu
import title as title_mod
import effects
import objects
import charter as charter_mod
import atc as atc_mod
import career as career_mod
import lang
import fleet
import mission as mission_mod
import traffic as traffic_mod
import autopilot as autopilot_mod
import course as course_mod
import input_map as im
import result as result_mod
import briefing as briefing_mod
import aircraft as aircraft_mod
from aircraft import Aircraft

PITCH_EXPO = 0.55           # ピッチの中央付近の鈍らせ具合（0で線形）
LOOK_MAX = 100.0            # 視点を振れる角度[deg]
LOOK_SPEED = 150.0          # 振る速さ[deg/s]
LOOK_BACK = 6.0             # 正面へ戻る速さの係数
# 手動着陸の評価。APを切った高度で「どこまで手で飛ばしたか」を測る。
# これより上で切れば全部手動あつかい、下まで任せるほど手動ぶんが減る
HAND_HIGH_FT = 1000.0
HAND_LOW_FT = 100.0
ASPECTS = (('4:3', 256, 192), ('1:1', 256, 256))   # 画面比率の選択肢
W, H = ASPECTS[0][1:]
RECT = (0, 0, W, H)
FUEL_MAX = 100.0                           # 燃料[%]
ENDURANCE = (10, 20, 30)                   # 全開での航続時間[分]の選択肢
IDLE_FRAC = 0.12                           # アイドルの消費（全開を1としたとき）
CLOUD_BASE, CLOUD_TOP = 95.0, 112.0        # マップ単位（1ユニット=8m）
RAIN_BASE = 58.0                           # 雨天時の低い雲底（約460m）
VIS_NAMES = ('CLEAR', 'HAZE', 'FOG')
VIS_HAZE = (1.0, 1.35, 1.6)                # 霞みの濃さ
VIS_SCALE = (1.0, 0.35, 0.10)              # 霞み始める距離の倍率
VIS_FOG = (0.0, 0.18, 0.62)                # 画面全体を覆う量


def _ramp(cur, tgt, rate, dt=1.0 / 60.0):
    """舵を目標へ滑らかに動かす。短く叩けば少しだけ当てられる。"""
    m = rate * dt
    d = tgt - cur
    return cur + (m if d > m else (-m if d < -m else d))


def _set_screen(i):
    """画面サイズを決めて、各モジュールへ配る。pyxel.init より前に呼ぶ。"""
    global W, H, RECT
    W, H = ASPECTS[i][1:]
    RECT = (0, 0, W, H)
    views.set_size(W, H)
    cockpit.set_size(W, H)
    menu.set_size(W, H)
    result_mod.set_size(W, H)
    briefing_mod.set_size(W, H)
    weather.set_size(W, H)


# 自動送りのときにたどる順番。夜明け側は同じパレットを逆にたどる
TOD_CYCLE = ('day', 'golden', 'dusk', 'night', 'dusk', 'golden')
TOD_PERIOD = (240.0, 480.0, 900.0)   # 一巡にかける秒数の選択肢
VERSION = '1.0.1'
TIME_MULT = (1, 2, 4)                # 時間加速の倍率
# 自動操縦のモードを読み上げる音声（autopilot.OFF/CRUISE/ILS の順）。
# 巡航は行き先を持つかどうかで読み分ける
AP_CLIP = ('', 'g_ap_cruise', 'g_ap_ils')
AP_CLIP_NAV = 'g_ap_nav'


class App:
    TODS = ('day', 'golden', 'dusk', 'night', 'auto')
    SUN = {'day': (-55, 30), 'golden': (-22, 8), 'dusk': None, 'night': None}

    def __init__(self, headless=False):
        # FPSは pyxel.init 時にしか決められないので、設定を先に読む
        cfg = im.load_config()
        self.fps = 30 if int(cfg.get('fps_limit', 60)) == 30 else 60
        self.dt = 1.0 / self.fps
        self.fscale = 60.0 / self.fps      # 60FPS基準の量を換算する係数
        # 画面サイズも pyxel.init 時にしか決められない
        self.aspect_i = int(cfg.get('aspect', 0)) % len(ASPECTS)
        lang.set_lang(int(cfg.get('lang', 0)))
        # ヘッドレス検証や PFS_NO_TITLE=1 のときはタイトルを出さない
        self.headless = bool(headless)
        self.title_t = None if (headless or os.environ.get('PFS_NO_TITLE')) else 0.0
        _set_screen(self.aspect_i)
        # ESCはメニューのキャンセルに使うので、既定の終了キーは無効化する
        pyxel.init(W, H, title='PFS - Pixel Flight Sim', fps=self.fps,
                   quit_key=pyxel.KEY_NONE, headless=headless)
        world.make_tileset(pyxel.images[0])
        world.make_clouds(pyxel.images[1])
        world.make_cloud_shadow(pyxel.images[2])
        for i, src in ((0, 0), (3, 0), (1, 1), (2, 2)):
            pyxel.tilemaps[i].imgsrc = src
        world.make_world(pyxel.tilemaps[0], pyxel.tilemaps[3])   # 昼 / 夜
        world.tile_wrap(pyxel.tilemaps[1])                       # 雲
        world.tile_wrap(pyxel.tilemaps[2])                       # 雲影
        self.rain_cloud = pyxel.Image(256, 256)                  # 雨雲
        world.make_rain_clouds(self.rain_cloud)
        pyxel.tilemaps[4].imgsrc = self.rain_cloud
        world.tile_wrap(pyxel.tilemaps[4])
        self.ac = Aircraft()
        self.view_i = 0         # 0=コクピット 1=全画面HUD 2=外部視点
        self.cam = None         # 外部視点のカメラ位置（追従で遅れる）
        self.tod_i = 0
        self.tod_t = 0.0        # 自動送りの経過時間[秒]
        self.tod_speed_i = 1    # 一巡の速さ
        self.dest_i = 1        # 目的地（初期は NORTH）
        self.visited = set()   # 訪れた見どころの名前
        self.charter = charter_mod.Charter()
        self._ap_was = False    # 自動操縦の入切を音で知らせるための前回値
        self._ap_mode_was = ''  # モードが変わったときも読み上げる
        self._ap_low_ft = None  # 今回の飛行でAPが働いた最低高度。Noneなら未使用
        self._calls = set()     # 鳴らし終えた対地高度のコール
        self._appr_from = 0.0   # 進入路に入ったときの高度[ft]
        self.atc = atc_mod.Atc()
        self.career = career_mod.Career()
        self.board = mission_mod.Board()
        self._ground_t = 0.0    # 飛べない状態の知らせを繰り返す間隔
        self._recover = False   # 滑走路外に降りたので回収待ち
        self._pending = None    # 精算待ちの着陸
        self.banner = ''        # 精算の表示（機体のメッセージとは別枠）
        self.result = result_mod.Result(self)
        self.brief = briefing_mod.Briefing(self)
        self.banner_t = 0
        self._hurt = 0.0
        self._fuel_spent = 0.0  # 前回の精算からの燃料代
        self._atc_ph = 'ramp'   # ramp / roll / air / inbound / final
        self._sink_t = 0.0      # 沈下率警報の間隔
        self.speed_i = 0        # 時間加速の段
        self.simt = 0.0         # 加速も含めた世界の経過時間[秒]
        self.clouds = True
        self.rain = weather.Rain()
        self.raining = False
        self.effects = effects.Effects()
        self.birds = effects.Birds()
        self.birds_on = True
        self.wiper = weather.Wiper()
        self.land_light = True
        self.app_guide = True   # 進入経路の輪を出すか
        self.result_on = True   # 着陸後のリザルト画面を出すか
        self.ap_nav = True      # 巡航で行き先へ向かうか（切れば遊覧）
        self.look = 0.0         # 視点の左右振り[deg]
        self.turb_shake = 0.0   # 乱気流による画面の揺れ
        self.flash = 0.0        # 稲光の明るさ
        self.thunder_t = 0.0    # 雷鳴までの秒数
        self.thunder_n = 0.0    # 雷の近さ 0..1
        self.lightning_on = True
        self.rnd = random.Random(29)
        self.vis = 0            # 0=CLEAR 1=HAZE 2=FOG
        self.wind = weather.Wind()
        self.detail = 2          # 0=LOW 1=MEDIUM 2=HIGH
        self.show_fps = False
        self.landing_log = []
        self.stats = {'best': 0, 'total': 0, 'count': 0, 'hand': 0}
        self.apt_best = {}      # 空港ごとの最高得点
        self.air_time = 0.0     # 総飛行時間[秒]
        self.traffic = traffic_mod.Traffic()
        self.course = course_mod.Course()
        self.pilot = autopilot_mod.Autopilot()
        self._t_draw = 0.0       # draw()の所要時間
        self._t_step = 0.0       # 実際のフレーム間隔
        self._t_last = 0.0
        self._steps = []
        self._probe = []        # 起動直後の自動判定用
        self._probe_last = 0.0
        self.paused = False
        self.fuel = FUEL_MAX
        self._fuel_warn = FUEL_MAX
        self.endurance_i = 2      # 既定は30分
        self.audio = audio.Audio()
        self.bgm = bgm.Bgm()
        self.imap = im.InputMap()
        self.menu = menu.Menu(self)
        self._was_ground = True
        self.shake = 0.0        # 接地の衝撃（減衰する）
        self.frames = 0         # 自前のフレーム数（ポーズ中は進まない）
        self.load_settings()
        self.load_flight()        # 中断したところから続ける
        self._state = {}          # 毎フレーム作り直さず使い回す
        # 生成済みのオブジェクトを世代管理から外し、GCの発生頻度を下げる。
        # 1フレームだけ突出して遅くなる（コマ落ちする）のを減らすため。
        gc.collect()
        try:
            gc.freeze()
        except AttributeError:
            pass
        gc.set_threshold(20000, 50, 50)
        if cfg:
            self._probe = None            # 一度設定済みなら自動判定しない
        if self.bgm.count:
            self.bgm.start()

    def run(self):
        pyxel.run(self.update, self.draw)

    # ------------------------------------------------------------ 設定の保存
    @property
    def cockpit_view(self):
        return self.view_i == 0

    @cockpit_view.setter
    def cockpit_view(self, v):
        self.view_i = 0 if v else 1

    def tod_name(self):
        return self.TODS[self.tod_i].upper()

    def tod_now(self):
        """いまの時刻。(主たる時刻, 混ぜる相手, 混ぜ具合0..1) を返す。

        AUTO のときは TOD_CYCLE を巡りながら、隣どうしを連続的に混ぜる。
        """
        if self.TODS[self.tod_i] != 'auto':
            return self.TODS[self.tod_i], None, 0.0
        n = len(TOD_CYCLE)
        step = TOD_PERIOD[self.tod_speed_i] / n
        k = (self.tod_t / step) % n
        i = int(k)
        t = k - i
        a, b = TOD_CYCLE[i], TOD_CYCLE[(i + 1) % n]
        if a == b:
            return a, None, 0.0
        # 名前で見る判定（夜かどうかなど）は、より近いほうを採用する
        if t > 0.5:
            return b, a, 1.0 - t
        return a, b, t

    def set_paused(self, v):
        self.paused = v
        if v:
            self.audio.set_muted(True)
            self.bgm.stop()
        else:
            self.audio.set_muted(False)
            if self.bgm.volume:
                self.bgm.start()

    FLIGHT_SAVE = 'pfs_flight.json'

    def save_flight(self):
        """飛行中の状態をそのまま保存する。いつ中断されても続きから飛べる。"""
        ac = self.ac
        im.save_json(self.FLIGHT_SAVE, {
            'x': ac.x, 'y': ac.y, 'alt': ac.alt, 'v': ac.V, 'gamma': ac.gamma,
            'hdg': ac.hdg, 'pitch': ac.pitch, 'roll': ac.roll,
            'throttle': ac.throttle, 'trim': ac.trim, 'flap': ac.flap_i,
            'brake': ac.brake, 'on_ground': ac.on_ground, 'engine': ac.engine,
            'fuel': self.fuel, 'view': self.view_i, 'simt': self.simt,
            'tod': self.tod_i, 'tod_t': self.tod_t, 'clouds': self.clouds,
            'rain': self.raining, 'vis': self.vis,
            'wind_level': self.wind.level, 'wind_dir': self.wind.direction,
            'job': mission_mod.job_to_dict(self.board.active)
            if self.board.active else None,
        })

    def load_flight(self):
        """保存された飛行状態を復元する。無ければ何もしない。"""
        d = im.load_json(self.FLIGHT_SAVE)
        if not d:
            return False
        ac = self.ac
        ac.x, ac.y = float(d['x']), float(d['y'])
        ac.alt, ac.V = float(d['alt']), float(d['v'])
        ac.gamma, ac.hdg = float(d['gamma']), float(d['hdg'])
        ac.pitch, ac.roll = float(d['pitch']), float(d['roll'])
        ac.throttle, ac.trim = float(d['throttle']), float(d['trim'])
        ac.flap_i = int(d.get('flap', 0))
        ac.brake = bool(d.get('brake', True))
        ac.on_ground = bool(d.get('on_ground', True))
        ac.engine = float(d.get('engine', 1.0))
        ac.elevator = ac.aileron = ac.rudder = 0.0
        self.fuel = float(d.get('fuel', FUEL_MAX))
        self._fuel_warn = self.fuel
        self.view_i = int(d.get('view', 0)) % 3
        self.simt = float(d.get('simt', 0.0))
        self.tod_i = int(d.get('tod', 0)) % len(self.TODS)
        self.tod_t = float(d.get('tod_t', 0.0))
        self.clouds = bool(d.get('clouds', True))
        self.raining = bool(d.get('rain', False))
        self.vis = int(d.get('vis', 0)) % 3
        self.wind.set_level(int(d.get('wind_level', 1)))
        self.wind.direction = float(d.get('wind_dir', 250.0))
        self.board.active = mission_mod.job_from_dict(d.get('job'))
        ac._say('FLIGHT RESUMED', 180)
        return True

    def reset_records(self):
        """飛行の記録を消す。キャリアをやり直すときに一緒に消す。

        記録は設定ファイル側（pfs_config.json）にあるので、
        キャリアのセーブを初期化しただけでは残ってしまう。
        """
        self.landing_log = []
        self.stats = {'best': 0, 'total': 0, 'count': 0, 'hand': 0}
        self.apt_best = {}
        self.visited = set()
        self.air_time = 0.0
        self.course.best = None
        self.charter.best = {}
        self.save_settings()

    def clear_flight_save(self):
        im.save_json(self.FLIGHT_SAVE, {})

    def save_settings(self):
        im.save_config({
            'layout': im.layout,
            'keys': self.imap.to_dict(),
            'bgm_mode': self.bgm.mode, 'bgm_vol': self.bgm.volume,
            'se_vol': self.audio.volume, 'atc_vol': self.atc.volume,
            'tod': self.tod_i,
            'tod_speed': self.tod_speed_i, 'lightning': self.lightning_on,
            'speed': self.speed_i,
            'clouds': self.clouds, 'rain': self.raining, 'vis': self.vis,
            'detail': self.detail, 'fps': self.show_fps,
            'fps_limit': self.fps, 'aspect': self.aspect_i,
            'lang': lang.lang,
            'wind_level': self.wind.level, 'wind_dir': int(self.wind.direction),
            'shear': self.wind.shear_on,
            'log': self.landing_log[-8:], 'stats': self.stats,
            'best_time': self.course.best,
            'apt_best': self.apt_best, 'air_time': int(self.air_time),
            'charter': self.charter.to_dict(),
            'visited': sorted(self.visited),
            'endurance': self.endurance_i,
            'birds': self.birds_on, 'wiper': self.wiper.on,
            'land_light': self.land_light, 'app_guide': self.app_guide,
            'result_on': self.result_on, 'ap_nav': self.ap_nav,
        })

    def load_settings(self):
        d = im.load_config()
        if not d:
            return
        # 配置を先に合わせてから割り当てを読む（保存値はその配置で書かれている）
        lay = int(d.get('layout', im.layout))
        if lay != im.layout:
            self.imap.set_layout(lay)
        self.imap.from_dict(d.get('keys'))
        self.bgm.set_mode(int(d.get('bgm_mode', 0)))
        self.bgm.volume = int(d.get('bgm_vol', 5))
        self.bgm._apply_gain()
        self.audio.set_volume(int(d.get('se_vol', 5)))
        self.atc.set_volume(int(d.get('atc_vol', 6)))
        self.tod_i = int(d.get('tod', 0)) % len(self.TODS)
        self.tod_speed_i = int(d.get('tod_speed', 1)) % len(TOD_PERIOD)
        self.speed_i = int(d.get('speed', 0)) % len(TIME_MULT)
        self.lightning_on = bool(d.get('lightning', True))
        self.clouds = bool(d.get('clouds', True))
        self.raining = bool(d.get('rain', False))
        self.vis = int(d.get('vis', 0)) % 3
        self.detail = int(d.get('detail', 2)) % 3
        self.show_fps = bool(d.get('fps', False))
        self.wind.set_level(int(d.get('wind_level', 1)))
        self.wind.direction = float(d.get('wind_dir', 250)) % 360
        self.wind.shear_on = bool(d.get('shear', True))
        self.landing_log = list(d.get('log') or [])
        self.apt_best = {str(k): int(v) for k, v in (d.get('apt_best') or {}).items()}
        self.air_time = float(d.get('air_time', 0.0))
        self.visited = set(d.get('visited') or [])
        self.charter.from_dict(d.get('charter'))
        self.endurance_i = int(d.get('endurance', 2)) % len(ENDURANCE)
        self.birds_on = bool(d.get('birds', True))
        self.wiper.on = bool(d.get('wiper', True))
        self.land_light = bool(d.get('land_light', True))
        self.app_guide = bool(d.get('app_guide', True))
        self.result_on = bool(d.get('result_on', True))
        self.ap_nav = bool(d.get('ap_nav', True))
        st = d.get('stats') or {}
        self.stats = {'best': int(st.get('best', 0)),
                      'total': int(st.get('total', 0)),
                      'count': int(st.get('count', 0)),
                      'hand': int(st.get('hand', 0))}
        bt = d.get('best_time')
        self.course.best = float(bt) if bt else None

    def _look(self, m):
        """視点の左右振り。自動操縦中も効かせたいので舵とは分けてある。

        右スティックは倒した量がそのまま角度になり、手を離せば正面へ戻る。
        十字キー(L2同時押し)は押している間だけ動く。
        """
        sk = m.stick('look_right') - m.stick('look_left')
        lk = m.axis('look_right', 'look_left')
        if sk:
            self.look = sk * LOOK_MAX
        elif lk:
            self.look = max(-LOOK_MAX, min(LOOK_MAX,
                                           self.look + lk * LOOK_SPEED * self.dt))
        elif not m.held['look_hold']:
            self.look -= self.look * min(1.0, LOOK_BACK * self.dt)
            if abs(self.look) < 0.5:
                self.look = 0.0

    # ------------------------------------------------------------ 入力
    def _controls(self):
        ac, m = self.ac, self.imap
        if m.pressed['autopilot']:
            if not self.career.can_autopilot():
                ac._say('NO AUTOPILOT FITTED', 150)
            else:
                # 進入線上なのにILSへ移れないと、巡航のまま滑走路から離れて
                # 「APが壊れている」ように見える。理由を出す
                warn = (not self.pilot.on and not self.career.can_ils()
                        and self.pilot.approach_ready(ac))
                self.pilot.toggle(ac, allow_ils=self.career.can_ils())
                if warn:
                    ac._say('NO ILS RECEIVER - CRUISE ONLY', 180)
        if m.pressed['view']:
            self.view_i = (self.view_i + 1) % 3
            if self.view_i == 2:
                self.cam = None       # 切り替えた瞬間は補間せず定位置から
        if m.pressed['dest']:
            self.dest_i = (self.dest_i + 1) % len(world.DESTS)
            ac._say('DEST ' + world.DESTS[self.dest_i].name, 90)
        if m.pressed['brake']:
            ac.brake = not ac.brake
            ac._say('BRAKE ' + ('ON' if ac.brake else 'OFF'), 60)
        if m.pressed['flap_down']:
            ac.set_flap(1); self.audio.click()
        if m.pressed['flap_up']:
            ac.set_flap(-1); self.audio.click()
        self._look(m)                   # 自動操縦中でも外は見まわせる
        if self.pilot.on:
            return                      # 作動中は手動の舵とスロットルを受け付けない
        if m.held['trim_down']:
            ac.add_trim(math.radians(-2.2) * self.dt)
        if m.held['trim_up']:
            ac.add_trim(math.radians(2.2) * self.dt)
        if m.held['throttle_up']:
            ac.add_throttle(0.9 * self.dt)
        if m.held['throttle_down']:
            ac.add_throttle(-0.9 * self.dt)
        # アナログ軸は倒した量をそのまま使う（ボタンなら1.0）。
        # ピッチだけは中央付近を鈍らせて、細かく当てられるようにする。
        e = m.axis('pitch_down', 'pitch_up', PITCH_EXPO)
        a = m.axis('roll_right', 'roll_left')
        r = m.axis('rudder_right', 'rudder_left')
        ac.elevator = _ramp(ac.elevator, -e, 2.6 if e else 5.0, self.dt)
        ac.aileron = _ramp(ac.aileron, a, 1.9 if a else 4.2, self.dt)
        ac.rudder = _ramp(ac.rudder, r, 3.0 if r else 6.0, self.dt)

    # ------------------------------------------------------------ 更新
    def update(self):
        self.imap.update()
        self.bgm.update()
        if self.title_t is not None:
            self._title_update()
            return
        if self.brief.open:
            self.brief.update(self.imap, auto=self.headless)
            if not self.headless:
                return
        if self.result.open:
            # ヘッドレス（自動テスト）では誰も閉じられないので世界を止めない
            self.result.update(self.imap, auto=self.headless)
            if not self.headless:
                return
        if self.menu.open:
            self.menu.update(self.imap)
            return
        if self.imap.pressed['menu']:
            self.menu.toggle()
            return
        self._controls()
        if self.paused:
            return
        self.frames += 1
        if self.banner_t > 0:          # 描画側で減らすと、描画回数に左右される
            self.banner_t -= 1
        # 時間加速。dtを伸ばすと積分が破綻するので、同じdtで複数回進める
        for _ in range(self.time_mult()):
            self._step(self.dt)
        self.audio.update(self.ac, self.frames * self.fscale)
        self.shake *= 0.94 ** self.fscale
        if self.raining:
            self.rain.update(self.ac.V, self.fscale, self.ac.roll)
        self.wiper.update(self.dt, self.rain if self.raining else None,
                          self.raining)

    def time_mult(self):
        """いまの時間倍率。地上や低空では効かせない。"""
        if self.speed_i == 0 or self.ac.on_ground or self.ac.alt_ft < 400.0:
            return 1
        return TIME_MULT[self.speed_i]

    def _step(self, dt):
        """世界を dt だけ進める。時間加速のときは1フレームに複数回呼ばれる。"""
        self.simt += dt
        self.career.update(dt, self.ac.throttle,
                           self.ac.engine > 0.01 and self.fuel > 0.0)
        self.career.apply(self.ac)
        # 積荷のぶん重くなる。離陸距離も失速速度も上がる
        self.ac.MASS = (fleet.spec(self.career.plane_id())['mass']
                        + self.board.payload())
        self.board.update(self.ac, dt)
        if self.ac.on_ground and self.ac.kias < 3.0:
            self.board.ensure(world.nearest_airport(self.ac.x, self.ac.y),
                              self.career.spec['cap'], self.career.level,
                              self.career.sk('TRUST'))
        if self.career.grounded and self.ac.on_ground:
            # 100%まで傷んだら、修理するまで出力が上がらない
            self.ac.throttle = min(self.ac.throttle, 0.15)
            self._ground_t -= dt
            if self._ground_t <= 0.0:
                self._ground_t = 8.0
                self.ac._say('UNAIRWORTHY - REPAIR OR RENT A CLUB AIRCRAFT', 240)
        self.wind.update(dt, self.ac.alt, not self.ac.on_ground)
        if self.wind.warn == 159:
            self.ac._say('WINDSHEAR', 160)
            self.audio.warn()
            self.atc.say('g_windshear')
        self.ac.step(dt, self.wind.vector())
        self.pilot.update(self.ac, dt, self.wind, self.ap_target())
        # 入切とモードは1回の say にまとめる。警報は後から言うと前を消すので
        ap_on = self.pilot.on
        ap_key = AP_CLIP[self.pilot.mode]
        if ap_key == 'g_ap_cruise' and self.pilot.target is not None:
            ap_key = AP_CLIP_NAV                   # 行き先つきの巡航
        if ap_on != self._ap_was or ap_key != self._ap_mode_was:
            clips = []
            if ap_on != self._ap_was:              # 自分から切れることもある
                self.audio.autopilot(ap_on)
                clips.append('g_ap_on' if ap_on else 'g_ap_off')
            if ap_on and ap_key != self._ap_mode_was:
                clips.append(ap_key)               # 巡航/NAV/ILSを続けて言う
            self._ap_was, self._ap_mode_was = ap_on, ap_key
            if clips:
                self.atc.say(*clips)
        if self.pilot.on and not self.ac.on_ground:
            a = self.ac.alt_ft         # APに任せた最低高度＝手動ぶんの境目
            self._ap_low_ft = a if self._ap_low_ft is None else min(self._ap_low_ft, a)
        self.traffic.update(dt)
        self.course.update(self.ac, dt)
        if self.course.passed:
            self.course.passed = False
            self.audio.chime()
        self.charter.update(self.ac, dt)
        if self.charter.event:
            if self.charter.event == 'fail':
                self.audio.fail()
            else:
                self.audio.chime()
            self.charter.event = ''
        self._fuel(dt)
        if self.birds.update(self.ac, dt, self.birds_on):
            self._bird_strike()
        if not self.ac.on_ground:
            self.air_time += dt
        self.tod_t += dt
        self._sights()
        self._callouts()
        self.atc.update(dt)
        self._atc_calls()
        self._turbulence(dt)
        self._lightning(dt)
        self.effects.update(dt)
        if self.ac.on_ground:
            self.effects.rolling(self.ac.x, self.ac.y, self.ac.hdg, self.ac.V,
                                 dt, self.raining)
        if self.ac.on_ground and not self._was_ground:
            self.effects.touchdown(self.ac.x, self.ac.y, self.ac.hdg,
                                   self.ac.touchdown_vs, self.ac.V, self.raining)
            if self._appr_from > 50.0:
                # 進入して降りてきたときだけ。離陸中に跳ねただけでは言わない
                self.atc.say('g_retard', 'g_retard')
            self.audio.touchdown(self.ac.touchdown_vs)
            self.shake = min(2.8, abs(self.ac.touchdown_vs) * 0.9)
            if self.ac.last_landing:
                r = self.ac.last_landing
                self.landing_log.append(r)
                del self.landing_log[:-8]
                self.stats['count'] += 1
                self.stats['total'] += r['score']
                self.stats['best'] = max(self.stats['best'], r['score'])
                a = r['apt']
                self.apt_best[a] = max(self.apt_best.get(a, 0), r['score'])
                self.charter.arrive(r)
                self._hurt = self.career.touchdown(r)   # ダメージだけ先に
                self._pending = r          # 精算は完全に止まってから
                if not r['on_rwy']:
                    self._recover = True      # 滑走路の外。自力では戻れない
                self.save_settings()
        if self._pending is not None:
            if not self.ac.on_ground:
                self._pending = None       # タッチアンドゴーは到着ではない
            elif self.ac.kias < 1.0:
                self._settle_landing()
        if self._recover and self.ac.on_ground and self.ac.kias < 1.0:
            self._recover_now()
        if self._was_ground and not self.ac.on_ground:
            self._ap_low_ft = None     # 離陸したら数え直す
        self._was_ground = self.ac.on_ground

    def burn_rate(self):
        """スロットル1.0あたりの消費[%/秒]。設定した航続時間から逆算する。

        機体ごとに燃費と搭載量が違うので、その比で伸び縮みする。
        """
        i = 0 if self.career.on else self.endurance_i   # キャリアは10分基準
        s = self.career.spec
        base = FUEL_MAX / (ENDURANCE[i] * 60.0 * (1.0 + IDLE_FRAC))
        # エンジンを整備するほど燃費が良くなる（5段で15%減）
        import career as _c
        eco = 1.0 - _c.UP_GAIN['ENGINE'] * self.career.up_rank('ENGINE')
        return base * s['burn'] / s['tank'] * eco

    def endurance_left(self):
        """いまのスロットルのままなら燃料が尽きるまで何秒か。"""
        r = (IDLE_FRAC + self.ac.throttle) * self.burn_rate()
        return self.fuel / r if r > 1e-6 else 9e9

    def _fuel(self, dt):
        """燃料を減らす。尽きればエンジン停止。地上で停止＋ブレーキなら給油。"""
        ac = self.ac
        if ac.engine > 0.01 and self.fuel > 0.0:
            # アイドルでもいくらかは食う
            self.fuel = max(0.0, self.fuel
                            - (IDLE_FRAC + ac.throttle) * dt * self.burn_rate())
            if self.fuel <= 0.0:
                ac.engine = 0.0
                self.career.hurt('ENGINE', 8.0)
                ac._say('FUEL EXHAUSTED - ENGINE OUT', 300)
                self.audio.warn()
            else:
                for lv in (20.0, 10.0, 5.0):
                    if self._fuel_warn > lv >= self.fuel:
                        # 残量だけでは切迫感が分からないので残り時間も出す
                        ac._say('FUEL LOW  %d PCT  %d MIN LEFT'
                                % (int(lv), max(1, int(round(
                                    self.endurance_left() / 60.0)))), 240)
                        self.audio.warn()
                        self.atc.say('g_fuel')
            self._fuel_warn = self.fuel
        if ac.on_ground and ac.V < 1.0 and ac.brake:
            if self.fuel < FUEL_MAX:
                want = min(dt * 14.0, FUEL_MAX - self.fuel)
                if self.career.on:
                    before = self.career.credits
                    want = self.career.buy_fuel(want)   # キャリアは有料
                    self._fuel_spent += before - self.career.credits
                    if want <= 1e-6:
                        self._no_fuel_money()
                self.fuel += want
                self._fuel_warn = self.fuel
                if self.fuel >= FUEL_MAX:
                    # いくら払ったかを出す。無言で引かれると気づけない
                    if self.career.on and self._fuel_spent >= 1.0:
                        ac._say('REFUELLED  -%d CR' % round(self._fuel_spent), 200)
                    else:
                        ac._say('REFUELLED - ENGINE READY', 150)
                    self._fuel_spent = 0.0
                    self.career.save()
            if ac.engine < 1.0 and self.fuel > 1.0:
                ac.engine = 1.0

    def _settle_landing(self):
        """完全に止まってから精算する。

        接地の瞬間はまだ転がっているので、金額やレベルの文字を読めない。
        止まってから、収支をリザルト画面にまとめて出す。
        """
        r, self._pending = self._pending, None
        job = self.board.active
        job_xp = job.xp if job else 0
        job_name = job.title_t() if job else ''
        job_origin = job.origin if job else ''
        job_t = job.t if job else 0.0
        cr0 = int(self.career.credits)
        lv0 = self.career.level
        xp0 = self.career.xp
        job_pay, note = self.board.landed(r)
        if not job_pay:
            job_xp, note = 0, (note or '')
        hand_f, hand_fmt, hand_arg = self.hand_flown()
        got, hand_pay, lv = 0, 0, 0
        if self.career.on:
            got, hand_pay, lv = self.career.settle(r, hand_f, self.hand_tough())
            if job_pay:
                # 交渉・拠点・荒天の割増をまとめて掛ける
                mul = ((1.0 + self.career.sk('DEAL'))
                       * self.career.base_pay(job_origin)
                       * self.career.storm_pay(self.wind_info()[1],
                                               self.wind.shear_on))
                job_pay = int(round(job_pay * mul))
                job_xp = int(round(job_xp * (1.0 + self.career.sk('LOG'))))
                self.career.credits += job_pay
                self.career.add_xp(job_xp)
                lv = self.career.level_up or lv
                self.career.level_up = 0
            self.career.save()
            self.roll_weather()
        saved = 0
        if self.board.free_fuel:
            self.board.free_fuel = False       # 回送は燃料込み
            miss = FUEL_MAX - self.fuel
            if miss > 0.5:
                saved = self.career.fuel_cost(miss)
                self.fuel = FUEL_MAX
                self._fuel_warn = FUEL_MAX
        hurt, self._hurt = self._hurt, 0.0
        if lv:
            self.audio.level_up()
        # 次の離陸に備えて、フラップとトリムを戻しておく。
        # 降ろしたままだと気づかずに離陸してしまう
        self.ac.flap_i = 0
        self.ac.trim = 0.0
        r['hand'] = hand_f          # 飛行記録にも手動かどうかを残す
        if hand_f >= 0.999 and r['on_rwy']:
            self.stats['hand'] = self.stats.get('hand', 0) + 1
            self.save_settings()
        hand = (hand_f, hand_fmt, hand_arg, hand_pay)
        if self.result_on:
            self._show_result(r, got, job_pay, job_name, job_t, saved,
                              cr0, xp0, lv0, hurt, note, hand)
        elif self.career.on:
            self.banner = self._banner_line(r, got, job_pay, job_xp, saved,
                                            hurt, lv, hand)
            self.banner_t = 420
        self._ap_low_ft = None

    def hand_flown(self):
        """着陸をどれだけ手で飛ばしたか (割合0..1, 表示用の書式, 引数)。

        APを使っていなければ満点。低い高度まで任せるほど割合が下がる。
        """
        a = self._ap_low_ft
        if a is None:
            return 1.0, 'HAND FLOWN', None
        f = max(0.0, min(1.0, (a - HAND_LOW_FT) / (HAND_HIGH_FT - HAND_LOW_FT)))
        if f >= 0.999:
            return 1.0, 'HAND FLOWN', None
        if f <= 0.0:
            return 0.0, 'AUTOLAND', None
        return f, 'AP TO %d FT', int(round(a))

    def hand_tough(self):
        """手動着陸の値打ち。横風・雨・夜で上がる 1.0〜1.8。

        悪天候ほど手で降ろす価値が上がる。裏返せば、悪天候でILSを使うのは
        「報酬を捨てて安全を買う」まっとうな判断になる。
        """
        t = min(0.45, abs(self.wind_info()[3]) / 18.0 * 0.45)
        if self.raining:
            t += 0.20
        if self.tod_now()[0] in ('dusk', 'night'):
            t += 0.15
        return 1.0 + min(0.8, t)

    def _banner_line(self, r, got, job_pay, job_xp, saved, hurt, lv, hand):
        """リザルト画面を切っているときの、1行版の精算表示。"""
        parts = ['%dP' % r['score']]
        if got:
            parts.append('+%d CR' % got)
        if hand[3]:
            parts.append('HAND +%d' % hand[3])
        if job_pay:
            parts.append('JOB +%d' % job_pay)
            parts.append('+%d XP' % job_xp)
        if saved:
            parts.append('FUEL FREE (-%d CR)' % saved)
        if hurt > 0.5:
            parts.append('DMG %d%%' % round(hurt))
        if lv:
            parts.append('LV UP %d' % lv)
        return '  '.join(parts)

    def _show_result(self, r, got, job_pay, job_name, job_t, saved,
                     cr0, xp0, lv0, hurt, note, hand):
        """リザルト画面に出す内訳を組み立てる。"""
        rows, bonus = [], []
        if self.career.on:
            if got:
                rows.append(('LANDING PAY', '', '+%d CR' % got,
                             result_mod.PLUS))
            elif not r['on_rwy']:
                rows.append(('LANDING PAY', '', 'OFF RUNWAY',
                             result_mod.MINUS))
            if hand[3]:
                rows.append(('HAND FLOWN BONUS', '', '+%d CR' % hand[3],
                             result_mod.PLUS))
            if job_pay:
                # 表示のときに訳すので、題名と所要時間は分けて持つ
                extra = ('  %s' % result_mod._mmss(job_t)) if job_t > 0 else ''
                rows.append((job_name, extra, '+%d CR' % job_pay,
                             result_mod.PLUS))
            if saved:
                bonus.append(('FUEL INCLUDED', 'SAVED %d CR', saved))
        tot = int(round(sum(self.career.dmg.values())))
        self.result.show({
            'apt': r['apt'], 'grade': r['grade'], 'on_rwy': r['on_rwy'],
            'score': r['score'], 'detail': aircraft_mod.score_parts(r),
            'hand': hand[:3],
            'career': self.career.on,
            'rows': rows, 'bonus': bonus,
            'cr0': cr0, 'cr1': int(self.career.credits),
            'xp': self.career.xp - xp0,
            'lv0': lv0, 'lv1': self.career.level,
            'need': self.career.next_level(),
            'dmg': None if self.career.rented else (hurt, tot),
            'note': ((note.strip(), bool(job_pay)) if note.strip() else None),
        })

    def _recover_now(self):
        """滑走路外で止まった機体を、最寄りの空港へ運んでもらう。

        草地からそのまま離陸できてしまうと、着陸をやり直す意味が無くなる。
        """
        self._recover = False
        ac = self.ac
        ap = world.nearest_airport(ac.x, ac.y)
        fee = self.career.recover()
        ac.place_at(ap)
        self.effects.clear()
        lost = ''
        if self.board.active is not None:
            self.board.abandon()
            lost = ' - JOB LOST'
        if fee:
            ac._say('RECOVERED TO %s  -%d CR%s'
                    % (world.apt_short(ap.name), fee, lost), 260)
        else:
            ac._say('RECOVERED TO %s%s'
                    % (world.apt_short(ap.name), lost), 260)

    def _no_fuel_money(self):
        """給油したいが金が足りないとき。何度も出さない。"""
        if self.ac.msg_t <= 0:
            self.ac._say('NO CREDITS FOR FUEL', 180)

    def _bird_strike(self):
        """バードストライク。出力が落ちて機体が揺れる。"""
        ac = self.ac
        ac.engine = min(ac.engine, 0.45)
        self.career.hurt('ENGINE', 22.0)
        ac._say('BIRD STRIKE - POWER LOSS', 260)
        self.audio.warn()
        self.shake = max(self.shake, 1.6)
        self.audio.touchdown(2.0)

    # 時刻ごとの星の見え具合（0=見えない, 1=満天）
    STAR = {'day': 0.0, 'golden': 0.0, 'dusk': 0.35, 'night': 1.0}

    @classmethod
    def _star_amount(cls, tod, blend, t):
        a = cls.STAR[tod]
        if blend is None:
            return a
        return a + (cls.STAR[blend] - a) * t

    @classmethod
    def _sun(cls, tod, blend, t):
        """混ぜている最中の太陽の位置。片方が夜なら近いほうに寄せる。"""
        a = cls.SUN[tod]
        if blend is None or t <= 0.0:
            return a
        b = cls.SUN[blend]
        if a is None or b is None:
            return a
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    ATC_INBOUND = 500.0      # このユニット以内で「inbound」を送る
    ATC_FINAL = 200.0        # このユニット以内で「final」を送る

    def _atc_calls(self):
        """離陸・進入・着陸の場面に合わせて管制通信を流す。"""
        ac = self.ac
        if not self.atc.ok:
            return
        ap = world.nearest_airport(ac.x, ac.y)
        end = ap.approach_end(ac.x, ac.y)
        rw = end[2]
        if ac.on_ground:
            if self._atc_ph in ('air', 'inbound', 'final') and ac.kias < 20.0:
                self.atc.say('t_exit')            # 着陸して減速したら
                self._atc_ph = 'ramp'
            elif self._atc_ph == 'ramp' and ac.throttle > 0.55 and ac.kias < 12.0:
                self.atc.say('p_ready_%s' % rw, 't_takeoff_%s' % rw)
                self._atc_ph = 'roll'
            return
        if self._atc_ph in ('ramp', 'roll'):
            if ac.alt_ft > 700.0:
                self.atc.say('t_departure')
                self._atc_ph = 'air'
            return
        if self.pilot.phase == 'GOAROUND' and self._atc_ph == 'final':
            self.atc.say('t_goaround', 'p_roger')
            self._atc_ph = 'air'
            return
        d = ap.dist_to_threshold(end, ac.x, ac.y)
        lat = (ac.x - ap.c) if ap.axis == 'NS' else (ac.y - ap.c)
        hd = abs((end[1] - math.degrees(ac.hdg) + 540.0) % 360.0 - 180.0)
        if self._atc_ph == 'air':
            if 0.0 < d < self.ATC_INBOUND and ac.alt_ft < 2500.0 and hd < 60.0:
                self.atc.say('p_inbound', 't_downwind')
                self._atc_ph = 'inbound'
        elif self._atc_ph == 'inbound':
            if (0.0 < d < self.ATC_FINAL and abs(lat) < 22.0 and hd < 35.0
                    and ac.alt_ft < 1300.0):
                self.atc.say('p_final_%s' % rw, 't_land_%s' % rw)
                self._atc_ph = 'final'

    APPR_D = (-60.0, 300.0)   # 滑走路端までの距離[ユニット]。負は滑走路上
    APPR_LAT = 20.0           # 中心線からの許容横ずれ（約160m）
    APPR_HDG = 35.0           # 滑走路方位との許容差[deg]

    def on_approach(self):
        """滑走路の進入路に乗っているか。

        高度コールはこのときだけ出す。滑走路と関係のない低空飛行や
        離陸直後に「10 ft」と言われても意味がない。
        """
        ac = self.ac
        if ac.on_ground:
            return False
        ap = world.nearest_airport(ac.x, ac.y)
        end = ap.approach_end(ac.x, ac.y)
        d = ap.dist_to_threshold(end, ac.x, ac.y)
        if not (self.APPR_D[0] < d < self.APPR_D[1]):
            return False
        lat = (ac.x - ap.c) if ap.axis == 'NS' else (ac.y - ap.c)
        if abs(lat) > self.APPR_LAT:
            return False
        hd = (end[1] - ac.hdg_deg + 540.0) % 360.0 - 180.0
        return abs(hd) <= self.APPR_HDG

    CALL_FT = (500, 200, 100, 50, 30, 10)    # 進入中に鳴らす対地高度

    def _callouts(self):
        """進入中、決められた高度を切るたびに短く鳴らす。"""
        ac = self.ac
        if ac.on_ground:
            self._calls.clear()
            # 接地した直後は進入高度を残す（Retardの判定に使う）。
            # 止まるか、次の離陸で出力を上げたら忘れる
            if ac.kias < 5.0 or ac.throttle > 0.5:
                self._appr_from = 0.0
            return
        if ac.alt_ft > 600.0 or not self.on_approach():
            self._calls.clear()
            self._appr_from = 0.0
            return
        if self._appr_from <= 0.0:
            # 進入路に入ったときの高度。ここより上のコールは鳴らさないので、
            # 滑走路上で浮いただけの離陸直後に「10 ft」とは言わない
            self._appr_from = ac.alt_ft
        if ac.vs_fpm > -60.0:                     # 降りているときだけ
            return
        for ft in self.CALL_FT:
            if ft not in self._calls and ac.alt_ft <= ft <= self._appr_from:
                self._calls.add(ft)
                if self.atc.ok and self.atc.on and self.atc.volume:
                    self.atc.say('g_%d' % ft)
                else:
                    self.audio.blip()
                break
        # 低空で沈み込みが強いときの警告
        self._sink_t = max(0.0, self._sink_t - self.dt)
        if ac.alt_ft < 450.0 and ac.vs_fpm < -1250.0 and self._sink_t <= 0.0:
            self._sink_t = 5.0
            self.atc.say('g_sinkrate')

    SIGHT_ALT = 900.0        # これより高いと見どころは通過扱いにしない

    def _sights(self):
        """見どころの上空を通ったら記録する。高すぎると素通り扱い。"""
        ac = self.ac
        if ac.on_ground or ac.alt > self.SIGHT_ALT:
            return
        for lm in world.LANDMARKS:
            if lm.name in self.visited:
                continue
            if math.hypot(lm.x - ac.x, lm.y - ac.y) < lm.radius:
                self.visited.add(lm.name)
                ac._say('OVER %s  (%d/%d)'
                        % (lm.name, len(self.visited), len(world.LANDMARKS)), 200)
                self.audio.chime()
                self.save_settings()
                break

    CH_BACK, CH_UP, CH_LAG = 8.0, 1.6, 3.0     # 外部視点の後方/上方/追従の速さ

    def _chase(self):
        """外部視点。機体の後ろ上方から見る。カメラは遅れて付いてくる。"""
        ac = self.ac
        tx = ac.x - math.sin(ac.hdg) * self.CH_BACK
        ty = ac.y - math.cos(ac.hdg) * self.CH_BACK
        tz = max(1.1, ac.alt_units + self.CH_UP)
        if self.cam is None:
            self.cam = [tx, ty, tz]
        else:
            k = min(1.0, self.dt * self.CH_LAG)
            self.cam[0] += (tx - self.cam[0]) * k
            self.cam[1] += (ty - self.cam[1]) * k
            self.cam[2] += (tz - self.cam[2]) * k
        cx, cy, cz = self.cam
        dx, dy = ac.x - cx, ac.y - cy
        d = math.hypot(dx, dy)
        hdg = math.degrees(math.atan2(dx, dy)) if d > 1e-3 else ac.hdg_deg
        pitch = math.degrees(math.atan2(ac.alt_units - cz, max(d, 0.2)))
        me = dict(model=objects.PLANE, pos=(ac.x, ac.y, ac.alt_units),
                  yaw=ac.hdg_deg, scale=1.15, lights=objects.PLANE_LIGHTS,
                  bank=math.degrees(ac.roll), nose=math.degrees(ac.pitch),
                  shadow=1.2 if ac.alt < 260.0 else 0.0)
        # 水平線を少しだけ機体に合わせて傾けると、旋回の勢いが出る
        return (cx, cy, cz), pitch, -hdg, math.degrees(ac.roll) * 0.22, me

    def roll_weather(self):
        """キャリアの空模様。選ぶものではなく、その日に与えられるもの。

        持っている資格の範囲でしか荒れない。夜間資格が無ければ夜は来ないし、
        計器飛行資格が無ければ雨も低視程も来ない。
        """
        r = self.career.rnd
        c = self.career
        pool = [0, 0, 0, 1]
        if c.has_rating('NIGHT'):
            pool += [2, 3]
        self.tod_i = r.choice(pool)
        self.clouds = r.random() < 0.8
        ifr = c.has_rating('IFR')
        self.raining = ifr and self.clouds and r.random() < 0.28
        if not ifr:
            self.vis = 0
        else:
            self.vis = 0 if r.random() < 0.6 else (1 if r.random() < 0.6 else 2)
        # 風はレベルで頭打ちにする。20ktを超える風は操縦が難しい
        self.wind.set_level(r.choice(c.wind_pool()))
        self.wind.direction = r.uniform(0.0, 360.0)
        self.wind.shear_on = c.shear_ok()

    def cloud_span(self):
        """雲底と雲頂[ユニット]。雲を切っていれば遥か上を返す。"""
        if not self.clouds or self.tod_now()[0] == 'night':
            return 9e5, 9e5
        base = RAIN_BASE if self.raining else CLOUD_BASE
        return base, base + (CLOUD_TOP - CLOUD_BASE)

    def _turbulence(self, dt):
        """風と高度から機体を揺さぶる。雲の中と低空でとくに荒れる。"""
        ac = self.ac
        base, top = self.cloud_span()
        in_cloud = base <= ac.alt_units <= top
        rr, pp, sh = weather.turbulence(self.wind.speed(), ac.alt, in_cloud,
                                        self.raining,
                                        self.simt, ac.V, ac.on_ground)
        # 荒天運航は風そのものは弱めない。荒れた空に慣れて煽られにくくなる
        calm = 1.0 - 0.30 * self.career.sk('STORM')
        rr, pp, sh = rr * calm, pp * calm, sh * calm
        self.turb_shake = sh
        if rr or pp:
            ac.roll += math.radians(rr) * dt
            ac.pitch += math.radians(pp) * dt

    def _lightning(self, dt):
        """雨天のとき、たまに稲光。近さに応じて遅れて雷鳴が鳴る。"""
        self.flash *= 0.82 ** (self.fscale * self.time_mult())
        if self.thunder_t > 0.0:
            self.thunder_t -= dt
            if self.thunder_t <= 0.0:
                self.audio.thunder(self.thunder_n)
        if not (self.raining and self.clouds and self.lightning_on):
            return
        if self.rnd.random() < dt * 0.055:          # 平均18秒に1回
            self.thunder_n = self.rnd.random() ** 2   # 近い雷はまれ
            self.flash = 0.30 + self.thunder_n * 0.70
            self.thunder_t = 0.35 + (1.0 - self.thunder_n) * 6.5

    def wind_info(self):
        """(風向, 風速kt, 正面成分kt, 横風成分kt)。滑走路基準の成分も返す。"""
        ap = world.nearest_airport(self.ac.x, self.ac.y)
        end = ap.approach_end(self.ac.x, self.ac.y)
        head, cross = self.wind.component(end[1])
        return (self.wind.eff_dir, self.wind.speed() * 1.94384, head, cross)

    GUIDE_D = 900.0          # この距離まで近づいたら進入の輪を出す

    def approach_airport(self):
        """いま降りようとしている空港。仕事があればその目的地。"""
        j = self.board.active if self.career.on else None
        if j is not None:
            if j.dest is not None:
                return j.dest
            if j.kind in ('TOUR', 'SEARCH', 'SURVEY') and not j.ready():
                return None          # まだ仕事の途中
            return next((a for a in world.AIRPORTS if a.name == j.origin), None)
        # 仕事が無ければ「向かっている空港」に降りるものとみなす。
        # 単に最寄りを取ると、通り過ぎた空港の輪が出てしまう
        ac = self.ac
        best = None
        for a in world.AIRPORTS:
            d = math.hypot(a.x - ac.x, a.y - ac.y)
            brg = math.degrees(math.atan2(a.x - ac.x, a.y - ac.y))
            off = abs((brg - ac.hdg_deg + 540.0) % 360.0 - 180.0)
            if off > 80.0 and d > 120.0:          # 後ろ側の空港は対象外
                continue
            if best is None or d < best[0]:
                best = (d, a)
        return best[1] if best else world.nearest_airport(ac.x, ac.y)

    def _approach_guide(self):
        """進入経路の輪を出すかどうか。(空港, 滑走路端) か None。"""
        ac = self.ac
        if not self.app_guide or ac.on_ground:
            return None
        ap = self.approach_airport()
        if ap is None or not hasattr(ap, 'ends'):
            return None
        if math.hypot(ap.x - ac.x, ap.y - ac.y) > self.GUIDE_D:
            return None
        return (ap, ap.approach_end(ac.x, ac.y))

    def nav_point(self):
        """いま向かうべき地点 (名前, x, y)。

        仕事を受けているあいだは、その目標を自動で指す。手で選び直さなくてよい。
        """
        name = None
        j = self.board.active if self.career.on else None
        if j is not None:
            t = j.nav_target()
            if t is not None:
                name, tx, ty = t
                if tx is None:                       # 空港名で指定された場合
                    ap = next((a for a in world.AIRPORTS if a.name == name), None)
                    if ap is not None:
                        tx, ty = ap.x, ap.y
                if tx is None:
                    name = None
        if name is None:
            d = world.DESTS[self.dest_i]
            name, tx, ty = d.name, d.x, d.y
        return name, tx, ty

    def nav(self):
        """目的地までの距離[km]と方位[deg]。"""
        name, tx, ty = self.nav_point()
        dx, dy = tx - self.ac.x, ty - self.ac.y
        return (name, math.hypot(dx, dy) * 8.0 / 1000.0,
                math.degrees(math.atan2(dx, dy)) % 360.0)

    def show_brief(self, job=None, index=None):
        """仕事の打ち合わせを出す。

        index を渡すと「受ける／やめておく」を尋ね、受けたときだけ受注する。
        損耗の警告を聞いてから整備へ引き返せるようにするため。
        index が無ければ受注済みの仕事の読み直し。
        """
        import dialogue
        job = job or self.board.active
        if job is None:
            return False
        at = self.board.at or world.nearest_airport(self.ac.x, self.ac.y).name
        lines = dialogue.brief(job, self, at)
        if index is None:
            self.brief.show(lines)
            return True

        def take():
            if not self.board.accept(index, self.career.spec['cap']):
                return None
            return dialogue.accepted(job)

        self.brief.show(lines, on_accept=take,
                        on_decline=lambda: dialogue.declined(self.career))
        return True

    def ap_target(self):
        """巡航モードで向かう先。遊覧に設定していれば None（気ままに飛ぶ）。

        キャリアでは仕事の最中なので、あてもなく飛ばれても困る。常に行き先へ。
        """
        if not (self.career.on or self.ap_nav):
            return None
        _n, tx, ty = self.nav_point()
        return (tx, ty)

    def view_shake(self):
        """接地の衝撃と滑走中の振動。視点のピッチ・ロールを揺らす[deg]。"""
        ac = self.ac
        amp = self.shake + self.turb_shake
        if ac.on_ground and ac.V > 1.5:
            amp += min(0.22, ac.V * 0.008)      # 滑走路のごつごつ
        if amp < 0.01:
            return 0.0, 0.0
        f = self.frames * self.fscale
        dp = (math.sin(f * 1.93) * 0.75 + math.sin(f * 0.71) * 0.30) * amp
        dr = (math.sin(f * 2.67) * 1.05 + math.sin(f * 1.13) * 0.42) * amp
        return dp, dr

    def state(self):
        ac = self.ac
        tod, tod_b, tod_t = self.tod_now()
        shake_p, shake_r = self.view_shake()
        ap = world.nearest_airport(ac.x, ac.y)
        end = ap.approach_end(ac.x, ac.y)
        night = tod in ('dusk', 'night')
        # 夜は雲を白く光らせても不自然なので層ごと畳む
        base = CLOUD_BASE if (self.clouds and tod != 'night') else 9e5
        if self.raining and self.clouds and tod != 'night':
            base = RAIN_BASE                      # 雨天は雲底が低く垂れ込める
        cam = (ac.x, ac.y, ac.alt_units)
        v_pitch = math.degrees(ac.pitch) + ac.dip + shake_p
        v_hdg = -ac.hdg_deg                       # 描画側は方位の符号が逆
        v_roll = math.degrees(ac.roll) + shake_r
        me = None
        if self.view_i == 2:
            cam, v_pitch, v_hdg, v_roll, me = self._chase()
        if self.look:
            v_hdg -= self.look          # 右を向くと世界は左へ回る
        S = self._state
        S.update(
            cam=cam,
            pitch=v_pitch,
            hdg=v_hdg,
            hdg_disp=ac.hdg_deg,
            roll=v_roll,
            tod=tod, tod_blend=tod_b, tod_t=tod_t,
            ground=3 if tod == 'night' else 0,
            base=base, top=base + (CLOUD_TOP - CLOUD_BASE),
            cloud_tm=4 if self.raining else 1,
            stars=self._star_amount(tod, tod_b, tod_t),
            star_phase=self.frames * self.fscale / 60.0,
            sun=self._sun(tod, tod_b, tod_t),
            sun_disc=7 if tod == 'golden' else 5,
            haze=(1.3 if self.raining else 0.95) * VIS_HAZE[self.vis],
            haze_scale=VIS_SCALE[self.vis], fog=VIS_FOG[self.vis],
            shadows=(tod == 'day') and not self.raining,
            msg=ac.msg if ac.msg_t > 0 else '',
            # 夜も白のまま。暗い色にすると霧（3番）と同化して見えなくなる
            rain=(self.rain, 12) if self.raining else None,
            # 滑走路灯・PAPI・進入灯は常時点灯（実際の空港と同じ）。
            # 時刻で消えると、進入中に目標を見失って不自然になる。
            lights=True, als=True,
            # にじむ光の輪は夜と低視程のときだけ
            glow=night or self.vis == 2,
            als_phase=int(self.frames * self.fscale) // 4,
            objects=True, ap=ap, end=end, nav=self.nav(), rwy=end[2],
            traffic=self.traffic.objects((ac.x, ac.y, 0)),
            # 自機はカメラのすぐ前にいるので、霧や着陸灯より後に描く
            self_plane=me,
            course=self.course, job=self.board.active if self.career.on else None,
            approach_guide=self._approach_guide(), look=self.look,
            effects=(self.effects, self.birds),
            land_light=(ac if (self.land_light and (night or self.vis == 2))
                        else None),
            wiper=(self.wiper, 5 if night else 0) if self.raining else None,
            bird_phase=self.frames * self.fscale / 60.0,
            detail=self.detail, wind_dir=self.wind.direction,
            wind=self.wind_info(),
            kt=int(ac.kias), ft=int(ac.alt_ft), fpm=int(ac.vs_fpm),
            rpm=ac.rpm, flap=ac.flap, fuel=int(self.fuel), thr=ac.throttle,
            brake=ac.brake, stall=ac.stalled, trim=math.degrees(ac.trim),
            eng_bad=self.career.on and self.career.dmg['ENGINE'] > 30.0,
            rudder=ac.rudder, pilot=self.pilot,
            vs0=ac.stall_kt,
            prop=int(self.frames * self.fscale * 47) % 360,
        )
        return S

    # ------------------------------------------------------------ 描画
    def _autotune(self, interval):
        """初回起動時だけ実速度を測り、60FPSが出ないなら30FPSを設定して知らせる。"""
        if self._probe is None:
            return
        self._probe.append(interval)
        if len(self._probe) < self.fps * 3:      # 3秒ぶん貯める
            return
        avg = len(self._probe) / sum(self._probe)
        self._probe = None
        if self.fps == 60 and avg < 45.0:
            self.fps = 30
            self.save_settings()
            self.ac._say('SLOW (%d FPS) - SET 30FPS, RESTART TO APPLY' % avg, 600)

    def _title_update(self):
        """タイトル画面。少し待ってから、どのボタンでも始める。"""
        self.title_t += self.dt
        if self.title_t <= 0.4:
            return
        # capture() は修飾キー単独を拾わないので、そこだけ足す。
        # MODIFIERS には軸の修飾（L2）がタプルで入るので、キーだけを見る。
        if im.capture() or any(pyxel.btnp(m) for m in im.MODIFIERS
                               if isinstance(m, int)):
            self.title_t = None
            fx.invalidate()            # タイトル用パレットを捨てる
            self.imap.clear()

    def draw(self):
        if self.title_t is not None:
            title_mod.draw(W, H)
            return
        t0 = time.perf_counter()
        if self._probe is not None:
            n = time.perf_counter()
            if self._probe_last:
                self._autotune(n - self._probe_last)
            self._probe_last = n
        S = self.state()
        if self.view_i == 0:
            cockpit.view(S)
        else:
            scene.draw_scene(RECT, S)
            if self.raining:
                self.rain.draw(RECT, S['rain'][1])
                # ワイパーは風防のものなので外部視点では出さない
                if self.view_i == 1:
                    self.wiper.draw(RECT, S['wiper'][1])
            hud.draw(RECT, self.ac, 'TRM%+4.1f' % math.degrees(self.ac.trim),
                     S['nav'], S['wind'], self.course, self.pilot,
                     chase=(self.view_i == 2 or abs(self.look) > 4.0),
                     look=self.look, charter=self.charter,
                     job=(self.board if self.career.on else None))
        if self.banner_t > 0:
            bw = len(self.banner) * 4
            by = (cockpit.GLASS[3] - 24) if self.view_i == 0 else (H - 44)
            pyxel.rect(W // 2 - bw // 2 - 3, by, bw + 5, 9, 0)
            pyxel.rectb(W // 2 - bw // 2 - 3, by, bw + 5, 9, 14)
            pyxel.text(W // 2 - bw // 2, by + 2, self.banner, 14)
        if self.flash > 0.03:
            pyxel.dither(min(0.85, self.flash))
            pyxel.rect(0, 0, W, H, 12)
            pyxel.dither(1.0)
        if self.paused:
            pyxel.rect(W // 2 - 22, 84, 44, 11, 0)
            pyxel.text(W // 2 - 10, 87, 'PAUSED', 12)
        if self.result.open:
            self.result.draw()
        if self.brief.open:
            self.brief.draw()
        if self.show_fps:
            now = time.perf_counter()
            self._t_draw += (now - t0 - self._t_draw) * 0.08
            if self._t_last:
                # 実際のフレーム間隔（Pyxel内部の画面転送と待ちも含む）
                self._steps.append(now - self._t_last)
                if len(self._steps) > 60:
                    del self._steps[0]
            self._t_last = now
            if self._steps:
                tot = sum(self._steps)
                fps = len(self._steps) / tot if tot > 0 else 0.0
                worst = max(self._steps) * 1000.0
            else:
                fps, worst = 0.0, 0.0
            good = self.fps - 5
            t = '%4.1f/%4.1fFPS W%4.1f' % (self._t_draw * 1000.0,
                                            min(fps, 999.0), min(worst, 99.9))
            pyxel.rect(W - 100, 0, 100, 8, 0)
            pyxel.text(W - 97, 1, t,
                       11 if fps > good else (14 if fps > good * 0.7 else 13))
        if self.menu.open:
            self.menu.draw()
        elif self.frames < 240:
            t = 'TAB / START : OPTION MENU'
            pyxel.rect(2, 2, len(t) * 4 + 4, 9, 0)
            pyxel.text(4, 4, t, 11)


if __name__ == '__main__':
    App().run()
