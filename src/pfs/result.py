"""着陸後のリザルト画面。

1行のバナーに全部詰めると、報酬・経験値・ダメージが読み取れない。
完全に停止して精算したところで、収支を表にして出す。
Aかスタートで閉じる。開いている間は世界を止める（メニューと同じ）。
"""
import pyxel

import fx
import lang

W, H = 256, 192
BG, FG, SEL, DIM, ACC = 0, 11, 14, 5, 12
PLUS, MINUS = 11, 13        # 収入は緑、支出は赤。どちらも時刻で変わらない色
LH = 11                     # 行間。日本語フォントが10pxなので詰めない
BAR_W = 56
TOP, SEP, FOOT = 15, 8, 15  # 見出しの下・区切り線・脚注に使う高さ
# 5番と12番は時刻で色が変わり、夜は地の色と見分けがつかない。
# リザルトを出している間だけ固定する（閉じるときに fx.invalidate で戻す）
UI_COLS = ((DIM, 0x5a6a78), (ACC, 0xf0d070))


def set_size(w, h):
    global W, H
    W, H = w, h


def _f():
    return lang.font()


def _txt(x, y, s, col):
    pyxel.text(x, y, s, col, _f())


def _w(s):
    f = _f()
    return f.text_width(s) if f else len(s) * 4


def _rtxt(x, y, s, col):
    """右端 x に揃えて書く。金額は桁がそろっていないと比べられない。"""
    _txt(x - _w(s), y, s, col)


def _note(s):
    """仕事の講評。「QUALITY 87%」だけは数字つきなので組み立て直す。"""
    if s.startswith('QUALITY'):
        try:
            return lang.T('QUALITY %d%%') % int(s.split()[1].rstrip('%'))
        except (IndexError, ValueError):
            pass
    return lang.T(s)


