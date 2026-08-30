"""Rule-based partial buy/sell signal engine for CORE holdings."""

from math import ceil


def _sma(values, period):
    result = [None] * len(values)
    if period <= 0:
        return result
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            result[index] = running / period
    return result


def _ema(values, period):
    result = [None] * len(values)
    if len(values) < period:
        return result
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    multiplier = 2 / (period + 1)
    previous = seed
    for index in range(period, len(values)):
        previous = ((values[index] - previous) * multiplier) + previous
        result[index] = previous
    return result


def _midpoint(highs, lows, period):
    result = [None] * len(highs)
    for index in range(period - 1, len(highs)):
        window_high = max(highs[index - period + 1:index + 1])
        window_low = min(lows[index - period + 1:index + 1])
        result[index] = (window_high + window_low) / 2
    return result


def _crossed_above(left, right, index=-1):
    previous = index - 1 if index >= 0 else len(left) + index - 1
    current = index if index >= 0 else len(left) + index
    if previous < 0 or current < 0:
        return False
    values = (left[previous], right[previous], left[current], right[current])
    return all(value is not None for value in values) and left[previous] <= right[previous] and left[current] > right[current]


def _crossed_below(left, right, index=-1):
    previous = index - 1 if index >= 0 else len(left) + index - 1
    current = index if index >= 0 else len(left) + index
    if previous < 0 or current < 0:
        return False
    values = (left[previous], right[previous], left[current], right[current])
    return all(value is not None for value in values) and left[previous] >= right[previous] and left[current] < right[current]


def _percentile(values, percentile):
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _linear_predictions(values, future_count):
    count = len(values)
    if count < 2:
        return []
    x_mean = (count - 1) / 2
    y_mean = sum(values) / count
    denominator = sum((index - x_mean) ** 2 for index in range(count))
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    intercept = y_mean - slope * x_mean
    return slope, [intercept + slope * index for index in range(count, count + future_count)]


def _dmi(highs, lows, closes, period=14):
    plus_dm = [0.0] * len(closes)
    minus_dm = [0.0] * len(closes)
    true_range = [0.0] * len(closes)
    for index in range(1, len(closes)):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0
        true_range[index] = max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )

    tr_sum = _sma(true_range, period)
    plus_sum = _sma(plus_dm, period)
    minus_sum = _sma(minus_dm, period)
    plus_di = [None] * len(closes)
    minus_di = [None] * len(closes)
    for index in range(len(closes)):
        if tr_sum[index]:
            plus_di[index] = 100 * plus_sum[index] / tr_sum[index]
            minus_di[index] = 100 * minus_sum[index] / tr_sum[index]
    return plus_di, minus_di


def _obv(closes, volumes):
    result = [0.0] * len(closes)
    for index in range(1, len(closes)):
        if closes[index] > closes[index - 1]:
            result[index] = result[index - 1] + volumes[index]
        elif closes[index] < closes[index - 1]:
            result[index] = result[index - 1] - volumes[index]
        else:
            result[index] = result[index - 1]
    return result


def _signal(group, name, weight):
    return {'group': group, 'name': name, 'weight': weight}


def _recommended_quantity(total_quantity, percentage, action):
    if total_quantity <= 0 or percentage <= 0 or action == 'HOLD':
        return 0
    quantity = max(1, int(ceil(total_quantity * percentage / 100)))
    return min(total_quantity, quantity) if action == 'PARTIAL_SELL' else quantity


