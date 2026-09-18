"""入力割り当て。キーボードとゲームパッドを同じ仕組みで扱う。

割り当ては「和音（chord）の候補リスト」で持つ。
和音の要素は [キーコード] か [軸コード, 符号] で、軸はアナログスティック用。
L や Shift を押している間は、それを含まない和音を無効にするので
「X = トリム」「L+X = 視点切替」のような組み合わせが両立する。
"""
import json
import os
import sys
from pathlib import Path

import pyxel

CONFIG_NAME = 'pfs_config.json'
AXIS_TH = 12000            # アナログスティックのしきい値
# 視点の左右振りは「倒した割合＝角度」にしたいので、専用の小さめの死帯を使う。
# 死帯を抜けた直後だけ滑らかに立ち上げ、そこから先は倒し量をそのまま返す
STICK_TH = 0.12            # ここまでは効かない（安物のスティックのぶれ対策）
STICK_BLEND = 0.10         # 死帯の上、これだけの幅で本来の値に追いつく

# アクション: (ID, 表示名, 押しっぱなしで効くか)
ACTIONS = [
    ('menu',          'OPTION MENU',   False),
    ('ok',            'MENU OK',       False),
    ('cancel',        'MENU CANCEL',   False),
    ('pitch_down',    'PITCH DOWN',    True),
    ('pitch_up',      'PITCH UP',      True),
    ('roll_left',     'ROLL LEFT',     True),
    ('roll_right',    'ROLL RIGHT',    True),
    ('rudder_left',   'RUDDER LEFT',   True),
    ('rudder_right',  'RUDDER RIGHT',  True),
    ('throttle_up',   'THROTTLE UP',   True),
    ('throttle_down', 'THROTTLE DOWN', True),
    ('flap_down',     'FLAP DOWN',     False),
    ('flap_up',       'FLAP UP',       False),
    ('trim_down',     'TRIM DOWN',     True),
    ('trim_up',       'TRIM UP',       True),
    ('look_left',     'LOOK LEFT',     True),
    ('look_right',    'LOOK RIGHT',    True),
    ('look_hold',     'LOOK HOLD',     True),
    ('brake',         'BRAKE',         False),
    ('view',          'VIEW TOGGLE',   False),
    ('dest',          'NEXT DEST',     False),
    ('autopilot',     'AUTOPILOT',     False),
]
ACTION_IDS = [a[0] for a in ACTIONS]
LABELS = {a[0]: a[1] for a in ACTIONS}

_G = pyxel
LB = _G.GAMEPAD1_BUTTON_LEFTSHOULDER
RB = _G.GAMEPAD1_BUTTON_RIGHTSHOULDER
LT = _G.GAMEPAD1_AXIS_TRIGGERLEFT
RT = _G.GAMEPAD1_AXIS_TRIGGERRIGHT
LX = _G.GAMEPAD1_AXIS_LEFTX
LY = _G.GAMEPAD1_AXIS_LEFTY
RX = _G.GAMEPAD1_AXIS_RIGHTX

# 修飾キー: これを押している間、それを含まない和音は無効になる。
# タプルはアナログ軸の修飾（L2のようなトリガ）。
LOOK_MOD = (LT, 1)
MODIFIERS = (pyxel.KEY_SHIFT, LB, LOOK_MOD)

