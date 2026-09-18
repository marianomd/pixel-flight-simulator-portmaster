"""BGM再生。pfs_assets/bgm 内の音楽ファイルをシーケンス／シャッフルで流す。

Pyxel は Sound.pcm() で WAV/OGG/MP3/FLAC を読める（内部は symphonia）。
日本語ファイル名も扱える。曲の終わりは pyxel.play_pos() が None を返すことで判る。
"""
import os
import random
import sys
from pathlib import Path

import pyxel

CH = 3                     # BGM専用チャンネル
SLOT = 63                  # サウンドスロット
EXTS = ('.wav', '.ogg', '.mp3', '.flac', '.m4a')
# 他のゲームと同居するので、ありふれた assets/ ではなく専用の名前にする
DIR_NAME = Path('pfs_assets') / 'bgm'
MODES = ('SEQUENCE', 'SHUFFLE')


# 起動した場所と、渡された pyxapp の場所を **読み込み時に** 押さえておく。
# pyxel はアプリを走らせる前に作業ディレクトリを展開先へ移すので、あとから
# Path.cwd() や相対パスの resolve() を呼ぶと展開先を指してしまい、
# 隣に置いた pfs_assets を見失う（音とBGMが鳴らなくなる）。
try:
    _START_CWD = Path.cwd()
except OSError:
    _START_CWD = None
_ARGV_DIRS = []
for _a in sys.argv[1:]:                          # pyxel play foo.pyxapp
    _p = Path(_a)
    if _p.suffix.lower() in ('.pyxapp', '.zip'):
        try:
            _ARGV_DIRS.append(_p.resolve().parent)
        except OSError:
            pass


def candidate_dirs(name=None, env_var='PFS_BGM_DIR'):
    """外置きアセットを探す場所。pyxapp は展開先で動くので実行時の位置も見る。"""
    name = DIR_NAME if name is None else name
    out = []
    if _START_CWD is not None:
        out.append(_START_CWD / name)
    try:
        out.append(Path.cwd() / name)
    except OSError:
        pass
    for d in _ARGV_DIRS:
        out.append(d / name)
    here = Path(__file__).resolve().parent
    out.append(here / name)                      # 開発時
    out.append(here.parent / name)               # pyxapp展開先の親
    env = os.environ.get(env_var)
    if env:
        out.insert(0, Path(env))
    seen, uniq = set(), []
    for p in out:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)
    return uniq


def scan():
    """最初に見つかったディレクトリの曲一覧を返す。"""
    for d in candidate_dirs():
        try:
            if not d.is_dir():
                continue
            files = sorted(p for p in d.iterdir()
                           if p.is_file() and p.suffix.lower() in EXTS)
            if files:
                return d, files
        except OSError:
            continue
    return None, []


class Bgm:
    def __init__(self, volume=5):
        self.dir, self.tracks = scan()
        self.mode = 0                  # 0=SEQUENCE 1=SHUFFLE
        self.volume = volume           # 0..10
        self.index = -1
        self.order = list(range(len(self.tracks)))
        self.playing = False
        self.error = ''
        self._apply_gain()

    # ------------------------------------------------------------ 情報
    @property
    def count(self):
        return len(self.tracks)

    @property
    def mode_name(self):
        return MODES[self.mode]

    def title(self, maxlen=20):
        """Pyxelの組み込みフォントはASCIIのみなので、表示できる文字だけに整形する。

        日本語ファイル名でも再生自体はできる（表示が番号だけになる）。
        """
        if not self.tracks or self.index < 0:
            return '---'
        stem = self.tracks[self.index].stem
        safe = ''.join(c for c in stem if 32 <= ord(c) < 127).strip()
        head = '%d/%d' % (self.index + 1, len(self.tracks))
        if len(safe) < 2:
            return head
        room = maxlen - len(head) - 1
        if len(safe) > room:
            safe = safe[:max(1, room - 1)] + '.'
        return '%s %s' % (head, safe.upper())

    # ------------------------------------------------------------ 制御
    def _apply_gain(self):
        try:
            pyxel.channels[CH].gain = 0.08 * self.volume
        except Exception:
            pass

    def set_volume(self, v):
        self.volume = max(0, min(10, v))
        self._apply_gain()
        if self.volume == 0:
            self.stop()
        elif not self.playing and self.tracks:
            self.start()

    def set_mode(self, m):
        self.mode = m % len(MODES)
        self._reorder()

    def _reorder(self):
        self.order = list(range(len(self.tracks)))
        if self.mode == 1:
            random.shuffle(self.order)

    def start(self):
        if not self.tracks or self.volume == 0:
            return
        self._reorder()
        self._play(0)

    def stop(self):
        self.playing = False
        try:
            pyxel.stop(CH)
        except Exception:
            pass

    def next(self, step=1):
        if not self.tracks:
            return
        pos = self.order.index(self.index) if self.index in self.order else -1
        self._play((pos + step) % len(self.order))

    def _play(self, order_pos):
        self.index = self.order[order_pos % len(self.order)]
        path = self.tracks[self.index]
        try:
            pyxel.sounds[SLOT].pcm(str(path))
            pyxel.play(CH, SLOT, loop=False)
            self.playing = True
            self.error = ''
        except Exception as e:                    # 壊れたファイルは飛ばす
            self.error = '%s: %s' % (path.name, type(e).__name__)
            self.playing = False

    def update(self):
        """曲が終わったら次の曲へ。"""
        if not self.playing or not self.tracks:
            return
        try:
            if pyxel.play_pos(CH) is None:
                self.next()
        except Exception:
            self.playing = False
