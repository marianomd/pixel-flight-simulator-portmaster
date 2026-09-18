"""表示言語。メニューの文字だけを英語／日本語で切り替える。

飛行中のHUDや計器の文字は英語のまま（実機の計器がそうであるため）。
メニューは日本語ビットマップフォント（umplus_j10r.bdf）で描く。
"""
from pathlib import Path

import pyxel

NAMES = ('ENGLISH', '日本語')
EN, JA = 0, 1
FONT_FILE = 'umplus_j10r.bdf'

lang = EN
_FONT = None


def font():
    """メニュー用のフォント。読めなければ None（組み込みフォントに戻す）。"""
    global _FONT
    if _FONT is None:
        for d in (Path(__file__).resolve().parent,
                  Path(__file__).resolve().parent.parent):
            p = d / FONT_FILE
            try:
                if p.is_file():
                    _FONT = pyxel.Font(str(p))
                    break
            except Exception:
                continue
        if _FONT is None:
            _FONT = False
    return _FONT or None


def set_lang(i):
    global lang
    lang = i % len(NAMES)


def lang_name():
    return NAMES[lang]



# 受注時の会話。英語は EN_TEXT、日本語は JA_TEXT に置く。
# 訳が無ければ英語のまま返るので、英語側もここに書いておく
BRIEF_EN = {
    'OPERATOR': 'OPERATOR', 'PILOT': 'PILOT',
    'BRIEF_INTRO_1': '%s dispatch. A routine run over to %s when you are ready.',
    'BRIEF_INTRO_2': 'This one is urgent. They are already waiting at %s.',
    'BRIEF_INTRO_3': '%s here. Emergency. Nobody else can fly this today. '
                     'Get it to %s - they are counting on you.',
    'BRIEF_INTRO_1H': '%s dispatch. Something local for you, if you are free.',
    'BRIEF_INTRO_2H': 'This one is urgent. Can you get airborne right away?',
    'BRIEF_INTRO_3H': '%s here. Emergency. Nobody else can fly this today. '
                      'Please - they are counting on you.',
    'BRIEF_HOW_FERRY': 'Just reposition the aircraft. Fuel is on the client - we '
                       'top you off after you shut down.',
    'BRIEF_HOW_CARGO': 'You carry %d KG. The weight lengthens your take-off roll '
                       'and raises the stall speed.',
    'BRIEF_HOW_PAX': 'Passengers on board, %d KG. Sharp inputs cost you their '
                     'rating - keep it gentle.',
    'BRIEF_HOW_TOUR': 'Show them %d sights, then bring them home to %s.',
    'BRIEF_HOW_SURVEY': 'Fly the marked line at %d FT, either direction. The line '
                        'turns green as you cover it - we need at least half.',
    'BRIEF_HOW_SEARCH': 'Sweep the area for smoke, then get below 300 FT to sight '
                        'the survivors. Land at %s once you have them.',
    'BRIEF_LIMIT': 'You have %d minutes. It should take about %d.',
    'BRIEF_WIND': 'Wind is up today - %d KT, %d KT across the runway. Do not force it.',
    'BRIEF_RAIN': 'It is raining. Watch your visibility on final.',
    'BRIEF_NIGHT': 'You will be landing after dark. Do not forget the landing light.',
    'BRIEF_SHEAR': 'Shear has been reported near the ground. Keep some speed in hand.',
    'BRIEF_DMG': 'One more thing - your %s is at %d%%. I would get it looked at.',
    'BRIEF_DMG_BAD': 'Your %s is at %d%%. You really should repair before flying '
                     'this one. Your call.',
    'BRIEF_PAY': 'Pays %d CR and %d XP on arrival.',
    'ACCEPT': 'ACCEPT', 'DECLINE': 'NOT NOW',
    'BRIEF_NO': 'Understood. I will keep it on the board for you.',
    'BRIEF_NO_DMG': 'Understood. Get the aircraft seen to - the job will keep.',
    'BRIEF_REPLY_1': 'Copy that. On my way.',
    'BRIEF_REPLY_2': 'Understood - I will keep the speed up.',
    'BRIEF_REPLY_3': '...Understood. I will get it there.',
}


def T(s):
    """表示文字を訳す。訳が無ければそのまま返す。"""
    if not s:
        return s
    if lang == EN:
        return BRIEF_EN.get(s, s)
    return JA_TEXT.get(s, BRIEF_EN.get(s, s))


