"""受注後の打ち合わせ画面。オペレーターとパイロットの会話。

仕事のやりかたと今日の条件を、その場で会話として伝える。説明書を開かずに
済むうえ、機体の損耗にも気づける。Aで送り、最後まで送ると閉じる。

顔絵は portraits.py（make_portraits.py が生成）から読む。まだ無ければ
簡単な人影を描いて代用する。会話中は専用の16色を当て、閉じるときに
fx.invalidate() で時刻のパレットへ戻す。
"""
import pyxel

import fx
import lang

try:
    import portraits
except ImportError:                     # 顔絵はあとから差し込める
    portraits = None

W, H = 256, 192
OP, PILOT = 0, 1                        # 話者

# 顔絵が無いときの色。12〜15はUI用に必ずこの色にする
FALLBACK = (0x101018, 0x2a3550, 0x4a6a90, 0x86a8c8,
            0xc8a882, 0x8a6a4a, 0x604838, 0xd8c8a8,
            0x3a4a3a, 0x6a8a5a, 0x203040, 0x505868,
            0x0a0c14, 0xf0f4f0, 0x4ce896, 0xf0b030)
BG, FG, ACC, WARN = 12, 13, 14, 15      # UIに使う4色（顔絵と共有しない）

PORT = 80                               # 顔絵の一辺
LH = 11                                 # 行間
PAD = 5
ROWS = 4                                # 本文の行数。英語は日本語より長い
# 名札とボタンの枠。日本語の字は描画位置から10px、英字は+2〜+8の7px。
# 14pxの枠に+2で描くと、日本語は上下2px、英字は上4px下3pxとどちらも中央に来る
TAG_H = 14
TAG_TY = 2
TAG_PAD = 6                             # 文字の左右に取る余白


def set_size(w, h):
    global W, H
    W, H = w, h


def _f():
    return lang.font()


def _w(s):
    f = _f()
    return f.text_width(s) if f else len(s) * 4


def _tag(x, y, text, fill, ink):
    """枠の中に文字を上下中央で置く。幅は文字に合わせて返す。"""
    w = _w(text) + TAG_PAD * 2
    pyxel.rect(x, y, w, TAG_H, fill)
    pyxel.rectb(x, y, w, TAG_H, FG)
    pyxel.text(x + TAG_PAD, y + TAG_TY, text, ink, _f())
    return w


def wrap(s, px):
    """幅pxに収まるように折る。

    日本語は単語境界が無いので1文字ずつ測る。英語で同じことをすると
    単語の途中で折れるので、行の中に空白があればそこまで戻す。
    """
    out, line = [], ''
    for ch in s:
        if ch == '\n':
            out.append(line)
            line = ''
            continue
        if _w(line + ch) > px and line:
            cut = line.rfind(' ')
            if cut > 0 and ch != ' ':
                out.append(line[:cut])
                line = line[cut + 1:]
            else:
                out.append(line.rstrip())
                line = ''
        if line or ch != ' ':
            line += ch
    if line:
        out.append(line)
    return out


