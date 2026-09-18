"""音。エンジン音・警報・効果音。Pyxelのサウンドスロットを使う。

エンジンは回転数に応じて6段のドローンを切り替え、チャンネル0でループ再生する。
"""
import pyxel

ENG0 = 0          # サウンドスロット 0..5 = エンジン
SND_STALL = 6
SND_TOUCH = 7
SND_GEAR = 8
SND_THUNDER = 9
SND_AP_ON = 10             # 自動操縦 入
SND_AP_OFF = 11            # 自動操縦 切
SND_WARN = 12              # 警報（燃料・エンジン・ウィンドシア）
SND_CHIME = 13             # よいこと（リング通過・見どころ・依頼達成）
SND_FAIL = 14              # わるいこと（依頼失敗）
SND_BLIP = 15              # 対地高度のコール
SND_LEVEL = 16             # レベルアップ
# チャンネル: 0=エンジン 1=音声(atc.py) 2=効果音 3=BGM
SE_CH = (0, 2)

_NOTES = ('c1', 'd1', 'f1', 'g1', 'a1', 'c2')


def setup():
    for i, n in enumerate(_NOTES):
        pyxel.sounds[ENG0 + i].set(n * 4, 'n', '2', 'n', 26)
    pyxel.sounds[SND_STALL].set('a3a3', 'p', '4', 'n', 10)
    pyxel.sounds[SND_TOUCH].set('f0c0', 'n', '54', 'f', 9)
    pyxel.sounds[SND_GEAR].set('c2', 'p', '3', 'n', 12)
    # 雷鳴。低いノイズを長く伸ばして遠くの轟きにする
    pyxel.sounds[SND_THUNDER].set('c0c0g0c0', 'n', '7654', 'f', 22)
    # 自動操縦: 入は「ピー」、切は「ピーピーピー」
    pyxel.sounds[SND_AP_ON].set('e3', 'p', '5', 'n', 14)
    pyxel.sounds[SND_AP_OFF].set('e3re3re3', 'p', '5', 'n', 9)
    pyxel.sounds[SND_WARN].set('a3f3a3f3', 'p', '6', 'n', 11)
    pyxel.sounds[SND_CHIME].set('e3a3', 'p', '54', 'n', 12)
    pyxel.sounds[SND_FAIL].set('a2e2c2', 'p', '543', 'n', 14)
    pyxel.sounds[SND_BLIP].set('c3', 'p', '3', 'n', 10)
    # レベルアップ。上がっていく分散和音
    pyxel.sounds[SND_LEVEL].set('c3e3g3c4', 'p', '5566', 'n', 13)


class Audio:
    def __init__(self, volume=5):
        self.muted = False
        self.volume = volume            # 0..10
        self._band = -1
        self._stall_t = 0
        try:
            setup()
            self.ok = True
        except Exception:
            self.ok = False
        self._apply_gain()

    def _apply_gain(self):
        g = 0.025 * self.volume
        try:
            for ch in SE_CH:
                pyxel.channels[ch].gain = g
        except Exception:
            pass

    def set_volume(self, v):
        self.volume = max(0, min(10, v))
        self._apply_gain()
        if self.volume == 0:
            self._stop()
        self.muted = self.muted and True

    def set_muted(self, v):
        self.muted = bool(v)
        if self.muted:
            self._stop()

    def _stop(self):
        for ch in SE_CH:
            try:
                pyxel.stop(ch)
            except Exception:
                pass
        self._band = -1

    def toggle(self):
        self.muted = not self.muted
        if self.muted:
            self._stop()
        return self.muted

    def update(self, ac, frame):
        if not self.ok or self.muted or self.volume == 0:
            return
        # スロットルが段の境目で揺れるとループ音を毎フレーム貼り直してしまうので、
        # ヒステリシスを入れて実際に段が変わったときだけ鳴らし直す。
        t = ac.throttle
        band = self._band
        if band < 0:
            band = int(min(5, max(0, t * 5.99)))
        else:
            lo, hi = band / 6.0, (band + 1) / 6.0
            if t < lo - 0.035:
                band -= 1
            elif t > hi + 0.035:
                band += 1
            band = max(0, min(5, band))
        if band != self._band:
            pyxel.play(0, ENG0 + band, loop=True)
            self._band = band
        if ac.stalled:
            if frame - self._stall_t > 24:
                self._stall_t = frame
                pyxel.play(2, SND_STALL)

    def touchdown(self, vs):
        if self.ok and not self.muted and self.volume:
            pyxel.play(2, SND_TOUCH)

    def _play(self, snd, ch=2):
        if self.ok and not self.muted and self.volume:
            pyxel.play(ch, snd)

    def autopilot(self, on):
        self._play(SND_AP_ON if on else SND_AP_OFF)

    def warn(self):
        self._play(SND_WARN)

    def chime(self):
        self._play(SND_CHIME)

    def level_up(self):
        self._play(SND_LEVEL)

    def fail(self):
        self._play(SND_FAIL)

    def blip(self):
        self._play(SND_BLIP)

    def thunder(self, near):
        """near: 0(遠い)〜1(近い)。近いほど大きく鳴る。"""
        if self.ok and not self.muted and self.volume and near > 0.05:
            pyxel.play(2, SND_THUNDER)

    def click(self):
        if self.ok and not self.muted and self.volume:
            pyxel.play(2, SND_GEAR)