def _mmss(sec):
    return '%d:%02d' % (int(sec) // 60, int(sec) % 60)


class Result:
    """精算の内訳をためて表示する。"""

    def __init__(self, app):
        self.app = app
        self.open = False
        self.d = {}
        self.t = 0             # 開いてからのフレーム数（誤爆防止）

    def show(self, d):
        self.d = d
        self.open = True
        self.t = 0

    def update(self, imap, auto=False):
        self.t += 1
        if auto and self.t > 120:     # 自動テスト用: ひとりでに閉じる
            self.open = False
            fx.invalidate()
            return
        if self.t < 12:        # 着陸直後の連打で消えないように少し待つ
            return
        if (imap.pressed['ok'] or imap.pressed['cancel']
                or imap.pressed['menu']):
            self.open = False
            fx.invalidate()        # 借りていたパレットを時刻のものへ戻す

    # ------------------------------------------------------------ 描画
    def _lines(self):
        """行数を数える。中身によって高さが変わる。"""
        d = self.d
        n = 6                                   # 見出し＋内訳3＋得点＋操縦
        if d.get('career'):
            n += len(d.get('rows', ())) + 1     # 収支＋所持金
            n += len(d.get('bonus', ()))
            n += 2                              # 経験値とレベル
            n += 1 if d.get('dmg') else 0
            n += 1 if d.get('note') else 0
        return n

    def draw(self):
        d = self.d
        pyxel.dither(0.72)
        pyxel.rect(0, 0, W, H, BG)
        pyxel.dither(1.0)
        for i, c in UI_COLS:
            pyxel.colors[i] = c
        h = min(H - 6, TOP + self._lines() * LH
                + (SEP * 2 if d.get('career') else 0) + FOOT)
        x, w = 8, W - 16
        y = (H - h) // 2
        pyxel.rect(x, y, w, h, BG)
        pyxel.rectb(x, y, w, h, FG)
        pyxel.rect(x + 1, y + 1, w - 2, 11, FG)
        _txt(x + 4, y + 2, lang.T('FLIGHT RESULT'), BG)
        left, right = x + 5, x + w - 6
        yy = y + 15
        yy = self._landing(left, yy, right, d)
        if d.get('career'):
            yy = self._sep(x, w, yy)
            yy = self._money(left, yy, right, d)
            yy = self._sep(x, w, yy)
            self._growth(left, yy, right, d)
        foot = lang.T('PRESS %s') % self.app.imap.label('ok').split(' / ')[0]
        _txt(left, y + h - 13, foot, DIM)

    def _sep(self, x, w, y):
        pyxel.line(x + 4, y + 1, x + w - 5, y + 1, DIM)
        return y + SEP

    # ------------------------------------------------------------ 着陸内容
    def _landing(self, x, y, r, d):
        _txt(x, y, lang.T('LANDING'), ACC)
        _rtxt(r, y, '%s  %s' % (d['apt'], lang.T(d['grade'])),
              SEL if d['on_rwy'] else MINUS)
        y += LH
        # 得点は3つの内訳でできている。どこで落としたかが分かるように出す
        pw = _w('00/00') + 6
        for name, val, pt, full in d['detail']:
            _txt(x + 5, y, lang.T(name), FG)
            _rtxt(r - pw, y, val, FG)
            _rtxt(r, y, '%d/%d' % (pt, full), SEL if pt >= full * 0.8 else DIM)
            y += LH
        _txt(x + 5, y, lang.T('SCORE'), ACC)
        s = d['score']
        _rtxt(r, y, '%d P' % s, SEL)
        bx = r - _w('000 P') - BAR_W - 8
        pyxel.rectb(bx, y + 2, BAR_W, 5, DIM)
        if s > 0:
            pyxel.rect(bx + 1, y + 3, int((BAR_W - 2) * s / 100.0), 3, ACC)
        y += LH
        # ILSを使ったかどうかの評価。自動でも罰は無いので色は落とすだけ
        f, fmt, arg = d['hand']
        _txt(x + 5, y, lang.T('FLYING'), ACC)
        _rtxt(r, y, lang.T(fmt) % arg if arg is not None else lang.T(fmt),
              SEL if f >= 0.999 else (FG if f > 0.0 else DIM))
        return y + LH

    # ------------------------------------------------------------ 収支
    def _money(self, x, y, r, d):
        for name, extra, val, col in d['rows']:
            _txt(x + 5, y, lang.T(name) + extra, FG)
            _rtxt(r, y, lang.T(val) if val.isupper() else val, col)
            y += LH
        _txt(x, y, lang.T('CREDITS'), ACC)
        cr = '%d CR' % d['cr1']
        _rtxt(r, y, cr, SEL)
        ar = r - _w(cr) - 8
        _rtxt(ar, y, '>', DIM)
        _rtxt(ar - _w('> '), y, '%d' % d['cr0'], DIM)
        y += LH
        for name, fmt, n in d.get('bonus', ()):  # 収支には出ないが得をしたぶん
            _txt(x + 5, y, lang.T(name), ACC)
            _rtxt(r, y, lang.T(fmt) % n, ACC)
            y += LH
        return y

    # ------------------------------------------------------------ 成長
    def _growth(self, x, y, r, d):
        _txt(x, y, lang.T('EXPERIENCE'), ACC)
        _rtxt(r, y, '+%d XP' % d['xp'], SEL if d['xp'] else DIM)
        y += LH
        up = d['lv1'] > d['lv0']
        # 上がったときは「LV 7 > 8」。新しい値だけだと何段上がったか誤解する
        lvs = ('LV %d > %d' % (d['lv0'], d['lv1'])) if up else ('LV %d' % d['lv1'])
        _txt(x + 5, y, lvs, SEL if up else FG)
        if up:
            _txt(x + 5 + _w(lvs) + 8, y, lang.T('LEVEL UP!'), SEL)
        elif d['need'] is not None:
            _rtxt(r, y, lang.T('NEXT %d XP') % d['need'], DIM)
        else:
            _rtxt(r, y, lang.T('RATING MAXED'), ACC)
        y += LH
        if d['dmg'] is not None:
            _txt(x, y, lang.T('DAMAGE'), ACC)
            tot = lang.T('TOTAL %d%%') % d['dmg'][1]
            _rtxt(r, y, tot, MINUS if d['dmg'][1] > 60
                  else (ACC if d['dmg'][1] > 25 else DIM))
            _rtxt(r - _w(tot) - 8, y, '+%.0f%%' % d['dmg'][0],
                  MINUS if d['dmg'][0] > 0.5 else DIM)
            y += LH
        if d.get('note'):
            text, ok = d['note']
            _txt(x, y, _note(text), ACC if ok else MINUS)
            y += LH
        return y