class Briefing:
    """会話の進行と描画。"""

    def __init__(self, app):
        self.app = app
        self.open = False
        self.lines = []                 # [(話者, 本文), ...]
        self.i = 0
        self.t = 0
        self.on_accept = None           # 受けるを選んだときに呼ぶ
        self.on_decline = None
        self.choosing = False
        self.sel = 0

    def show(self, lines, on_accept=None, on_decline=None):
        """会話を出す。on_accept があれば最後に受注の可否を尋ねる。"""
        if not lines:
            return
        self.lines = list(lines)
        self.i = 0
        self.t = 0
        self.on_accept = on_accept
        self.on_decline = on_decline
        self.choosing = False
        self.sel = 0
        self.open = True

    def close(self):
        self.open = False
        fx.invalidate()                 # 借りていたパレットを時刻のものへ戻す

    def update(self, imap, auto=False):
        self.t += 1
        if auto and self.t > 90:        # 自動テスト用: ひとりでに閉じる
            self.close()
            return
        if self.t < 10:                 # 受注のAで飛ばさないよう少し待つ
            return
        if self.choosing:
            self._choose(imap)
            return
        if imap.pressed['ok'] or imap.pressed['menu']:
            self.i += 1
            self.t = 10
            if self.i >= len(self.lines):
                if self.on_accept is not None:
                    self.choosing = True    # 受けるかどうかを尋ねる
                    self.i = len(self.lines) - 1
                else:
                    self.close()
        elif imap.pressed['cancel']:
            self.close()

    def _choose(self, imap):
        """受ける／やめておく。断ったときは仕事一覧に残る。"""
        if imap.pressed['roll_left']:
            self.sel = 0
        if imap.pressed['roll_right']:
            self.sel = 1
        if imap.pressed['cancel']:
            self.sel = 1
        elif not imap.pressed['ok']:
            return
        cb = self.on_accept if self.sel == 0 else self.on_decline
        self.on_accept = self.on_decline = None
        self.choosing = False
        more = cb() if cb else None
        if more:                        # 返事が続くなら会話を延長する
            self.lines += list(more)
            self.i += 1
            self.t = 10
        else:
            self.close()

    # ------------------------------------------------------------ 描画
    def _palette(self):
        pal = portraits.PALETTE if portraits else FALLBACK
        for i, c in enumerate(pal):
            pyxel.colors[i] = c

    def draw(self):
        if not self.lines:
            return
        who, text = self.lines[min(self.i, len(self.lines) - 1)]
        self._palette()                 # 会話中は顔絵用の16色を借りる
        pyxel.dither(0.96)
        pyxel.rect(0, 0, W, H, BG)
        pyxel.dither(1.0)
        box_h = LH * ROWS + 18
        by = H - box_h - 4
        # 顔絵。話し手を手前に大きく、聞き手は反対側に置く
        px = 6 if who == OP else W - PORT - 6
        self._portrait(px, by - PORT - 12, who)
        pyxel.rect(4, by, W - 8, box_h, BG)
        pyxel.rectb(4, by, W - 8, box_h, FG)
        name = lang.T('OPERATOR' if who == OP else 'PILOT')
        nw = _w(name) + TAG_PAD * 2
        nx = 8 if who == OP else W - 12 - nw
        _tag(nx, by - 9, name, FG, BG)
        y = by + 12
        for ln in wrap(text, W - 8 - PAD * 2)[:ROWS]:
            pyxel.text(9, y, ln, FG, _f())
            y += LH
        if self.choosing:
            self._choice(by + box_h - 16)
        elif pyxel.frame_count % 30 < 20:   # 送りの合図
            n = '%d/%d' % (self.i + 1, len(self.lines))
            pyxel.text(W - 12 - _w(n), by + box_h - 9, n, ACC, _f())

    def _choice(self, y):
        """受注の可否。枠の下端に2択を並べる。"""
        labels = (lang.T('ACCEPT'), lang.T('DECLINE'))
        wid = [_w(t) + TAG_PAD * 2 for t in labels]
        x = W - 10 - wid[0] - wid[1] - 6
        for i, t in enumerate(labels):
            on = (i == self.sel)
            x += _tag(x, y, t, FG if on else BG, BG if on else FG) + 6

    def _portrait(self, x, y, who):
        if portraits is not None:
            pyxel.blt(x, y, portraits.image(who), 0, 0, PORT, PORT)
            pyxel.rectb(x - 1, y - 1, PORT + 2, PORT + 2, FG)
            return
        # 顔絵が届くまでの仮の人影
        pyxel.rect(x, y, PORT, PORT, 1)
        pyxel.rectb(x - 1, y - 1, PORT + 2, PORT + 2, FG)
        cx = x + PORT // 2
        pyxel.circ(cx, y + 24, 13, 4 if who == OP else 5)
        pyxel.circ(cx, y + 66, 26, 2 if who == OP else 3)
        pyxel.rect(x, y + PORT, PORT, 4, 1)