# 訳。左が英語（コード内の表記）、右が日本語
JA_TEXT = {
    # ページ名
    'OPTIONS': 'オプション', 'FLIGHT': 'フライト', 'WEATHER': '天候',
    'GRAPHICS': '描画', 'AUDIO': '音', 'CONTROLS': '操作',
    'KEY MAPPING': 'キー割り当て', 'RESET POSITION': '位置のやり直し',
    'HELP': 'ヘルプ', 'LANDING LOG': '飛行記録', 'HANGAR': 'ハンガー', 'SHOP': 'ショップ',
    'AIRCRAFT': '機体', 'JOB BOARD': '仕事一覧', 'RATINGS': '資格',
    # 共通
    'ON': 'オン', 'OFF': 'オフ', 'NORMAL': '等倍', 'START': '開始',
    'RUNNING': '実行中', 'ACCEPT': '受注', 'OWNED': '所有', 'FLYING': '搭乗中',
    'SELL': '売る', 'HELD': '取得済', 'FITTED': '装備済', 'MAX': '最大',
    'QUIT': '終了', 'PAUSE': '一時停止', 'MODE': 'モード',
    'OPERATOR': 'オペレーター', 'PILOT': 'パイロット',
    'BRIEF_INTRO_1': 'こちら%sです。手が空いていたら%sまで一本お願いできますか。',
    'BRIEF_INTRO_2': '至急の便です。%sで先方がもう待っています。',
    'BRIEF_INTRO_3': '%sより緊急です。この条件で飛べるのはあなたしかいません。'
                     '%sまで、どうか依頼主の願いを叶えてあげてください。',
    'BRIEF_INTRO_1H': 'こちら%sです。近場で一本お願いできますか。',
    'BRIEF_INTRO_2H': '至急の便です。すぐに上がれますか。',
    'BRIEF_INTRO_3H': '%sより緊急です。この条件で飛べるのはあなたしかいません。'
                      'どうか依頼主の願いを叶えてあげてください。',
    'BRIEF_HOW_FERRY': '機体の回送だけの仕事です。燃料は依頼主持ちなので、'
                       '降りたらこちらで満タンにしておきます。',
    'BRIEF_HOW_CARGO': '積荷は%dKGです。重くなるぶん離陸滑走が伸び、'
                       '失速速度も上がります。',
    'BRIEF_HOW_PAX': 'お客様が%dKG分お乗りになります。急な操作は乗り心地に'
                     '響きますので、丁寧にお願いします。',
    'BRIEF_HOW_TOUR': '見どころを%d箇所ご案内して、%sまでお連れしてください。',
    'BRIEF_HOW_SURVEY': '測線を高度%dFTで飛んでください。向きはどちらからでも。'
                        '撮れたところから線が緑に変わります。半分以上は必要です。',
    'BRIEF_HOW_SEARCH': '範囲を回って発煙を探し、救助者を目視するために300FT以下で'
                        '対象に近づいてください。確認できたら%sへ降りてください。',
    'BRIEF_LIMIT': '制限時間は%d分。見込みは%d分ほどです。',
    'BRIEF_WIND': '今日は風が強いです。%dKT、滑走路に対して横風%dKT。'
                  '無理はなさらないでください。',
    'BRIEF_RAIN': '雨が降っています。進入中の視界にお気をつけて。',
    'BRIEF_NIGHT': '日が落ちてからの着陸になります。着陸灯をお忘れなく。',
    'BRIEF_SHEAR': '地表付近でシアーの報告が出ています。速度に余裕を持って。',
    'BRIEF_DMG': 'それと一点。%sの損耗が%d%%です。整備をおすすめします。',
    'BRIEF_DMG_BAD': '%sの損耗が%d%%あります。正直、飛ぶ前に直された方が。'
                     'ご判断はお任せします。',
    'BRIEF_PAY': '到着で%dCRと%dXPです。',
    'ACCEPT': '受ける', 'DECLINE': 'やめておく',
    'BRIEF_NO': '承知しました。一覧に残しておきます。',
    'BRIEF_NO_DMG': '承知しました。機体を診てもらってください。仕事は残しておきます。',
    'BRIEF_REPLY_1': '了解、行ってきます。',
    'BRIEF_REPLY_2': '急ぎですね。速度は詰めていきます。',
    'BRIEF_REPLY_3': '……わかりました。必ず届けます。',
    'GEAR': '脚', 'WING': '主翼', 'ENGINE': 'エンジン', 'AIRFRAME': '機体',
    'HEAVY WEATHER': '荒天運航', 'HOME CONTRACT': '拠点契約',
    'ROUGHER DAYS, BETTER PAY': '荒れた日が来るが報酬も上がる',
    'MORE WORK FROM YOUR BASE': '拠点発の仕事が増える',
    'HOME BASE': '拠点', 'NOT SET': '未設定',
    'RATING MAXED': '階級は最高位', 'ABOUT': 'このゲームについて', 'VERSION': '版', 'ASSETS': '素材', 'SEE THIRD-PARTY.MD': '詳細は THIRD-PARTY.md',
    'FONT': 'フォント', 'ATC VOICE': '管制音声', 'SPEECH SYNTHESIS': '音声合成',
    'RECORD': '記録', 'LANDINGS': '着陸回数', 'BEST SCORE': '最高得点',
    'PILOT SKILLS': '操縦者スキル', 'PILOT': 'パイロット',
    'NEGOTIATION': '交渉', 'LOGBOOK': '記録', 'CLIENT TRUST': '顧客信頼',
    'PROCUREMENT': '買い付け', 'MAINTENANCE': '整備手配',
    'JOBS PAY MORE': '仕事の報酬が上がる', 'JOBS GIVE MORE XP': '仕事の経験値が上がる',
    'HARDER JOBS APPEAR MORE OFTEN': '高難度の仕事が出やすくなる',
    'CHEAPER IN THE SHOP': 'ショップが安くなる',
    'CHEAPER REPAIRS AND FUEL': '修理と燃料が安くなる',
    'AIRCRAFT UPGRADES': '機体強化', 'UPGRADE PARTS': '部位の強化',
    'EQUIPMENT': '装備', 'REINFORCED GEAR': '強化脚', 'WING SPAR KIT': '主翼桁補強',
    'ENGINE OVERHAUL': 'エンジン整備', 'AIRFRAME BRACING': '機体補強',
    'TOUGHER, BETTER BRAKES': '頑丈になりブレーキが効く',
    'TOUGHER, LOWER STALL SPEED': '頑丈になり失速速度が下がる',
    'LESS WEAR, BETTER ECONOMY': '摩耗が減り燃費が良くなる',
    'TOUGHER, LESS DRAG': '頑丈になり抗力が減る',
    'MAX': '最大',
    'ARCADE': 'アーケード', 'CAREER': 'キャリア', 'CREDITS': '所持金',
    'LANGUAGE': '言語',
    # FLIGHT
    'RING COURSE': 'リングコース', 'JOBS': '仕事', 'CHARTER': 'チャーター',
    'TIME SPEED': '時間加速', 'FUEL': '燃料', 'ENDURANCE': '航続時間',
    'LANDING LIGHT': '着陸灯', 'APPROACH GUIDE': '着陸ガイド',
    'RESULT SCREEN': 'リザルト画面', 'AUTOPILOT CRUISE': 'AP巡航',
    'TO DESTINATION': '目的地へ', 'FREE TOUR': '遊覧',
    # リザルト画面
    'FLIGHT RESULT': '飛行結果', 'LANDING': '着陸', 'SCORE': '得点',
    'SINK RATE': '沈下率', 'TOUCHDOWN': '接地点', 'CENTRELINE': '中心線',
    'LANDING PAY': '着陸報酬', 'OFF RUNWAY': '滑走路外', 'FUEL INCLUDED': '燃料込み',
    'SAVED %d CR': '%d CR お得', 'FLYING': '操縦', 'HAND FLOWN': '手動',
    'AUTOLAND': '自動着陸', 'AP TO %d FT': 'AP解除 %d FT',
    'HAND FLOWN BONUS': '手動着陸ボーナス',
    'H=HAND  /=PARTIAL  A=AUTO': 'H=手動  /=一部AP  A=自動着陸', 'EXPERIENCE': '経験値', 'LEVEL UP!': 'レベルアップ!',
    'NEXT %d XP': '次まで %d XP', 'DAMAGE': '損傷', 'TOTAL %d%%': '合計 %d%%',
    'PRESS %s': '%s でとじる',
    'LATE - HALF PAY': '遅延 - 報酬は半額', 'MISSED THE RUNWAY': '目的地の滑走路ではない',
    'NOT FINISHED YET': '仕事がまだ終わっていない', 'QUALITY %d%%': '出来ばえ %d%%',
    'BIRDS': '鳥', 'SAVE FLIGHT': '飛行を保存', 'NOW': '今すぐ',
    'RUNWAY': '滑走路', 'ON FINAL': '最終進入', 'CRUISE': '巡航',
    # WEATHER
    'TIME OF DAY': '時刻', 'DAY LENGTH': '一巡の長さ', 'CLOUDS': '雲',
    'RAIN': '雨', 'WIPER': 'ワイパー', 'LIGHTNING': '雷',
    'VISIBILITY': '視程', 'WIND': '風', 'WIND DIR': '風向',
    'WIND SHEAR': 'ウィンドシア', 'SET BY THE DAY': 'その日の空模様',
    # GRAPHICS
    'DETAIL': '描き込み', 'CLOUD SHADOWS': '雲の影', 'CLOUD LAYER': '雲層',
    'SHOW FPS': 'FPS表示', 'FPS LIMIT': 'FPS上限', 'ASPECT': '画面比率',
    'LOW': '低', 'MEDIUM': '中', 'HIGH': '高',
    # AUDIO
    'BGM MODE': 'BGMの順番', 'BGM VOLUME': 'BGM音量', 'SE VOLUME': '効果音',
    'ATC VOICE': '管制音声', 'BGM TRACK': '曲', 'TRACKS FOUND': '曲数',
    'SEQUENCE': '順番', 'SHUFFLE': 'ランダム',
    # CONTROLS
    'BUTTON LAYOUT': 'ボタン配置', 'RESET TO DEFAULT': '初期値に戻す',
    # HANGAR
    'LEVEL': 'レベル', 'RANK': '階級', 'FLIGHTS': '飛行回数',
    'RENT CLUB AIRCRAFT': 'クラブ機を借りる', 'GEAR': '脚', 'WING': '主翼',
    'ENGINE': 'エンジン', 'AIRFRAME': '機体', 'REFUEL TO FULL': '満タンに給油',
    'RESET CAREER': 'キャリアをやり直す', 'START OVER': 'やり直す',
    'PRESS AGAIN': 'もう一度押す', 'STUDENT': '訓練生', 'PRIVATE': '自家用',
    'COMMERCIAL': '事業用', 'AIRLINE': '定期便',
    # 仕事
    'FERRY FLIGHT': '回送', 'CARGO': '貨物', 'PASSENGERS': '旅客',
    'SIGHTSEEING': '遊覧', 'AERIAL SURVEY': '空中測量',
    'SEARCH AND RESCUE': '捜索救難', 'ON A JOB': '受注中', 'PAY': '報酬',
    'ABANDON JOB': '仕事を降りる', 'TIME LEFT': '残り時間', 'DONE': '達成',
    'TOO HEAVY': '積載超過', 'RUSH': '至急', 'CRITICAL': '緊急', 'STANDARD': '通常',
    # 資格・装備
    'NIGHT RATING': '夜間飛行資格', 'INSTRUMENT RATING': '計器飛行資格',
    'MULTI-ENGINE': '多発機資格', 'AUTOPILOT': '自動操縦',
    'ILS RECEIVER': 'ILS受信機',
    'FLY AT DUSK AND NIGHT': '夕方と夜に飛べる', 'FLY IN RAIN AND LOW VIS': '雨と低視程で飛べる',
    'FLY THE TWIN': '双発機に乗れる', 'CRUISE HOLD': '巡航の姿勢維持',
    'AUTOLAND ON THE GLIDESLOPE': '進入経路に乗って自動着陸',
    # 値
    'DAY': '昼', 'GOLDEN': '夕焼け', 'DUSK': '薄暮', 'NIGHT': '夜',
    'AUTO': '自動', 'CALM': '無風', 'MODERATE': '中', 'STRONG': '強',
    'CLEAR': '良好', 'HAZE': 'かすみ', 'FOG': '濃霧', 'LIGHT': '弱',
    'CAREER: NO': 'キャリアでは不可', 'AVAILABLE': '件',
    'NEXT': '次', 'MIN': '分', 'YOUR AIRCRAFT': '自機の状態',
    'PATCH ALL (20% LEFT)': '応急修理（20%残る）',
    'TRAINER': '練習機', 'BUSH PLANE': 'ブッシュ機', 'TOURER': '長距離機',
    'SPORT': '高速機', 'TWIN': '双発機', 'CLUB': 'クラブ機',
    'BOARD AT': '掲示板',
    '%d SIGHTS, TO %s': '%d箇所を巡り %sへ', 'LINE AT %d FT': '測線 %d FT',
    'SEARCH, LAND %s': '捜索して %sへ', 'TO %s  %d KG': '%sへ  %d KG',
    'TO %s': '%sへ', '%s AIRPORT': '%s空港',
    'EST': '目安', 'XP': 'XP', 'LIMIT': '制限', 'TARGETS': '目標', 'CANCEL': '取り消し',
    # 見出し
    'STATUS': '状態', 'MAINTENANCE': '整備', 'UPGRADES': '強化', 'EARN RATINGS': '資格を取る', 'CHANGE AIRCRAFT': '機体を変える',
    'RECENT LANDINGS': '直近の着陸', 'CAREER TOTAL': '通算',
    # 記録
    'SIGHTS': '見どころ', 'AIR TIME': '総飛行時間', 'SEEN': '訪問済',
    'COURSE BEST': 'コース最速', 'NO LANDINGS YET': 'まだ着陸記録がありません',
}