DEFAULTS = {
    'menu':          [[pyxel.KEY_TAB], [_G.GAMEPAD1_BUTTON_START]],
    'ok':            [[pyxel.KEY_RETURN], [_G.GAMEPAD1_BUTTON_A]],
    'cancel':        [[pyxel.KEY_ESCAPE], [_G.GAMEPAD1_BUTTON_B]],
    'pitch_down':    [[pyxel.KEY_UP], [_G.GAMEPAD1_BUTTON_DPAD_UP], [LY, -1]],
    'pitch_up':      [[pyxel.KEY_DOWN], [_G.GAMEPAD1_BUTTON_DPAD_DOWN], [LY, 1]],
    'roll_left':     [[pyxel.KEY_LEFT], [_G.GAMEPAD1_BUTTON_DPAD_LEFT], [LX, -1]],
    'roll_right':    [[pyxel.KEY_RIGHT], [_G.GAMEPAD1_BUTTON_DPAD_RIGHT], [LX, 1]],
    'rudder_left':   [[pyxel.KEY_Q], [LB, _G.GAMEPAD1_BUTTON_DPAD_LEFT], [LB, LX, -1]],
    'rudder_right':  [[pyxel.KEY_E], [LB, _G.GAMEPAD1_BUTTON_DPAD_RIGHT], [LB, LX, 1]],
    'throttle_up':   [[pyxel.KEY_X], [RT, 1]],
    'throttle_down': [[pyxel.KEY_Z], [RB]],
    'flap_down':     [[pyxel.KEY_F], [_G.GAMEPAD1_BUTTON_Y]],
    'flap_up':       [[pyxel.KEY_SHIFT, pyxel.KEY_F], [_G.GAMEPAD1_BUTTON_A]],
    'trim_down':     [[pyxel.KEY_LEFTBRACKET], [_G.GAMEPAD1_BUTTON_X]],
    'trim_up':       [[pyxel.KEY_RIGHTBRACKET], [_G.GAMEPAD1_BUTTON_B]],
    # 右スティック横、または L2＋十字キー左右で視点を振る
    'look_left':     [[RX, -1], [_G.GAMEPAD1_BUTTON_DPAD_LEFT, LT, 1],
                      [pyxel.KEY_COMMA]],
    'look_right':    [[RX, 1], [_G.GAMEPAD1_BUTTON_DPAD_RIGHT, LT, 1],
                      [pyxel.KEY_PERIOD]],
    # 押している間は振った向きを保つ
    'look_hold':     [[pyxel.KEY_SLASH], [LT, 1]],
    'brake':         [[pyxel.KEY_B], [LB, _G.GAMEPAD1_BUTTON_B]],
    'view':          [[pyxel.KEY_V], [LB, _G.GAMEPAD1_BUTTON_X]],
    'dest':          [[pyxel.KEY_N], [LB, LT, 1]],
    'autopilot':     [[pyxel.KEY_A], [_G.GAMEPAD1_BUTTON_BACK]],
}

# ------------------------------------------------------------------ 名前
def _build_names():
    out = {}
    for n in dir(pyxel):
        if n.startswith(('KEY_', 'GAMEPAD', 'MOUSE_')):
            v = getattr(pyxel, n)
            if isinstance(v, int) and v not in out:
                out[v] = (n.replace('GAMEPAD1_BUTTON_', 'PAD ')
                           .replace('GAMEPAD1_AXIS_', 'AX ')
                           .replace('KEY_', ''))
    return out


NAMES = _build_names()
_SHORT = {'LEFTSHOULDER': 'L', 'RIGHTSHOULDER': 'R', 'TRIGGERLEFT': 'L2',
          'TRIGGERRIGHT': 'R2', 'LEFTBRACKET': '[', 'RIGHTBRACKET': ']',
          'DPAD_UP': 'UP', 'DPAD_DOWN': 'DOWN', 'DPAD_LEFT': 'LEFT',
          'DPAD_RIGHT': 'RIGHT', 'LEFTX': 'LX', 'LEFTY': 'LY', 'RETURN': 'ENT',
          'ESCAPE': 'ESC'}


# ------------------------------------------------------------------ ボタン配置
# 任天堂系のハンドヘルドは SDL の A/B・X/Y が物理刻印と入れ替わっている。
# 割り当てそのものを入れ替え、表示名も物理刻印に合わせる。
LAYOUTS = ('XBOX', 'NINTENDO')
FACE_PAIRS = ((_G.GAMEPAD1_BUTTON_A, _G.GAMEPAD1_BUTTON_B),
              (_G.GAMEPAD1_BUTTON_X, _G.GAMEPAD1_BUTTON_Y))
_FACE_SWAP = {}
for _a, _b in FACE_PAIRS:
    _FACE_SWAP[_a] = _b
    _FACE_SWAP[_b] = _a
layout = 1                     # 既定は NINTENDO（手元のハンドヘルド向け）


def swap_faces(chords):
    """和音の A/B・X/Y を入れ替えた新しいリストを返す。

    軸の符号(±1)はボタンコードと衝突しないのでそのまま通る。
    """
    return [[_FACE_SWAP.get(e, e) for e in c] for c in chords]


def key_name(code):
    if layout == 1 and code in _FACE_SWAP:
        code = _FACE_SWAP[code]        # 物理刻印で見せる
    n = NAMES.get(code, '?%d' % code)
    for a, b in _SHORT.items():
        n = n.replace(a, b)
    return n


def chord_name(ch):
    if len(ch) == 2 and _is_axis(ch):
        return key_name(ch[0]) + ('+' if ch[1] > 0 else '-')
    parts = []
    i = 0
    while i < len(ch):
        if i == len(ch) - 2 and _is_axis(ch[i:]):
            parts.append(key_name(ch[i]) + ('+' if ch[i + 1] > 0 else '-'))
            break
        parts.append(key_name(ch[i]))
        i += 1
    out = '+'.join(parts)
    if out.count('PAD ') > 1:                # 「PAD L+PAD X」を「PAD L+X」に
        first = out.index('PAD ')
        out = out[:first + 4] + out[first + 4:].replace('PAD ', '')
    return out


