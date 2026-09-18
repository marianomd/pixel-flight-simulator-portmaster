"""機体の諸元。5機種それぞれに得意な仕事がある。

cruise と range_km は表示用の実測値（スロットル72%、キャリアの燃料基準）。
推定式で出すと実際とずれるので、測った値をそのまま持たせてある。

数値を散らすだけでなく、「短い滑走路に降りられる」「速いが失速も速い」など
役割が分かれるようにしてある。aircraft.Aircraft のクラス定数を、機体ごとの
値でインスタンス側から上書きする。
"""
import math

# id, 表示名, 価格, 説明
SPECS = (
    dict(id='TRAINER', name='TRAINER', price=0,
         desc='SLOW BUT FORGIVING',
         mass=1100.0, wing=16.2, cl0=0.30, cla=5.0, stall_deg=15.0,
         cd0=0.032, k=0.045, thrust=3050.0, vne=82.0,
         burn=1.0, tank=1.0, repair=1.0, gear=1.0, cruise=94, range_km=39, cap=180),
    dict(id='BUSH', name='BUSH PLANE', price=3800,
         desc='SHORT FIELD, TOUGH GEAR',
         mass=1150.0, wing=21.0, cl0=0.34, cla=5.2, stall_deg=16.0,
         cd0=0.048, k=0.050, thrust=3600.0, vne=72.0,
         burn=1.15, tank=1.1, repair=0.85, gear=0.55, cruise=80, range_km=31, cap=300),
    dict(id='TOURER', name='TOURER', price=9000,
         desc='LONG RANGE, STEADY',
         mass=1500.0, wing=19.5, cl0=0.32, cla=5.0, stall_deg=15.0,
         cd0=0.029, k=0.042, thrust=3700.0, vne=90.0,
         burn=1.0, tank=1.45, repair=1.2, gear=0.8, cruise=98, range_km=58, cap=420),
    dict(id='SPORT', name='SPORT', price=6500,
         desc='FAST, LANDS FAST TOO',
         mass=1050.0, wing=13.0, cl0=0.28, cla=4.8, stall_deg=14.0,
         cd0=0.024, k=0.040, thrust=4350.0, vne=108.0,
         burn=1.5, tank=0.85, repair=1.45, gear=1.3, cruise=128, range_km=30, cap=120),
    dict(id='TWIN', name='TWIN', price=15000,
         desc='POWERFUL, DEMANDING',
         mass=2100.0, wing=21.0, cl0=0.30, cla=5.0, stall_deg=15.0,
         cd0=0.034, k=0.043, thrust=7400.0, vne=115.0,
         burn=2.1, tank=1.5, repair=1.9, gear=0.95, cruise=113, range_km=33, cap=760),
)

BY_ID = {s['id']: s for s in SPECS}
IDS = tuple(s['id'] for s in SPECS)
FIRST = 'TRAINER'


def spec(pid):
    return BY_ID.get(pid, BY_ID[FIRST])


def apply_spec(ac, pid):
    """機体の諸元を機体オブジェクトへ移す。"""
    s = spec(pid)
    ac.MASS = s['mass']
    ac.WING = s['wing']
    ac.CL0 = s['cl0']
    ac.CLA = s['cla']
    ac.A_STALL = math.radians(s['stall_deg'])
    ac.CD0 = s['cd0']
    ac.K = s['k']
    ac.THRUST = s['thrust']
    ac.VNE = s['vne']
    ac.spec_id = pid


def stall_kt(pid, flap=0):
    """フラップ位置での失速速度[kt]（表示用）。"""
    s = spec(pid)
    cl = s['cl0'] + s['cla'] * math.radians(s['stall_deg'] - flap * 0.055) \
        + flap * 0.022
    v = math.sqrt(2.0 * s['mass'] * 9.81 / (1.225 * s['wing'] * cl))
    return v * 1.94384
