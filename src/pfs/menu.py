"""オプションメニュー。キーマップ・音声・天候・位置リセットなどをここで操作する。"""
import pyxel
import fx
import input_map as im
import bgm
import lang


def main_vis(app):
    import main
    return main.VIS_NAMES[app.vis]


def _endurance(app):
    import main
    return main.ENDURANCE[app.endurance_i]


def _aspect(app):
    import main
    return main.ASPECTS[app.aspect_i][0]


def _fleet_name(pid):
    import fleet
    return fleet.spec(pid)['name']


def _jobs(app):
    j = app.board.active
    if j is None:
        return '%d %s' % (len(app.board.jobs), lang.T('AVAILABLE'))
    if j.limit:
        t = j.left()
        return '%s %d:%02d' % (j.kind[:6], int(t) // 60, int(t) % 60)
    return j.kind[:8]


def _charter(app):
    c = app.charter
    if c.active:
        return '%s %d:%02d' % (c.dest.name[:6], int(c.left()) // 60,
                               int(c.left()) % 60)
    return 'ACCEPT'


def _speed(app):
    import main
    n = main.TIME_MULT[app.speed_i]
    if n == 1:
        return 'NORMAL'
    return 'x%d%s' % (n, '' if app.time_mult() > 1 else ' (CRUISE)')


def _tod_speed(app):
    import main
    if main.App.TODS[app.tod_i] != 'auto':
        return '-'
    return '%d %s' % (round(main.TOD_PERIOD[app.tod_speed_i] / 60.0),
                      lang.T('MIN'))

W, H = 256, 192
BG, FG, SEL, DIM, ACC = 0, 11, 14, 5, 12
# 5(副文)と1(選択バー)は時刻パレットでは地表と空の色で、夜になると背景と
# ほぼ同じ明るさになり読めなくなる（夜のコントラスト比は 1.01:1 と 1.00:1）。
# リザルト画面と同じように、メニューを出している間だけ固定した色を借りて、
# 閉じるときに fx.invalidate() で時刻のパレットへ戻す。
SELBAR = 1
UI_COLS = ((DIM, 0x5a6a78), (SELBAR, 0x24365e))
DETAIL = ('LOW', 'MEDIUM', 'HIGH')
ROWS = 11


def set_size(w, h):
    global W, H, ROWS
    W, H = w, h
    ROWS = max(6, (h - 56) // 12)
TITLES = {'main': 'OPTIONS', 'flight': 'FLIGHT', 'weather': 'WEATHER',
          'gfx': 'GRAPHICS', 'audio': 'AUDIO', 'controls': 'CONTROLS',
          'keys': 'KEY MAPPING', 'reset': 'RESET POSITION', 'help': 'HELP',
          'log': 'LANDING LOG', 'hangar': 'HANGAR', 'fleet': 'AIRCRAFT',
          'jobs': 'JOB BOARD', 'ratings': 'RATINGS', 'shop': 'SHOP',
          'upgrade': 'AIRCRAFT UPGRADES', 'skills': 'PILOT SKILLS',
          'about': 'ABOUT'}
SEC = '_sec'                 # 見出し行の目印（選べない）
PINNED = ('shop', 'fleet', 'ratings', 'upgrade', 'skills')   # 所持金を固定表示するページ
SUBPAGES = ('flight', 'weather', 'gfx', 'audio', 'controls', 'keys', 'reset',
            'help', 'log', 'hangar', 'fleet', 'jobs', 'ratings', 'shop',
            'upgrade', 'skills', 'about')


def _f():
    """メニュー用フォント。無ければ組み込みフォント。"""
    return lang.font()


def _txt(x, y, s, col):
    pyxel.text(x, y, s, col, _f())


def _w(s):
    f = _f()
    return f.text_width(s) if f else len(s) * 4


def _ranks(r, n):
    """強化の段数を目で見て分かる形にする。"""
    return '*' * r + '-' * (n - r)


def _bar(x, y, w, v, vmax):
    pyxel.rectb(x, y, w, 5, DIM)
    if v > 0:
        pyxel.rect(x + 1, y + 1, int((w - 2) * v / vmax), 3, ACC)


class Menu:
    def __init__(self, app):
        self.app = app
        self.open = False
        self.page = 'main'
        self.stack = []        # 上の階層へ戻るための履歴
        self.sel = {}          # ページ毎の選択位置（未訪問は0）
        self.top = 0
        self.capture = None          # 割り当て取得中のアクションID
        self.confirm = ''            # 二度押しで実行する項目
        self.note = ''
        self.note_t = 0

    # ---------------------------------------------------------------- 制御
    def toggle(self):
        self.open = not self.open
        if not self.open:
            fx.invalidate()             # 借りていた色を時刻のものへ戻す
        self.page = 'main'
        self.stack = []
        self.capture = None
        self.app.imap.clear()

    def _pin(self):
        """スクロールしても消えない行。買い物中は所持金を出し続ける。"""
        if self.page in PINNED and self.app.career.on:
            return '%s   %d CR' % (lang.T('CREDITS'),
                                   int(self.app.career.credits))
        return None

    def rows(self):
        """一覧に使える行数。固定表示があるぶん1行減る。"""
        return ROWS - (1 if self._pin() else 0)

    def _go(self, page):
        """下の階層へ入る。"""
        self.stack.append(self.page)
        self.page = page
        self.top = 0
        items = self._items()
        if items and not self._pickable(items[self.sel.get(page, 0) % len(items)]):
            self.sel[page] = self._seek(items, 0, 1)

    def _back(self):
        """ひとつ上の階層へ戻る。最上位なら閉じる。"""
        if self.stack:
            self.page = self.stack.pop()
            self.top = 0
        else:
            self.toggle()

    def _say(self, s, t=90):
        self.note, self.note_t = s, t

    # ---------------------------------------------------------------- 項目
    def _main_items(self):
        import career
        a = self.app
        out = []
        if a.career.on:                      # キャリアでだけ出る3つを先頭に
            out.append(('JOBS', _jobs(a), 'jobs'))
            out.append(('HANGAR', '>', 'hangar'))
            out.append(('SHOP', '>', 'shop'))
        return out + [
            ('FLIGHT', '>', 'flight'),
            ('WEATHER', '>', 'weather'),
            ('GRAPHICS', '>', 'gfx'),
            ('AUDIO', '>', 'audio'),
            ('CONTROLS', '>', 'controls'),
            ('LANDING LOG', '>', 'log'),
            ('LANGUAGE', lang.lang_name(), 'lang'),
            ('MODE', career.NAMES[a.career.mode], 'mode'),
            ('ABOUT', '>', 'about'),
            ('QUIT', '', 'quit'),
        ]

    def _flight_items(self):
        a = self.app
        # キャリアでは位置のやり直しと燃料の直接補給は使えない（点の意味が消える）
        car = a.career.on
        out = [
            ('RESET POSITION', 'CAREER: NO' if car else '>',
             None if car else 'reset'),
            ('RING COURSE', 'RUNNING' if a.course.active else 'START', 'course'),
        ]
        if not car:                      # 仕事はキャリアの第1階層へ移した
            out.append(('CHARTER', _charter(a), 'charter'))
        return out + [
            ('TIME SPEED', _speed(a), 'speed'),
            ('FUEL', '%d%%' % int(a.fuel), None if car else 'fuel'),
            ('ENDURANCE', '%d %s' % (_endurance(a), lang.T('MIN')),
             None if car else 'endurance'),
            ('LANDING LIGHT', 'ON' if a.land_light else 'OFF', 'land_light'),
            ('APPROACH GUIDE', 'ON' if a.app_guide else 'OFF', 'app_guide'),
            ('RESULT SCREEN', 'ON' if a.result_on else 'OFF', 'result_on'),
            # キャリアは仕事中なので、巡航は常に行き先へ向かう
            ('AUTOPILOT CRUISE',
             'TO DESTINATION' if (car or a.ap_nav) else 'FREE TOUR',
             None if car else 'ap_nav'),
            ('BIRDS', 'ON' if a.birds_on else 'OFF', 'birds'),
            ('SAVE FLIGHT', 'NOW', 'save_now'),
            ('PAUSE', 'ON' if a.paused else 'OFF', 'pause'),
        ]

    def _weather_items(self):
        a = self.app
        if a.career.on:
            # 天候は仕事とともに与えられるもの。選べるのはアーケードだけ
            return [('SET BY THE DAY', '', None),
                    ('TIME OF DAY', a.tod_name(), None),
                    ('CLOUDS', 'ON' if a.clouds else 'OFF', None),
                    ('RAIN', 'ON' if a.raining else 'OFF', None),
                    ('WIPER', 'ON' if a.wiper.on else 'OFF', 'wiper'),
                    ('LIGHTNING', 'ON' if a.lightning_on else 'OFF', 'lightning'),
                    ('VISIBILITY', main_vis(a), None),
                    ('WIND', a.wind.level_name, None),
                    ('WIND DIR', '%03d' % int(a.wind.direction), None),
                    ('WIND SHEAR', 'ON' if a.wind.shear_on else 'OFF', None)]
        return [
            ('TIME OF DAY', a.tod_name(), 'tod'),
            ('DAY LENGTH', _tod_speed(a), 'tod_speed'),
            ('CLOUDS', 'ON' if a.clouds else 'OFF', 'clouds'),
            ('RAIN', 'ON' if a.raining else 'OFF', 'rain'),
            ('WIPER', 'ON' if a.wiper.on else 'OFF', 'wiper'),
            ('LIGHTNING', 'ON' if a.lightning_on else 'OFF', 'lightning'),
            ('VISIBILITY', main_vis(a), 'vis'),
            ('WIND', a.wind.level_name, 'wind'),
            ('WIND DIR', '%03d' % int(a.wind.direction), 'wind_dir'),
            ('WIND SHEAR', 'ON' if a.wind.shear_on else 'OFF', 'shear'),
        ]

    def _hangar_items(self):
        """整備と補給。キャリアモードのときだけ出る。"""
        import career
        import world
        a = self.app
        c = a.career
        ground = a.ac.on_ground and a.ac.kias < 3.0
        nxp = c.next_level()
        _, nxt = c.next_rank()
        out = [('STATUS', '', SEC),
               ('CREDITS', '%d CR' % int(c.credits), None),
               ('%s %d' % (lang.T('LEVEL'), c.level),
                ('%s %d XP' % (lang.T('NEXT'), nxp)) if nxp else 'MAX', None),
               ('RANK', lang.T(c.rank_name()), None),
               ('FLIGHTS', str(c.flights), None)]
        if nxt:
            out.append(('  %s %s' % (lang.T('NEXT'), lang.T(nxt)),
                        '%d XP' % c.next_rank()[0], None))

        out.append(('MAINTENANCE', '', SEC))
        gnd = '' if c.airworthy else ' - UNAIRWORTHY'
        out.append((lang.T('YOUR AIRCRAFT') + gnd,
                    '%d%%' % round(100.0 - c.worst), None))
        for p in career.PARTS:
            d = c.dmg[p]
            key = ('fix_' + p) if d > 0.0 else None
            out.append(('  %-8s %3d%%' % (lang.T(p), round(d)),
                        '%d CR' % c.repair_cost(p), key))
        pc = c.patch_all_cost()
        out.append(('PATCH ALL (20% LEFT)', '%d CR' % pc,
                    'patch' if pc > 0 else None))
        miss = 100.0 - a.fuel
        out.append(('REFUEL TO FULL', '%d CR' % c.fuel_cost(miss),
                    'buy_fuel' if miss > 0.5 else None))
        out.append(('  (HOLD BRAKE ON GROUND TO FUEL)', '', None))

        out.append(('CAREER', '', SEC))
        out.append(('RESET CAREER',
                    'PRESS AGAIN' if self.confirm == 'wipe' else 'START OVER',
                    'wipe'))
        return out

    def _shop_items(self):
        """買い物。機体・資格・装備をここにまとめる。"""
        import career
        a = self.app
        c = a.career
        ground = a.ac.on_ground and a.ac.kias < 3.0
        out = [('AIRCRAFT', '', SEC),
               ('CHANGE AIRCRAFT', 'CLUB -%d%%' % round(career.RENT_CUT * 100)
                if c.rented else lang.T(_fleet_name(c.plane)), 'fleet')]
        if ground:
            out.append(('RENT CLUB AIRCRAFT', 'ON' if c.rented else 'OFF', 'rent'))
        else:
            out.append(('  (CHANGE ON THE GROUND)', '', None))
        out.append(('RATINGS', '', SEC))
        out.append(('EARN RATINGS',
                    '%d / %d' % (len(c.ratings), len(career.RATINGS)), 'ratings'))
        out.append(('PILOT', '', SEC))
        if c.sk_rank('BASE'):
            out.append(('HOME BASE', lang.T('%s AIRPORT') % c.base if c.base
                        else lang.T('NOT SET'), 'base'))
        out.append(('PILOT SKILLS', '%d / %d' % (
            sum(c.sk_rank(x[0]) for x in career.SKILL),
            len(career.SKILL) * career.SK_MAX), 'skills'))
        out.append(('AIRCRAFT UPGRADES', '', SEC))
        out.append(('UPGRADE PARTS', '%d / %d' % (
            sum(c.up_rank(p) for p, _n, _d in career.UPGRADE),
            len(career.UPGRADE) * career.UP_MAX), 'upgrade'))
        out.append(('EQUIPMENT', '', SEC))
        for eid, nm, cost, desc in career.EQUIP:
            on = c.fitted(eid)
            out.append((nm, 'FITTED' if on else '%d CR' % cost,
                        None if (on or c.rented) else ('eq_' + eid)))
            out.append(('  %s' % desc, '', None))
        return out

    def _about_items(self):
        """この作品について。版と、素材の出どころ。"""
        import main as _m
        import pyxel as _p
        a = self.app
        st = a.stats
        return [
            ('PFS', '', SEC),
            ('PIXEL FLIGHT SIMULATOR', '', None),
            ('  VERSION', _m.VERSION, None),
            ('  PYXEL', _p.VERSION, None),
            ('ASSETS', '', SEC),
            ('  FONT', 'U-M+ / COZ', None),
            ('  ATC VOICE', 'SPEECH SYNTHESIS', None),
            ('RECORD', '', SEC),
            ('  LANDINGS', '%d' % st.get('count', 0), None),
            ('  BEST SCORE', '%d P' % st.get('best', 0), None),
            ('  HAND FLOWN', '%d' % st.get('hand', 0), None),
        ]

    def _skills_items(self):
        """操縦者のスキル。機体を乗り換えても残る。"""
        import career
        c = self.app.career
        out = [('%s %d' % (lang.T('LEVEL'), c.level), '', SEC)]
        for sid, name, lv0, gain, desc in career.SKILL:
            r = c.sk_rank(sid)
            need = c.sk_need_lv(sid)
            if r >= career.SK_MAX:
                val, key = 'MAX', None
            elif c.level < need:
                val, key = 'LV%d' % need, None
            else:
                val, key = '%d CR' % c.sk_cost(sid), 'sk_' + sid
            out.append((name, val, key))
            out.append(('  %s  %s' % (_ranks(r, career.SK_MAX), lang.T(desc)),
                        '', None))
        return out

    def _upgrade_items(self):
        """機体強化。部位ごとに5段まで。売ると一緒に消える。"""
        import career
        c = self.app.career
        out = [('%s  %s' % (lang.T('AIRCRAFT'),
                            lang.T(_fleet_name(c.plane))), '', SEC)]
        if c.rented:
            out.append(('  (CLUB AIRCRAFT CANNOT BE UPGRADED)', '', None))
            return out
        for part, name, desc in career.UPGRADE:
            r = c.up_rank(part)
            cost = c.up_cost(part)
            val = 'MAX' if r >= career.UP_MAX else '%d CR' % cost
            out.append((name, val, None if r >= career.UP_MAX else ('up_' + part)))
            out.append(('  %s  %s' % (_ranks(r, career.UP_MAX), lang.T(desc)),
                        '', None))
        return out

    def _jobs_items(self):
        """ジョブボード。いる空港で受けられる仕事が並ぶ。"""
        a = self.app
        b = a.board
        ground = a.ac.on_ground and a.ac.kias < 3.0
        if b.active is not None:
            j = b.active
            out = [('ON A JOB', '', SEC),
                   ('  %s' % j.title_t(), '', None),
                   ('  %s' % j.summary_t()[:24], '', None),
                   ('  PAY', '%d CR' % j.pay, None),
                   ('  EST', '%d %s' % (max(1, round(j.est)), lang.T('MIN')),
                    None),
                   ('  XP', '+%d' % j.xp, None),
                   ('BRIEFING', '', 'brief')]
            if j.limit:
                t = j.left()
                out.append(('  TIME LEFT',
                            '%d:%02d' % (int(t) // 60, int(t) % 60), None))
            if j.targets:
                out.append(('TARGETS', '', SEC))
                for i, (tx, ty, nm) in enumerate(j.targets):
                    out.append(('  %s' % nm[:14],
                                'DONE' if j.hit[i] else '-', None))
            out.append(('CANCEL', '', SEC))
            out.append(('ABANDON JOB', '', 'abandon'))
            return out
        out = [('%s  %s' % (lang.T('BOARD AT'),
                            lang.T('%s AIRPORT') % b.at), '', SEC)]
        if not ground:
            out.append(('  (LAND TO TAKE A JOB)', '', None))
        cap = a.career.spec['cap']
        for i, j in enumerate(b.jobs):
            # 機体を乗り換えたあとなど、積めない仕事は理由を出して選ばせない
            heavy = j.payload > cap
            val = 'TOO HEAVY' if heavy else '%d CR' % j.pay
            if i:
                out.append(('', '', SEC))
            out.append((j.title_t(), val,
                        None if (heavy or not ground) else ('job_%d' % i)))
            out.append(('  %s' % j.summary_t()[:24], '', None))
            note = '%s %d %s   +%d XP' % (lang.T('EST'), max(1, round(j.est)),
                                          lang.T('MIN'), j.xp)
            if j.limit:
                note += '  %s %d %s' % (lang.T('LIMIT'),
                                        round(j.limit / 60.0), lang.T('MIN'))
            out.append(('  %s' % note, '', None))
        return out

    def _ratings_items(self):
        """資格。XPが足りて、金が払えれば取れる。"""
        import career
        c = self.app.career
        nxp = c.next_level()
        out = [('%s %d' % (lang.T('LEVEL'), c.level),
                ('%s %d XP' % (lang.T('NEXT'), nxp)) if nxp else 'MAX', None),
               ('XP', '%d  (%s)' % (c.xp, lang.T(c.rank_name())), None)]
        for rid, nm, need_lv, cost, desc in career.RATINGS:
            held = c.has_rating(rid)
            ok, why = c.rating_ready(rid)
            val = 'HELD' if held else ('%d CR' % cost if ok else why)
            out.append((nm, val, ('rat_' + rid) if ok else None))
            out.append(('  %s' % desc, '', None))
        return out

    def _fleet_items(self):
        """機体の一覧。買う・乗り換える・売る。"""
        import fleet
        a = self.app
        c = a.career
        ground = a.ac.on_ground and a.ac.kias < 3.0
        out = []
        if not ground:
            out.append(('  (LAND FIRST TO CHANGE)', '', None))
        for s in fleet.SPECS:
            pid = s['id']
            own = c.owns(pid)
            if own:
                val = 'FLYING' if pid == c.plane else 'OWNED'
                key = None if pid == c.plane else ('sel_' + pid)
            else:
                val = '%d CR' % s['price']
                key = 'buy_' + pid
            out.append((s['name'], '', SEC))
            out.append(('  %s' % s['desc'], val, key if ground else None))
            out.append(('  STALL %d  CRZ %d KT  %d KM'
                        % (round(fleet.stall_kt(pid)), s['cruise'], s['range_km']),
                        '', None))
            if own and pid != c.plane and len(c.hangar) > 1:
                out.append(('  SELL', '%d CR' % c.value(pid),
                            ('sell_' + pid) if ground else None))
        return out

    def _controls_items(self):
        return [
            ('KEY MAPPING', '>', 'keys'),
            ('BUTTON LAYOUT', self.app.imap.layout_name, '_layout'),
            ('HELP', '>', 'help'),
        ]

    def _audio_items(self):
        b = self.app.bgm
        return [
            ('BGM MODE', b.mode_name, 'bgm_mode'),
            ('BGM VOLUME', str(b.volume), 'bgm_vol'),
            ('SE VOLUME', str(self.app.audio.volume), 'se_vol'),
            ('ATC VOICE', str(self.app.atc.volume), 'atc_vol'),
            ('BGM TRACK', b.title(18), 'bgm_track'),
            ('TRACKS FOUND', str(b.count), None),
        ]

    def _gfx_items(self):
        a = self.app
        return [
            ('DETAIL', DETAIL[a.detail], 'detail'),
            ('CLOUD SHADOWS', 'ON' if a.detail >= 2 else 'OFF', None),
            ('CLOUD LAYER', 'ON' if a.detail >= 1 else 'OFF', None),
            ('SHOW FPS', 'ON' if a.show_fps else 'OFF', 'fps'),
            ('FPS LIMIT', '%d (NEXT LAUNCH)' % a.fps, 'fps_limit'),
            ('ASPECT', '%s (NEXT LAUNCH)' % _aspect(a), 'aspect'),
        ]

    def _log_items(self):
        a = self.app
        log = a.landing_log
        st = a.stats
        head = []
        if st['count']:
            head.append(('BEST %d  AVG %d' % (st['best'], st['total'] // st['count']),
                         '%d LDG' % st['count'], None))
            head.append(('HAND FLOWN', '%d / %d' % (st.get('hand', 0),
                                                    st['count']), None))
        head.insert(0, ('CAREER TOTAL', '', SEC))
        t = int(a.air_time)
        head.append(('AIR TIME', '%d:%02d:%02d' % (t // 3600, t // 60 % 60, t % 60),
                     None))
        if a.course.best:
            head.append(('COURSE BEST', '%.1fS' % a.course.best, None))
        import world
        head.append(('%s  %d / %d' % (lang.T('SIGHTS'), len(a.visited),
                                      len(world.LANDMARKS)), '', SEC))
        for lm in world.LANDMARKS:
            seen = lm.name in a.visited
            head.append(('  %s' % lm.name[:14], 'SEEN' if seen else '-', None))
        for k in sorted(a.charter.best):
            head.append(('  CHARTER %s' % k[:12], '%d P' % a.charter.best[k], None))
        for name in sorted(a.apt_best):
            head.append(('  %s BEST' % lang.T('%s AIRPORT') % name,
                         '%d P' % a.apt_best[name], None))
        if not log:
            return head + [('NO LANDINGS YET', '', None)]
        out = list(head) + [('RECENT LANDINGS', '', SEC),
                            ('  H=HAND  /=PARTIAL  A=AUTO', '', None)]
        for r in reversed(log):
            mark = '%3dP' % r['score'] if r['on_rwy'] else 'MISS'
            # H=手動 /=途中からAP A=自動着陸。空欄はキャリア以前の記録
            h = r.get('hand')
            hm = ' ' if h is None else ('H' if h >= 0.999 else ('/' if h > 0 else 'A'))
            out.append(('%-7s %5.1fM/S' % (r['apt'][:7], r['vs']),
                        '%4dM %+3dM %s %s' % (r['zone'], r['lateral'], hm, mark),
                        None))
        return out

    def _reset_items(self):
        return [('RUNWAY', '', 'r_runway'), ('ON FINAL', '', 'r_final'),
                ('CRUISE', '', 'r_cruise')]

    def _keys_items(self):
        return ([(im.LABELS[a], self.app.imap.label(a), a) for a in im.ACTION_IDS]
                + [('RESET TO DEFAULT', '', '_reset')])

    def _items(self):
        f = {'main': self._main_items, 'flight': self._flight_items,
             'weather': self._weather_items, 'audio': self._audio_items,
             'reset': self._reset_items, 'gfx': self._gfx_items,
             'log': self._log_items, 'controls': self._controls_items,
             'hangar': self._hangar_items, 'fleet': self._fleet_items,
             'shop': self._shop_items,
             'jobs': self._jobs_items, 'ratings': self._ratings_items,
             'upgrade': self._upgrade_items,
             'skills': self._skills_items,
             'about': self._about_items,
             'keys': self._keys_items}.get(self.page)
        return f() if f else []

    # ---------------------------------------------------------------- 更新
    def update(self, imap):
        if self.note_t > 0:
            self.note_t -= 1
        if self.capture:
            self._update_capture()
            return
        if imap.pressed['menu']:
            self.toggle()
            return
        if imap.pressed['cancel']:
            self._back()
            return
        items = self._items()
        if not items:
            return
        n = len(items)
        if not any(self._pickable(it) for it in items):
            # 押せる項目が無いページ（飛行記録など）は、上下でそのまま送る
            top = max(0, n - self.rows())
            if self._rep(imap, 'pitch_down'):
                self.top = max(0, self.top - 1)
            if self._rep(imap, 'pitch_up'):
                self.top = min(top, self.top + 1)
            self.top = min(self.top, top)
            return
        s = self.sel.get(self.page, 0) % n
        if not self._pickable(items[s]):        # 選べない行に居たら動かす
            s = self._seek(items, s, 1)
        if self._rep(imap, 'pitch_down'):
            s = self._seek(items, s, -1)
        if self._rep(imap, 'pitch_up'):
            s = self._seek(items, s, 1)
        if s != self.sel.get(self.page, 0):
            self.confirm = ''        # 選択が動いたら確認は取り消す
        self.sel[self.page] = s
        key = items[s][2]
        if self._rep(imap, 'roll_left'):
            self._adjust(key, -1)
        if self._rep(imap, 'roll_right'):
            self._adjust(key, 1)
        if imap.pressed['ok']:
            self._activate(key)
        rows = self.rows()
        self.top = max(0, min(s - rows + 2, max(0, n - rows)))
        if s < self.top:
            self.top = s

    @staticmethod
    def _pickable(item):
        return item[2] is not None and item[2] != SEC

    @classmethod
    def _seek(cls, items, s, d):
        """次に選べる項目へ。見出しや説明の行は飛ばす。"""
        n = len(items)
        for _ in range(n):
            s = (s + d) % n
            if cls._pickable(items[s]):
                return s
        return s

    def _rep(self, imap, action):
        """押しっぱなしでリピートする方向入力。"""
        if imap.pressed[action]:
            self._hold = 0
            return True
        if imap.held[action]:
            self._hold = getattr(self, '_hold', 0) + 1
            if self._hold > 18 and self._hold % 4 == 0:
                return True
        return False

    def _update_capture(self):
        ch = im.capture()
        if not ch:
            return
        a = self.capture
        conflict = self.app.imap.conflicts(a, ch)
        if conflict:
            self._say('ALREADY USED BY ' + im.LABELS[conflict])
        else:
            self.app.imap.set(a, ch)
            self._say('SET ' + im.chord_name(ch))
            self.app.save_settings()
        self.capture = None
        self.app.imap.clear()

    def _adjust(self, key, d):
        a = self.app
        if key == 'tod':
            a.tod_i = (a.tod_i + d) % len(a.TODS)
        elif key == 'clouds':
            a.clouds = not a.clouds
        elif key == 'rain':
            a.raining = not a.raining
        elif key == 'tod_speed':
            import main as _m
            a.tod_speed_i = (a.tod_speed_i + d) % len(_m.TOD_PERIOD)
        elif key == 'shear':
            a.wind.shear_on = not a.wind.shear_on
        elif key == 'lightning':
            a.lightning_on = not a.lightning_on
        elif key == 'wiper':
            a.wiper.on = not a.wiper.on
        elif key == 'land_light':
            a.land_light = not a.land_light
        elif key == 'app_guide':
            a.app_guide = not a.app_guide
        elif key == 'result_on':
            a.result_on = not a.result_on
        elif key == 'ap_nav':
            a.ap_nav = not a.ap_nav
        elif key == 'birds':
            a.birds_on = not a.birds_on
        elif key == 'endurance':
            import main as _m
            a.endurance_i = (a.endurance_i + d) % len(_m.ENDURANCE)
        elif key == 'fuel':
            import main as _m
            a.fuel = max(0.0, min(_m.FUEL_MAX, a.fuel + d * 10.0))
            a._fuel_warn = a.fuel
            if a.fuel > 1.0 and a.ac.engine < 1.0 and a.ac.on_ground:
                a.ac.engine = 1.0
        elif key == 'vis':
            a.vis = (a.vis + d) % 3
        elif key == 'pause':
            a.set_paused(not a.paused)
        elif key == 'bgm_mode':
            a.bgm.set_mode(a.bgm.mode + d)
        elif key == 'bgm_vol':
            a.bgm.set_volume(a.bgm.volume + d)
        elif key == 'se_vol':
            a.audio.set_volume(a.audio.volume + d)
        elif key == 'atc_vol':
            a.atc.set_volume(a.atc.volume + d)
        elif key == 'bgm_track':
            a.bgm.next(d)
        elif key == 'lang':
            lang.set_lang(lang.lang + d)
            a.save_settings()
        elif key == 'mode':
            import career
            a.career.mode = career.CAREER if a.career.mode == career.ARCADE \
                else career.ARCADE
            a.career.save()
            a.board.active = None      # モードをまたいで仕事は持ち越さない
            a.board.at = ''
            if a.career.on:
                a.roll_weather()
                self._say('CAREER MODE - WEATHER IS GIVEN')
            else:
                self._say('ARCADE MODE')
        elif key == 'speed':
            import main as _m
            a.speed_i = (a.speed_i + d) % len(_m.TIME_MULT)
        elif key == 'charter':
            if a.charter.active:
                a.charter.stop()
            else:
                a.charter.start(a.ac)
                self.toggle()
        elif key == 'course':
            if a.course.active:
                a.course.stop()
            else:
                a.course.start()
                self.toggle()
        elif key == 'wind':
            a.wind.set_level(a.wind.level + d)
        elif key == 'wind_dir':
            a.wind.turn(d * 10)
        elif key == 'detail':
            a.detail = (a.detail + d) % 3
        elif key == 'fps':
            a.show_fps = not a.show_fps
        elif key == 'aspect':
            import main as _m
            a.aspect_i = (a.aspect_i + d) % len(_m.ASPECTS)
            self._say('ASPECT %s - RESTART TO APPLY' % _aspect(a), 150)
        elif key == 'fps_limit':
            a.fps = 30 if a.fps == 60 else 60
            self._say('FPS LIMIT %d - RESTART TO APPLY' % a.fps, 150)
        elif key == '_layout':
            a.imap.set_layout(im.layout + 1)
            self._say('LAYOUT ' + a.imap.layout_name)
        else:
            return
        a.save_settings()

    def _activate(self, key):
        a = self.app
        before = a.career.msg
        if key in SUBPAGES:
            self._go(key)
        elif key in ('tod', 'clouds', 'rain', 'pause', 'bgm_mode', 'bgm_track',
                     '_layout', 'wind', 'detail', 'fps', 'fps_limit', 'course',
                     'vis', 'wiper', 'land_light', 'birds', 'endurance', 'app_guide', 'result_on', 'ap_nav',
                     'base',
                     'aspect', 'lightning', 'tod_speed', 'charter', 'speed', 'lang',
                     'shear'):
            self._adjust(key, 1)
        elif key == 'quit':
            a.save_flight()        # 中断しても続きから飛べるように
            a.save_settings()
            pyxel.quit()
        elif key == 'save_now':
            a.save_flight()
            a.save_settings()
            self._say('FLIGHT SAVED')
        elif key == 'mode':
            self._adjust(key, 1)
        elif key and key.startswith('fix_'):
            a.career.repair(key[4:])
        elif key == 'wipe':
            # 取り返しがつかないので二度押しで確定する
            if self.confirm == 'wipe':
                self.confirm = ''
                a.career.reset()
                a.reset_records()      # 飛行記録も一緒に消す
                a.clear_flight_save()
                a.board.active = None
                a.board.at = ''
                a.fuel = 100.0
                a._fuel_warn = 100.0
                a.ac.reset_runway()
                a.roll_weather()
                self._say('CAREER RESET')
            else:
                self.confirm = 'wipe'
                self._say('PRESS AGAIN TO WIPE EVERYTHING', 180)
        elif key == 'patch':
            a.career.patch_all()
        elif key == 'rent':
            a.career.rent(not a.career.rented)
        elif key and key.startswith('buy_'):
            a.career.buy(key[4:])
        elif key and key.startswith('sel_'):
            a.career.select(key[4:])
        elif key and key.startswith('sell_'):
            a.career.sell(key[5:])
        elif key and key.startswith('job_'):
            i = int(key[4:])
            if 0 <= i < len(a.board.jobs):
                self.toggle()
                # 受注は打ち合わせの最後に決める。整備のため断ることもできる
                a.show_brief(a.board.jobs[i], index=i)
        elif key == 'brief':
            self.toggle()
            a.show_brief()
        elif key == 'abandon':
            a.board.abandon()
        elif key and key.startswith('rat_'):
            a.career.buy_rating(key[4:])
        elif key and key.startswith('eq_'):
            a.career.buy_equip(key[3:])
        elif key and key.startswith('up_'):
            a.career.buy_upgrade(key[3:])
        elif key and key.startswith('sk_'):
            a.career.buy_skill(key[3:])
        elif key == 'base':
            import world
            names = [x.name for x in world.AIRPORTS]
            i = names.index(a.career.base) + 1 if a.career.base in names else 0
            a.career.base = names[i % len(names)]
            a.career.save()
            self._say('HOME BASE %s' % a.career.base)
        elif key == 'buy_fuel':
            import main as _m
            got = a.career.buy_fuel(_m.FUEL_MAX - a.fuel)
            a.fuel += got
            a._fuel_warn = a.fuel
            a.career.save()
            self._say('FUELLED %d PERCENT' % round(got) if got > 0.5
                      else 'NOT ENOUGH CREDITS')
        elif key in ('r_runway', 'r_final', 'r_cruise'):
            {'r_runway': a.ac.reset_runway, 'r_final': a.ac.reset_final,
             'r_cruise': a.ac.reset_cruise}[key]()
            a._ap_low_ft = None       # 置き直したら手動の判定もやり直す
            self.toggle()
        elif key == 'fuel':
            import main as _m
            a.fuel = _m.FUEL_MAX
            a._fuel_warn = a.fuel
            if a.ac.on_ground:
                a.ac.engine = 1.0
            self._say('FUEL FULL')
        elif key == '_reset':
            a.imap.reset(); a.save_settings(); self._say('KEYMAP RESET')
        elif key in im.ACTION_IDS:
            self.capture = key
            self._say('PRESS NEW KEY / BUTTON', 600)
        # 整備や購入の結果はキャリア側がメッセージを持つので、ここで出す
        if a.career.msg and a.career.msg != before:
            self._say(a.career.msg[:44])

    # ---------------------------------------------------------------- 描画
    def draw(self):
        pyxel.dither(0.6)
        pyxel.rect(0, 0, W, H, BG)
        pyxel.dither(1.0)
        for i, c in UI_COLS:            # 時刻によらず読める色を借りる
            pyxel.colors[i] = c
        x, y, w = 18, 12, W - 36
        pyxel.rect(x, y, w, H - 30, BG)
        pyxel.rectb(x, y, w, H - 30, FG)
        title = lang.T(TITLES.get(self.page, 'OPTIONS'))
        pyxel.rect(x + 1, y + 1, w - 2, 11, FG)
        _txt(x + 5, y + 2, title, BG)
        ly = y + 15
        pin = self._pin()
        if pin:
            pyxel.rect(x + 1, ly - 1, w - 2, 12, SELBAR)
            _txt(x + 5, ly, pin, ACC)
            pyxel.line(x + 1, ly + 11, x + w - 2, ly + 11, DIM)
            ly += 13
        if self.page == 'help':
            self._draw_help(x + 5, y + 15, w - 10)
        else:
            self._draw_list(x + 4, ly, w - 8)
        b = y + H - 30 - 9
        foot = 'OK:%s  BACK:%s' % (self.app.imap.label('ok').split(' / ')[0],
                                   self.app.imap.label('cancel').split(' / ')[0])
        pyxel.rect(x + 1, b - 1, w - 2, 10, BG)
        _txt(x + 5, b, foot, DIM)
        if self.note_t > 0:
            pyxel.rect(x + 1, b - 12, w - 2, 11, BG)
            _txt(x + 5, b - 11, lang.T(self.note), SEL)

    def _draw_list(self, x, y, w):
        items = self._items()
        s = self.sel.get(self.page, 0) % max(1, len(items))
        rows = self.rows()
        view = items[self.top:self.top + rows]
        for i, (name, val, key) in enumerate(view):
            idx = self.top + i
            yy = y + i * 12
            if key == SEC:                       # 見出し。罫線で区切る
                t = lang.T(name)
                _txt(x + 1, yy, t, ACC)
                lx = x + _w(t) + 4
                pyxel.line(lx, yy + 5, x + w - 2, yy + 5, DIM)
                continue
            on = (idx == s)
            if on:
                pyxel.rect(x, yy - 1, w, 12, SELBAR)
                _txt(x + 1, yy, '>', SEL)
            col = SEL if on else (DIM if key is None else FG)
            # 行頭の空白（字下げ）は訳の対象外なので、分けてから訳す
            pad = len(name) - len(name.lstrip())
            _txt(x + 7 + pad * 4, yy, lang.T(name.strip()), col)
            if key in ('bgm_vol', 'se_vol', 'atc_vol'):
                _bar(x + w - 62, yy + 3, 40, int(val), 10)
                _txt(x + w - 18, yy, val, col)
            elif val:
                v = lang.T(val)
                _txt(x + w - _w(v) - 2, yy, v, ACC if on else col)
        if len(items) > rows:
            _txt(x + w - 10, y - 2, '^' if self.top else ' ', DIM)
            _txt(x + w - 10, y + rows * 12 - 4,
                 'v' if self.top + rows < len(items) else ' ', DIM)

    def _draw_help(self, x, y, w):
        m = self.app.imap
        rows = [('PITCH', 'pitch_down', 'pitch_up'),
                ('ROLL', 'roll_left', 'roll_right'),
                ('RUDDER', 'rudder_left', 'rudder_right'),
                ('THROTTLE', 'throttle_up', 'throttle_down'),
                ('FLAP', 'flap_down', 'flap_up'),
                ('TRIM', 'trim_down', 'trim_up'),
                ('LOOK', 'look_left', 'look_right')]
        for i, (nm, a, b) in enumerate(rows):
            yy = y + i * 15
            _txt(x, yy + 3, lang.T(nm), ACC)
            _txt(x + 62, yy - 1, m.label(a).split(' / ')[0], FG)
            _txt(x + 62, yy + 7, m.label(b).split(' / ')[0], FG)
        yy = y + len(rows) * 15 + 2
        for nm, a in (('BRAKE', 'brake'), ('VIEW', 'view'), ('DEST', 'dest'),
                      ('MENU', 'menu')):
            _txt(x, yy, lang.T(nm), ACC)
            _txt(x + 62, yy, m.label(a), FG)
            yy += 10