def _is_axis(ch):
    """末尾2要素が [軸コード, 符号] の形か。"""
    return (len(ch) >= 2 and ch[-1] in (1, -1)
            and NAMES.get(ch[-2], '').startswith('AX '))


def binding_name(chords, maxn=2):
    if not chords:
        return '(NONE)'
    return ' / '.join(chord_name(c) for c in chords[:maxn])


def _defaults_for(lay):
    """DEFAULTS は XBOX 配置で書いてあるので、必要なら入れ替えて返す。"""
    d = {k: [list(c) for c in v] for k, v in DEFAULTS.items()}
    if lay == 1:
        d = {k: swap_faces(v) for k, v in d.items()}
    return d


# ------------------------------------------------------------------ 本体
class InputMap:
    def __init__(self):
        self.binds = _defaults_for(layout)
        self.held = {k: False for k in ACTION_IDS}
        self.amount = {k: 0.0 for k in ACTION_IDS}   # アナログ軸の踏み込み量 0..1
        self.pressed = {k: False for k in ACTION_IDS}
        self._prev = dict(self.held)

    @property
    def layout_name(self):
        return LAYOUTS[layout]

    def set_layout(self, i):
        """ボタン配置を切り替える。現在の割り当てもまとめて入れ替える。"""
        global layout
        i = i % len(LAYOUTS)
        if i == layout:
            return
        layout = i
        self.binds = {k: swap_faces(v) for k, v in self.binds.items()}

    # ---------------------------------------------------------- 判定
    @staticmethod
    def _mod_held(m):
        """修飾キーが押されているか。タプルならアナログ軸。"""
        if isinstance(m, tuple):
            return pyxel.btnv(m[0]) * m[1] > AXIS_TH
        return pyxel.btn(m)

    @staticmethod
    def _mod_in(m, keys, ch):
        """その修飾キーが和音に含まれているか。"""
        if isinstance(m, tuple):
            return _is_axis(ch) and ch[-2] == m[0] and ch[-1] == m[1]
        return m in keys

    @staticmethod
    def _elem_held(code, sign=None, th=AXIS_TH):
        if sign is None:
            return pyxel.btn(code)
        return pyxel.btnv(code) * sign > th

    @staticmethod
    def _elem_amount(code, sign):
        """軸の踏み込み量を 0..1 で返す。しきい値から最大までを割り当てる。"""
        v = pyxel.btnv(code) * sign
        if v <= AXIS_TH:
            return 0.0
        return min(1.0, (v - AXIS_TH) / float(32767 - AXIS_TH))

    def _chord_amount(self, ch):
        """その和音の効き具合。ボタンなら1.0、軸なら倒した量。"""
        if not self._chord_held(ch):
            return 0.0
        if _is_axis(ch):
            return max(0.05, self._elem_amount(ch[-2], ch[-1]))
        return 1.0

    def _chord_held(self, ch, th=AXIS_TH):
        if _is_axis(ch):
            keys, axis = ch[:-2], (ch[-2], ch[-1])
        else:
            keys, axis = list(ch), None
        for k in keys:
            if not pyxel.btn(k):
                return False
        if axis and not self._elem_held(axis[0], axis[1], th):
            return False
        # 修飾キーを押しているのに和音に含まれていなければ無効
        for m in MODIFIERS:
            if not self._mod_in(m, keys, ch) and self._mod_held(m):
                return False
        return True

    def update(self):
        self._prev = dict(self.held)
        for a in ACTION_IDS:
            amt = 0.0
            for c in self.binds.get(a, []):
                amt = max(amt, self._chord_amount(c))
            h = amt > 0.0
            self.amount[a] = amt
            self.held[a] = h
            self.pressed[a] = h and not self._prev[a]

    def stick(self, action):
        """スティック単独の割り当ての倒し量 0..1。修飾つきやボタンは数えない。

        視点の左右振りだけは、スティックなら倒した位置で角度が決まり、
        十字キー（L2と同時押し）なら押している間だけ動く、と分けたい。
        操縦用の広い死帯を使うと半分倒して2割しか振れないので、ここでは
        死帯を抜けたあと倒し量をそのまま返す。
        """
        th = int(STICK_TH * 32767)
        amt = 0.0
        for c in self.binds.get(action, []):
            if not (_is_axis(c) and len(c) == 2 and self._chord_held(c, th)):
                continue
            r = min(1.0, pyxel.btnv(c[-2]) * c[-1] / 32767.0)
            amt = max(amt, r * min(1.0, (r - STICK_TH) / STICK_BLEND))
        return amt

    def axis(self, minus, plus, expo=0.0):
        """2方向の入力を -1..1 にまとめる。expo>0 で中央付近を鈍らせる。"""
        v = self.amount[minus] - self.amount[plus]
        if expo > 0.0:
            v = v * (1.0 - expo) + (v * v * v) * expo
        return v

    def clear(self):
        """押しっぱなし扱いにして、直後の1フレームで再入力されるのを防ぐ。

        update() の先頭で _prev = held を取るので、ここで held を立てておく。
        """
        for a in ACTION_IDS:
            self.held[a] = True
            self.pressed[a] = False

    # ---------------------------------------------------------- 設定
    def label(self, action):
        return binding_name(self.binds.get(action, []))

    def set(self, action, chord):
        self.binds[action] = [list(chord)]

    def conflicts(self, action, chord):
        """OK と CANCEL が同じにならないようにするための確認。"""
        for other in ('ok', 'cancel'):
            if other != action and list(chord) in [list(c) for c in self.binds[other]]:
                return other
        return None

    def to_dict(self):
        return {k: [list(c) for c in v] for k, v in self.binds.items()}

    def from_dict(self, d):
        for k, v in (d or {}).items():
            if k in self.binds and isinstance(v, list) and v:
                self.binds[k] = [list(c) for c in v]

    def reset(self):
        self.binds = _defaults_for(layout)