def analyze_trade_signal(history, total_quantity=0):
    """Evaluate the latest completed candle against the documented A-F rules."""
    clean_history = [
        item for item in history
        if all(item.get(key) is not None for key in ('open', 'high', 'low', 'close', 'volume'))
    ]
    if len(clean_history) < 120:
        raise ValueError('신호 계산에는 최소 120거래일의 일봉 데이터가 필요합니다.')

    opens = [float(item['open']) for item in clean_history]
    highs = [float(item['high']) for item in clean_history]
    lows = [float(item['low']) for item in clean_history]
    closes = [float(item['close']) for item in clean_history]
    volumes = [float(item['volume']) for item in clean_history]

    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [None if ema12[i] is None or ema26[i] is None else ema12[i] - ema26[i] for i in range(len(closes))]
    macd_values = [value for value in macd if value is not None]
    signal_compact = _ema(macd_values, 9)
    macd_signal = [None] * len(closes)
    compact_index = 0
    for index, value in enumerate(macd):
        if value is not None:
            macd_signal[index] = signal_compact[compact_index]
            compact_index += 1

    tenkan = _midpoint(highs, lows, 9)
    kijun = _midpoint(highs, lows, 26)
    span_b_base = _midpoint(highs, lows, 52)
    span_a = [None] * len(closes)
    span_b = [None] * len(closes)
    for index in range(len(closes) - 26):
        if tenkan[index] is not None and kijun[index] is not None:
            span_a[index + 26] = (tenkan[index] + kijun[index]) / 2
        if span_b_base[index] is not None:
            span_b[index + 26] = span_b_base[index]

    plus_di, minus_di = _dmi(highs, lows, closes)
    obv = _obv(closes, volumes)
    obv_ma20 = _sma(obv, 20)
    distance = [None if ma5[i] in (None, 0) else closes[i] / ma5[i] * 100 for i in range(len(closes))]
    historical_distance = distance[max(0, len(distance) - 501):-1]
    distance_p90 = _percentile(historical_distance, 0.90)
    distance_p10 = _percentile(historical_distance, 0.10)

    current_cloud = span_b[-1]
    track = 'TRACK_1' if ma60[-1] is not None and current_cloud is not None and closes[-1] > ma60[-1] and closes[-1] > current_cloud else 'TRACK_2'
    sell_signals = []
    buy_signals = []

    # A/A': two independent early-warning signals.
    if _crossed_below(macd, macd_signal):
        sell_signals.append(_signal('A', 'MACD 시그널선 하향 돌파', 5))
    if _crossed_above(macd, macd_signal):
        buy_signals.append(_signal("A'", 'MACD 시그널선 상향 돌파', 5))
    if _crossed_below(closes, tenkan):
        sell_signals.append(_signal('A', '종가 일목 전환선 하향 이탈', 5))
    if _crossed_above(closes, tenkan):
        buy_signals.append(_signal("A'", '종가 일목 전환선 상향 돌파', 5))

    # B/B': correlated short-term signals are counted once.
    sell_b = []
    buy_b = []
    if _crossed_below(closes, ma5): sell_b.append('5일선 하향 이탈')
    if _crossed_above(closes, ma5): buy_b.append('5일선 상향 돌파')
    if ma5[-3] is not None and ma5[-2] >= ma5[-3] and ma5[-1] < ma5[-2]: sell_b.append('5일선 기울기 음전환')
    if ma5[-3] is not None and ma5[-2] <= ma5[-3] and ma5[-1] > ma5[-2]: buy_b.append('5일선 기울기 양전환')
    if _crossed_below(ma5, ma10): sell_b.append('5/10 데드크로스')
    if _crossed_above(ma5, ma10): buy_b.append('5/10 골든크로스')
    if _crossed_below(tenkan, kijun): sell_b.append('일목 전환선/기준선 데드크로스')
    if _crossed_above(tenkan, kijun): buy_b.append('일목 전환선/기준선 골든크로스')
    if sell_b: sell_signals.append(_signal('B', ' / '.join(sell_b), 10))
    if buy_b: buy_signals.append(_signal("B'", ' / '.join(buy_b), 10))

    # C/C': correlated medium-term signals are counted once.
    sell_c = []
    buy_c = []
    if _crossed_below(ma5, ma20): sell_c.append('5/20 데드크로스')
    if _crossed_above(ma5, ma20): buy_c.append('5/20 골든크로스')
    if _crossed_below(ma20, ma60): sell_c.append('20/60 데드크로스')
    if _crossed_above(ma20, ma60): buy_c.append('20/60 골든크로스')
    if ma20[-3] is not None and ma20[-2] >= ma20[-3] and ma20[-1] < ma20[-2]: sell_c.append('20일선 기울기 음전환')
    if ma20[-3] is not None and ma20[-2] <= ma20[-3] and ma20[-1] > ma20[-2]: buy_c.append('20일선 기울기 양전환')
    if all(value is not None for value in kijun[-4:]):
        if kijun[-1] < kijun[-2] < kijun[-3] < kijun[-4]: sell_c.append('일목 기준선 3일 연속 하락')
        if kijun[-1] > kijun[-2] > kijun[-3] > kijun[-4]: buy_c.append('일목 기준선 3일 연속 상승')
    if sell_c: sell_signals.append(_signal('C', ' / '.join(sell_c), 15))
    if buy_c: buy_signals.append(_signal("C'", ' / '.join(buy_c), 15))

    average_volume = sum(volumes[-6:-1]) / 5 if sum(volumes[-6:-1]) else 0
    volume_ratio = volumes[-1] / average_volume if average_volume else 0
    day_return = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0
    negative_filter = volume_ratio >= 1.30 and closes[-1] < opens[-1] and day_return <= -1.5
    positive_threshold = 2.0 if track == 'TRACK_2' else 1.30
    positive_filter = volume_ratio >= positive_threshold and closes[-1] > opens[-1] and day_return >= 1.5

    # D/D': 60-day regression trendline and prior 60-day support.
    if len(closes) >= 63:
        low_regression = _linear_predictions(lows[-62:-2], 2)
        high_regression = _linear_predictions(highs[-62:-2], 2)
        support = min(lows[-62:-2])
        if low_regression:
            slope, predicted = low_regression
            if slope > 0 and closes[-2] >= predicted[0] and closes[-1] < predicted[1] and negative_filter:
                sell_signals.append(_signal('D', '상승 추세선 하향 이탈(거래량 확인)', 15))
        if closes[-2] >= support and closes[-1] < support and negative_filter:
            sell_signals.append(_signal('D', '최근 60일 지지선 붕괴(거래량 확인)', 15))

        if high_regression:
            slope, predicted = high_regression
            trend_breakout = slope < 0 and closes[-2] <= predicted[0] and closes[-1] > predicted[1]
            if track == 'TRACK_2':
                confirmed = _linear_predictions(highs[-63:-3], 3)
                if confirmed:
                    confirmed_slope, levels = confirmed
                    trend_breakout = confirmed_slope < 0 and all(closes[-3 + i] > levels[i] for i in range(3))
            if trend_breakout and positive_filter:
                buy_signals.append(_signal("D'", '하락 추세선 상향 돌파(거래량 확인)', 15))
        support_bounce = lows[-1] <= support * 1.01 and closes[-1] > support and positive_filter
        if track == 'TRACK_2':
            support_bounce = all(closes[index] > support for index in (-3, -2, -1)) and lows[-3] <= support * 1.01 and positive_filter
        if support_bounce:
            buy_signals.append(_signal("D'", '최근 60일 지지선 반등(거래량 확인)', 15))

    # E/E': independent Ichimoku levels.
    for line, sell_name, buy_name in (
        (kijun, '기준선 아래 진입', '기준선 위 복귀'),
        (span_a, '선행스팬1 아래 진입', '선행스팬1 위 복귀'),
        (span_b, '선행스팬2 아래 이탈', '선행스팬2 위 돌파'),
    ):
        if _crossed_below(closes, line): sell_signals.append(_signal('E', sell_name, 5))
        if _crossed_above(closes, line): buy_signals.append(_signal("E'", buy_name, 5))
    if len(closes) >= 28:
        if closes[-2] >= closes[-28] and closes[-1] < closes[-27]: sell_signals.append(_signal('E', '후행스팬 역전', 5))
        if closes[-2] <= closes[-28] and closes[-1] > closes[-27]: buy_signals.append(_signal("E'", '후행스팬 양전환', 5))

    # F/F': lower-confidence supporting indicators.
    if distance_p90 is not None and distance[-2] <= distance_p90 < distance[-1]:
        sell_signals.append(_signal('F', '이격도 최근 2년 상위 10% 진입', 5))
    if distance_p10 is not None and distance[-2] < distance_p10 <= distance[-1]:
        buy_signals.append(_signal("F'", '이격도 최근 2년 하위 10% 탈출', 5))
    if _crossed_above(minus_di, plus_di): sell_signals.append(_signal('F', 'DI-가 DI+ 상향 돌파', 5))
    if _crossed_above(plus_di, minus_di): buy_signals.append(_signal("F'", 'DI+가 DI- 상향 돌파', 5))
    if all(obv_ma20[index] is not None and obv[index] < obv_ma20[index] for index in (-3, -2, -1)) and obv[-4] >= obv_ma20[-4]:
        sell_signals.append(_signal('F', 'OBV 20일선 하향 이탈 3일 지속', 5))
    if _crossed_above(obv, obv_ma20): buy_signals.append(_signal("F'", 'OBV 20일선 상승 전환', 5))

    sell_percentage = min(100, sum(item['weight'] for item in sell_signals))
    raw_buy_percentage = min(100, sum(item['weight'] for item in buy_signals))
    buy_percentage = raw_buy_percentage * (0.5 if track == 'TRACK_2' else 1.0)

    if sell_percentage > buy_percentage:
        action = 'PARTIAL_SELL'
        percentage = sell_percentage
        selected_signals = sell_signals
    elif buy_percentage > sell_percentage:
        action = 'PARTIAL_BUY'
        percentage = buy_percentage
        selected_signals = buy_signals
    else:
        action = 'HOLD'
        percentage = 0
        selected_signals = []

    quantity = max(0, int(total_quantity or 0))
    return {
        'as_of': str(clean_history[-1].get('date', '')),
        'close': closes[-1],
        'track': track,
        'action': action,
        'percentage': round(percentage, 1),
        'recommended_quantity': _recommended_quantity(quantity, percentage, action),
        'total_quantity': quantity,
        'sell_percentage': round(sell_percentage, 1),
        'buy_percentage': round(buy_percentage, 1),
        'sell_signals': sell_signals,
        'buy_signals': buy_signals,
        'signals': selected_signals,
        'volume_ratio': round(volume_ratio, 2),
        'distance_thresholds': {
            'p10': round(distance_p10, 2) if distance_p10 is not None else None,
            'p90': round(distance_p90, 2) if distance_p90 is not None else None,
        },
    }
