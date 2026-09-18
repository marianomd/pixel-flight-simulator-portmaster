"""受注したときの会話を組み立てる。

決め打ちの台本を種類ぶん書くのではなく、部品を積む。
「導入 → やりかた → 今日の条件 → 機体の状態 → 返事」の順で、
当てはまるものだけを並べるので、荒天や損耗のときだけ話が増える。
"""
import lang
import mission
import world
from briefing import OP, PILOT

WIND_HARD = 16.0            # これ以上の横風なら注意を促す[kt]
DMG_WARN = 55.0             # これ以上溜まっていたら整備を勧める[%]
DMG_BAD = 80.0


def _T(key, *args):
    t = lang.T(key)
    return (t % args) if args else t


def _apt(name):
    """空港名は方角と紛らわしいので「空港」を付ける。"""
    if world.is_airport(name):
        return _T('%s AIRPORT', name)
    return name


def _intro(job, at):
    """導入。難度が上がるほど芝居がかる。

    遊覧や測量は出発地へ戻る仕事なので、行き先を言うと
    「CENTRAL空港よりCENTRAL空港まで」になってしまう。言い回しを分ける。
    """
    back = (job.where() == at)
    if job.tier >= 3:
        return (_T('BRIEF_INTRO_3H', _apt(at)) if back
                else _T('BRIEF_INTRO_3', _apt(at), _apt(job.where())))
    if job.tier == 2:
        return _T('BRIEF_INTRO_2H') if back else _T('BRIEF_INTRO_2',
                                                    _apt(job.where()))
    return (_T('BRIEF_INTRO_1H', _apt(at)) if back
            else _T('BRIEF_INTRO_1', _apt(at), _apt(job.where())))


def _how(job):
    """やりかた。ここが説明書の代わりになる。"""
    k = job.kind
    if k == mission.KIND_FERRY:
        return _T('BRIEF_HOW_FERRY')
    if k == mission.KIND_CARGO:
        return _T('BRIEF_HOW_CARGO', job.payload)
    if k == mission.KIND_PAX:
        return _T('BRIEF_HOW_PAX', job.payload)
    if k == mission.KIND_TOUR:
        return _T('BRIEF_HOW_TOUR', len(job.targets), _apt(job.origin))
    if k == mission.KIND_SURVEY:
        return _T('BRIEF_HOW_SURVEY', round(job.alt * 3.28084))
    return _T('BRIEF_HOW_SEARCH', _apt(job.where()))


def _weather(app):
    """今日の条件。荒れているときだけ出す。"""
    out = []
    _d, kt, _h, cross = app.wind_info()
    if abs(cross) >= WIND_HARD or kt >= 20.0:
        out.append(_T('BRIEF_WIND', int(kt), int(abs(cross))))
    if app.raining:
        out.append(_T('BRIEF_RAIN'))
    if app.tod_now()[0] in ('dusk', 'night'):
        out.append(_T('BRIEF_NIGHT'))
    if app.wind.shear_on:
        out.append(_T('BRIEF_SHEAR'))
    return out


def _damage(career):
    """機体の状態。気づかないまま出発するのを防ぐ。"""
    if not career.on or career.rented:
        return []
    worst = max(career.dmg, key=lambda k: career.dmg[k])
    v = career.dmg[worst]
    if v >= DMG_BAD:
        return [_T('BRIEF_DMG_BAD', lang.T(worst), int(v))]
    if v >= DMG_WARN:
        return [_T('BRIEF_DMG', lang.T(worst), int(v))]
    return []


def _reply(job):
    if job.tier >= 3:
        return _T('BRIEF_REPLY_3')
    if job.tier == 2:
        return _T('BRIEF_REPLY_2')
    return _T('BRIEF_REPLY_1')


def brief(job, app, at):
    """打ち合わせの本文 [(話者, 本文), ...]。返事はまだ入れない。

    受けるかどうかを尋ねる前にパイロットが「行ってきます」と言ってしまうと、
    整備のために断る余地が無くなる。返事は accepted() に分けてある。
    """
    lines = [(OP, _intro(job, at)), (OP, _how(job))]
    if job.limit:
        lines.append((OP, _T('BRIEF_LIMIT', int(round(job.limit / 60.0)),
                             int(round(job.est)))))
    lines += [(OP, s) for s in _weather(app)]
    lines += [(OP, s) for s in _damage(app.career)]
    lines.append((OP, _T('BRIEF_PAY', job.pay, job.xp)))
    return lines


def accepted(job):
    """受けたときの返事。"""
    return [(PILOT, _reply(job))]


def declined(career):
    """断ったときのひと言。整備が要るなら、そちらを勧める。"""
    if career.on and not career.rented and max(career.dmg.values()) >= DMG_WARN:
        return [(OP, _T('BRIEF_NO_DMG'))]
    return [(OP, _T('BRIEF_NO'))]