# ------------------------------------------------------------------ 押されたキーの取得
_SCAN = None


def scan_codes():
    """割り当て変更時に走査するキー・ボタンの一覧。"""
    global _SCAN
    if _SCAN is None:
        out = []
        for n in dir(pyxel):
            if n.startswith('KEY_') and n not in ('KEY_UNKNOWN',):
                out.append(getattr(pyxel, n))
            elif n.startswith('GAMEPAD1_BUTTON_'):
                out.append(getattr(pyxel, n))
        _SCAN = sorted(set(out))
    return _SCAN


AXES = [(LX, 1), (LX, -1), (LY, 1), (LY, -1), (LT, 1), (RT, 1),
        (_G.GAMEPAD1_AXIS_RIGHTX, 1), (_G.GAMEPAD1_AXIS_RIGHTX, -1),
        (_G.GAMEPAD1_AXIS_RIGHTY, 1), (_G.GAMEPAD1_AXIS_RIGHTY, -1)]


def capture():
    """いま押されているものを和音として返す。無ければ None。"""
    plain = [m for m in MODIFIERS if not isinstance(m, tuple)]
    mods = [m for m in plain if pyxel.btn(m)]
    ax_mod = next((m for m in MODIFIERS
                   if isinstance(m, tuple)
                   and pyxel.btnv(m[0]) * m[1] > AXIS_TH), None)
    for code in scan_codes():
        if code in plain:
            continue
        if pyxel.btnp(code):
            ch = mods + [code]
            if ax_mod:                      # 軸の修飾は和音の末尾に置く
                ch += [ax_mod[0], ax_mod[1]]
            return ch
    if ax_mod is None:                      # 軸は和音に1つしか持てない
        for code, sign in AXES:
            if pyxel.btnv(code) * sign > AXIS_TH:
                return mods + [code, sign]
    return None


# ------------------------------------------------------------------ 保存
def _writable(d, create=False):
    try:
        if create:
            d.mkdir(parents=True, exist_ok=True)
        elif not d.is_dir():
            return False
        t = d / '.pfs_write_test'
        t.write_text('', encoding='utf-8')
        t.unlink()
        return True
    except OSError:
        return False


_CFG = None


def data_path(name):
    """設定ファイルと同じ場所に、別名のデータファイルを置く。"""
    return config_path().parent / name


def save_json(name, data):
    try:
        data_path(name).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                   encoding='utf-8')
        return True
    except OSError:
        return False


def load_json(name):
    try:
        return json.loads(data_path(name).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def config_path():
    """書き込める場所に設定ファイルを置く。

    ランチャーによってはカレントディレクトリが読み取り専用なので、
    pyxapp と同じ階層 → カレント → ホーム の順に試す。
    """
    global _CFG
    if _CFG is not None:
        return _CFG
    cands = []
    env = os.environ.get('PFS_CONFIG_DIR')
    if env:
        cands.append(Path(env))
    for a in sys.argv[1:]:
        p = Path(a)
        if p.suffix.lower() in ('.pyxapp', '.zip'):
            cands.append(p.resolve().parent)
    try:
        cands.append(Path.cwd())
    except OSError:
        pass
    home = Path.home() / '.config' / 'pfs'
    for d in cands:
        if _writable(d):
            _CFG = d / CONFIG_NAME
            return _CFG
    if _writable(home, create=True):            # 最後の砦だけ作る
        _CFG = home / CONFIG_NAME
        return _CFG
    _CFG = Path.cwd() / CONFIG_NAME
    return _CFG


def save_config(data):
    try:
        config_path().write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                 encoding='utf-8')
        return True
    except OSError:
        return False


def load_config():
    try:
        return json.loads(config_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
