"""管制通信と音声警報の再生。

クリップは pfs_assets/atc に外置きしてある（BGMと同じ扱い）。

**無線と機上警報は別のチャンネルで鳴らす。** 4つの標準チャンネルは
エンジン・無線・効果音・BGMで埋まっているので、警報用に1本足している。
同じチャンネルだと、交信の途中で高度コールやウィンドシアが割り込んで
前の声を消してしまい、雰囲気が壊れる。実機でも無線と機上警報は別系統。
"""
from pathlib import Path

import pyxel

import atc_data
import bgm

CH = 1                      # 無線（管制官とパイロット）
SLOT = 62                   # 無線のサウンド枠
SLOT_W = 61                 # 警報のサウンド枠。別々でないと上書きされる
DIR_NAME = Path('pfs_assets') / 'atc'
GAP = 0.35                  # クリップの間にあける時間[秒]
MAX_Q = 4                   # 溜めすぎない


def find_dir():
    for d in bgm.candidate_dirs(DIR_NAME, 'PFS_ATC_DIR'):
        try:
            if d.is_dir() and any(d.glob('*.wav')):
                return d
        except OSError:
            continue
    return None


class Atc:
    def __init__(self, volume=6):
        self.dir = find_dir()
        self.on = True
        self.volume = volume        # 0..10
        self.q = []                 # 無線の順番待ち
        self.wait = 0.0             # いま鳴っている（＋間合いの）残り時間
        self.qw = []                # 機上警報の順番待ち
        self.wait_w = 0.0
        self.last = ''
        self.chw = self._add_channel()
        self._apply_gain()

    @staticmethod
    def _add_channel():
        """警報用のチャンネルを1本増やす。増やせなければ無線と同居する。"""
        try:
            pyxel.channels.append(pyxel.Channel())
            return len(pyxel.channels) - 1
        except Exception:
            return CH

    @property
    def ok(self):
        return self.dir is not None

    def set_volume(self, v):
        self.volume = max(0, min(10, v))
        self._apply_gain()

    def _apply_gain(self):
        for ch in {CH, self.chw}:
            try:
                pyxel.channels[ch].gain = 0.09 * self.volume
            except Exception:
                pass

    # ------------------------------------------------------------ 再生
    def say(self, *names):
        """順に鳴らす。機上の警報（g_）は別チャンネルで無線に重ねる。

        高度のコールが無線の交信を待っていると、言い終わるころには接地している。
        かといって無線を消すと交信が尻切れになるので、両方鳴らす。
        """
        if not (self.on and self.ok and self.volume):
            return
        if names and names[0].startswith('g_'):
            # 新しい警報が優先。古い警報は捨てるが、無線には触れない
            self.qw = list(names)
            self.wait_w = 0.0
            return
        for n in names:
            if len(self.q) < MAX_Q:
                self.q.append(n)

    def clear(self):
        self.q = []
        self.qw = []

    def update(self, dt):
        self.wait = self._pump(dt, self.wait, self.q, CH, SLOT)
        if self.chw != CH:
            self.wait_w = self._pump(dt, self.wait_w, self.qw, self.chw, SLOT_W)
        elif not self.q:                  # チャンネルを増やせなかったとき
            self.wait = self._pump(dt, self.wait, self.qw, CH, SLOT)

    def _pump(self, dt, wait, q, ch, slot):
        """1系統ぶんの再生。残り時間を返す。"""
        if wait > 0.0:
            return wait - dt
        if not q:
            return 0.0
        name = q.pop(0)
        try:
            pyxel.sounds[slot].pcm(str(self.dir / (name + '.wav')))
            pyxel.play(ch, slot)
        except Exception:
            return 0.0
        self.last = name
        return atc_data.DUR.get(name, 2.0) + GAP
