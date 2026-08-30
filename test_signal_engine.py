import unittest
from unittest.mock import patch

from app import app
from signal_engine import analyze_trade_signal


def make_history(last_close=None, last_open=None, last_volume=None):
    history = []
    for index in range(180):
        price = 100 + (index * 0.05)
        history.append({
            'date': f'2026{(index // 28) % 12 + 1:02d}{index % 28 + 1:02d}',
            'open': price - 0.2,
            'high': price + 1,
            'low': price - 1,
            'close': price,
            'volume': 1000,
        })
    if last_close is not None:
        history[-1].update({
            'open': last_open,
            'high': max(last_open, last_close) + 1,
            'low': min(last_open, last_close) - 1,
            'close': last_close,
            'volume': last_volume,
        })
    return history


class SignalEngineTest(unittest.TestCase):
    def test_bearish_break_calculates_partial_sell_quantity(self):
        signal = analyze_trade_signal(make_history(80, 108, 3000), 100)
        self.assertEqual(signal['action'], 'PARTIAL_SELL')
        self.assertGreater(signal['percentage'], 0)
        self.assertEqual(signal['recommended_quantity'], round(signal['percentage']))
        self.assertLessEqual(signal['recommended_quantity'], 100)

    def test_bullish_break_calculates_partial_buy_quantity(self):
        history = make_history()
        for index in range(120, 179):
            price = 115 - ((index - 120) * 0.25)
            history[index].update({
                'open': price + 0.1,
                'high': price + 1,
                'low': price - 1,
                'close': price,
            })
        history[-1].update({'open': 99, 'high': 122, 'low': 98, 'close': 121, 'volume': 4000})
        signal = analyze_trade_signal(history, 80)
        self.assertEqual(signal['action'], 'PARTIAL_BUY')
        self.assertGreater(signal['recommended_quantity'], 0)

    def test_requires_enough_history(self):
        with self.assertRaises(ValueError):
            analyze_trade_signal(make_history()[:60], 10)

    def test_portfolio_api_returns_quantity_without_sending_telegram(self):
        client = app.test_client()
        with patch('app.get_signal_history', return_value=make_history(80, 108, 3000)):
            response = client.post('/api/portfolio-signals', json={
                'holdings': [{'code': '005930', 'name': '삼성전자', 'quantity': 100}],
                'notify': False,
            })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['results'][0]['signal']['action'], 'PARTIAL_SELL')
        self.assertGreater(payload['results'][0]['signal']['recommended_quantity'], 0)
        self.assertFalse(payload['telegram']['sent'])


if __name__ == '__main__':
    unittest.main()
