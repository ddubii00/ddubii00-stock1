from flask import Flask, jsonify, request, render_template
import json
import requests
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

app = Flask(__name__)

# Common Korean stock nicknames
NICKNAMES = {
    '삼전': '삼성전자',
    '삼전우': '삼성전자우',
    '하닉': 'SK하이닉스',
    '슼하': 'SK하이닉스',
    '현차': '현대자동차',
    '현대차': '현대자동차',
    '기아차': '기아',
    '엘전': 'LG전자',
    '엘디': 'LG디스플레이',
    '엘화': 'LG화학',
    '엔솔': 'LG에너지솔루션',
    '삼바': '삼성바이오로직스',
    '삼에스': '삼성SDI',
    '삼디': '삼성SDI',
    '셀트': '셀트리온',
    '네바': 'NAVER',
    '카카': '카카오'
}

def load_stocks_db():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, 'stocks.json')
        with open(db_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading stocks.json: {e}")
        return []

stocks_db = load_stocks_db()

# --- US STOCKS SUPPORT CONSTANTS & HELPER FUNCTIONS ---
SECTOR_ETF_MAP = {
    'Technology': 'XLK',
    'Electronic Technology': 'XLK',
    'Financial Services': 'XLF',
    'Finance': 'XLF',
    'Healthcare': 'XLV',
    'Health Technology': 'XLV',
    'Consumer Cyclical': 'XLY',
    'Consumer Durables': 'XLY',
    'Industrials': 'XLI',
    'Industrial Services': 'XLI',
    'Consumer Staples': 'XLP',
    'Consumer Defensive': 'XLP',
    'Energy': 'XLE',
    'Utilities': 'XLU',
    'Real Estate': 'XLRE',
    'Basic Materials': 'XLB',
    'Communication Services': 'XLC'
}

US_SECTOR_BENCHMARK_NAMES = {
    'XLK': 'Technology Select Sector SPDR ETF',
    'XLF': 'Financial Select Sector SPDR ETF',
    'XLV': 'Health Care Select Sector SPDR ETF',
    'XLY': 'Consumer Discretionary Select Sector SPDR ETF',
    'XLI': 'Industrial Select Sector SPDR ETF',
    'XLP': 'Consumer Staples Select Sector SPDR ETF',
    'XLE': 'Energy Select Sector SPDR ETF',
    'XLU': 'Utilities Select Sector SPDR ETF',
    'XLRE': 'Real Estate Select Sector SPDR ETF',
    'XLB': 'Materials Select Sector SPDR ETF',
    'XLC': 'Communication Services Select Sector SPDR ETF',
    '^GSPC': 'S&P 500'
}

KOREA_SECTOR_BENCHMARK_RULES = [
    (('음식료', '식품', '담배'), '1005', 'KOSPI-05.KS', 'KRX 음식료품 업종지수'),
    (('섬유', '의복'), '1006', 'KOSPI-06.KS', 'KRX 섬유의복 업종지수'),
    (('종이', '목재'), '1007', 'KOSPI-07.KS', 'KRX 종이목재 업종지수'),
    (('화학', '소재', '배터리', '2차전지'), '1008', '267490.KS', 'KRX 화학 업종지수'),          # KODEX 2차전지산업
    (('의약', '제약', '바이오', '건강관리'), '1009', '244580.KS', 'KRX 의약품 업종지수'),        # KODEX 바이오
    (('비금속',), '1010', 'KOSPI-10.KS', 'KRX 비금속광물 업종지수'),
    (('철강', '금속'), '1011', 'KOSPI-11.KS', 'KRX 철강금속 업종지수'),
    (('기계',), '1012', 'KOSPI-12.KS', 'KRX 기계 업종지수'),
    (('전기전자', '전자', '반도체', '디스플레이'), '1013', '091160.KS', 'KRX 전기전자 업종지수'), # KODEX 반도체
    (('의료정밀', '정밀'), '1014', 'KOSPI-14.KS', 'KRX 의료정밀 업종지수'),
    (('운수장비', '자동차', '부품', '조선'), '1015', '091180.KS', 'KRX 운수장비 업종지수'),      # KODEX 자동차
    (('유통',), '1016', 'KOSPI-16.KS', 'KRX 유통업 업종지수'),
    (('전기가스', '가스'), '1017', 'KOSPI-17.KS', 'KRX 전기가스업 업종지수'),
    (('건설',), '1018', 'KOSPI-18.KS', 'KRX 건설업 업종지수'),
    (('운수창고', '항공', '해운', '물류'), '1019', 'KOSPI-19.KS', 'KRX 운수창고업 업종지수'),
    (('통신',), '1020', 'KOSPI-20.KS', 'KRX 통신업 업종지수'),
    (('금융', '은행', '증권', '보험'), '1021', '091170.KS', 'KRX 금융업 업종지수'),             # KODEX 은행
    (('서비스', '인터넷', '게임', '미디어', '소프트웨어'), '1026', 'KOSPI-26.KS', 'KRX 서비스업 업종지수')
]

US_PEERS_MAP = {}

US_TICKER_NAMES = {
    'AAPL': '애플 (Apple)',
    'MSFT': '마이크로소프트 (Microsoft)',
    'NVDA': '엔비디아 (NVIDIA)',
    'AVGO': '브로드컴 (Broadcom)',
    'ORCL': '오라클 (Oracle)',
    'CRM': '세일즈포스 (Salesforce)',
    'JPM': 'JP모건 (JPMorgan)',
    'BAC': '뱅크오브아메리카 (BAC)',
    'MS': '모건스탠리 (Morgan Stanley)',
    'GS': '골드만삭스 (Goldman Sachs)',
    'WFC': '웰스파고 (Wells Fargo)',
    'V': '비자 (Visa)',
    'LLY': '일라이릴리 (Eli Lilly)',
    'UNH': '유나이티드헬스 (UnitedHealth)',
    'JNJ': '존슨앤존슨 (Johnson & Johnson)',
    'ABBV': '애브비 (AbbVie)',
    'MRK': '머크 (Merck)',
    'PFE': '화이자 (Pfizer)',
    'AMZN': '아마존 (Amazon)',
    'TSLA': '테슬라 (Tesla)',
    'HD': '홈디포 (Home Depot)',
    'MCD': '맥도날드 (McDonalds)',
    'NKE': '나이키 (Nike)',
    'SBUX': '스타벅스 (Starbucks)',
    'GE': '제네럴일렉트릭 (GE)',
    'CAT': '캐터필러 (Caterpillar)',
    'UNP': '유니온퍼시픽 (Union Pacific)',
    'HON': '허니웰 (Honeywell)',
    'RTX': '레이시온 (RTX)',
    'LMT': '록히드마틴 (Lockheed Martin)',
    'PG': '프록터앤갬블 (P&G)',
    'KO': '코카콜라 (Coca-Cola)',
    'PEP': '펩시코 (PepsiCo)',
    'COST': '코스트코 (Costco)',
    'WMT': '월마트 (Walmart)',
    'TGT': '타겟 (Target)',
    'XOM': '엑슨모빌 (ExxonMobil)',
    'CVX': '쉐브론 (Chevron)',
    'COP': '코노코필립스 (ConocoPhillips)',
    'SLB': '슐럼버거 (Schlumberger)',
    'EOG': 'EOG리소스 (EOG Resources)',
    'MPC': '마라톤페트롤리엄 (Marathon)',
    'NEE': '넥스트에라 (NextEra)',
    'SO': '서던컴퍼니 (Southern Co)',
    'DUK': '듀크에너지 (Duke Energy)',
    'D': '도미니언 (Dominion)',
    'AEP': '아메리칸일렉트릭 (AEP)',
    'SRE': '셈프라에너지 (Sempra)',
    'PLD': '프로로지스 (Prologis)',
    'AMT': '아메리칸타워 (American Tower)',
    'EQIX': '에퀴닉스 (Equinix)',
    'CCI': '크라운캐슬 (Crown Castle)',
    'WY': '와이어하우저 (Weyerhaeuser)',
    'PSA': '퍼블릭스토리지 (Public Storage)',
    'LIN': '린데 (Linde)',
    'APD': '에어프로덕츠 (Air Products)',
    'SHW': '셔윈윌리엄스 (Sherwin-Williams)',
    'FCX': '프리포트맥모란 (Freeport)',
    'NEM': '뉴몬트 (Newmont)',
    'CTVA': '코르테바 (Corteva)',
    'META': '메타 (Meta)',
    'GOOGL': '구글 (Alphabet)',
    'NFLX': '넷플릭스 (Netflix)',
    'DIS': '디즈니 (Disney)',
    'TMUS': '티모바일 (T-Mobile)',
    'VZ': '버라이즌 (Verizon)',
    'SPY': 'S&P 500 ETF (SPY)'
}

def search_us_stocks(query):
    if not query:
        return []
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=6&newsCount=0"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200:
            data = res.json()
            results = []
            for quote in data.get('quotes', []):
                quote_type = quote.get('quoteType')
                exch = quote.get('exchange', '')
                symbol = quote.get('symbol', '')
                if quote_type == 'EQUITY' and exch in ['NYQ', 'NMS', 'NGM', 'PCX', 'ASE'] and '.' not in symbol:
                    results.append({
                        'code': symbol,
                        'name': quote.get('shortname') or quote.get('longname') or symbol,
                        'market': 'NASDAQ' if exch in ['NMS', 'NGM'] else 'NYSE',
                        'sector': quote.get('sector', 'US Stock')
                    })
            return results
    except Exception as e:
        print(f"Error searching US stocks: {e}")
    return []

def fetch_yahoo_history(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            chart = data.get('chart', {}).get('result', [None])[0]
            if chart:
                timestamps = chart.get('timestamp', [])
                indicators = chart.get('indicators', {}).get('quote', [{}])[0]
                opens   = indicators.get('open',   [])
                highs   = indicators.get('high',   [])
                lows    = indicators.get('low',    [])
                closes  = indicators.get('close',  [])
                volumes = indicators.get('volume', [])

                history = []
                for i, ts in enumerate(timestamps):
                    c = closes[i]  if i < len(closes)  and closes[i]  is not None else None
                    o = opens[i]   if i < len(opens)   and opens[i]   is not None else c
                    h = highs[i]   if i < len(highs)   and highs[i]   is not None else c
                    l = lows[i]    if i < len(lows)    and lows[i]    is not None else c
                    v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0
                    if ts is not None and c is not None:
                        date_str = datetime.fromtimestamp(ts).strftime('%Y%m%d')
                        history.append({
                            'date':   date_str,
                            'open':   round(o, 4),
                            'high':   round(h, 4),
                            'low':    round(l, 4),
                            'close':  round(c, 4),
                            'volume': int(v)
                        })
                return history
    except Exception as e:
        print(f"Error fetching Yahoo history for {symbol}: {e}")
    return []

def fetch_us_stock_metadata(symbol):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}&quotesCount=1"
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    name = symbol
    market = 'US'
    sector = 'US Stock'
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get('quotes', [])
            if quotes:
                quote = quotes[0]
                name = quote.get('shortname') or quote.get('longname') or symbol
                exch = quote.get('exchange', '')
                market = 'NASDAQ' if exch in ['NMS', 'NGM'] else ('NYSE' if exch == 'NYQ' else 'US')
                sector = quote.get('sector', 'US Stock')
    except Exception as e:
        print(f"Error fetching metadata for {symbol}: {e}")
    return name, market, sector

def get_stock_detail(code):
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    res = requests.get(url, headers=headers)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Get sector
    sector_link = soup.find('a', href=re.compile(r'sise_group_detail\.naver\?type=upjong'))
    sector_name = "미분류"
    sector_code = ""
    if sector_link:
        sector_name = sector_link.text.strip()
        href = sector_link.get('href', '')
        match = re.search(r'no=(\d+)', href)
        if match:
            sector_code = match.group(1)
            
    return sector_name, sector_code

def get_price_history(code, count=500):
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0"
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
    res = requests.get(url, headers=headers)
    root = ET.fromstring(res.text)
    items = root.findall('.//item')
    
    history = []
    for item in items:
        data_str = item.attrib['data']
        parts = data_str.split('|')
        if len(parts) >= 5:
            history.append({
                'date': parts[0],
                'open': float(parts[1]),
                'high': float(parts[2]),
                'low': float(parts[3]),
                'close': float(parts[4]),
                'volume': float(parts[5]) if len(parts) > 5 else 0.0
            })
    return history

def get_foreign_ratio_history(code, count=300):
    if not (code and code.isdigit() and len(code) == 6):
        return []
    headers = {'User-Agent': 'Mozilla/5.0'}
    records = []
    for page in range(1, 7):  # 6페이지 = 약 150거래일(6개월) 분량, 속도 최적화
        try:
            url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
            res = requests.get(url, headers=headers, timeout=7)
            res.encoding = 'euc-kr'
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.type2 tr')
            found = 0
            for row in rows:
                cols = [c.get_text(' ', strip=True) for c in row.select('td')]
                if len(cols) < 9:
                    continue
                date = re.sub(r'[^0-9]', '', cols[0])
                ratio_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*%', cols[8])
                if len(date) == 8 and ratio_match:
                    records.append({'date': date, 'ratio': float(ratio_match.group(1))})
                    found += 1
            if found == 0:
                break
        except Exception as e:
            print(f"Error fetching foreign ratio page {page} for {code}: {e}")
            break
    uniq = {}
    for r in records:
        uniq[r['date']] = r['ratio']
    items = sorted(uniq.items(), key=lambda x: x[0])[-count:]
    return [{'date': d, 'ratio': v} for d, v in items]

def get_sector_stocks(sector_code):
    if not sector_code:
        return []
    headers = {'User-Agent': 'Mozilla/5.0'}
    results = []
    seen = set()
    try:
        for page in range(1, 3):  # 2페이지로 제한, 피어 표시용으로 충분
            url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_code}&page={page}"
            res = requests.get(url, headers=headers, timeout=5)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.select_one('table.type_5')
            if not table:
                continue
            links = table.select('a[href*=\"item/main.naver?code=\"]')
            page_count = 0
            for a in links:
                href = a.get('href', '')
                m = re.search(r'code=(\d{6})', href)
                if not m:
                    continue
                code = m.group(1)
                name = a.text.strip()
                if not name or code in seen:
                    continue
                row = a.find_parent('tr')
                cols = [td.get_text(' ', strip=True) for td in row.select('td')] if row else []
                # Naver 업종 상세 표: 시가총액(억)은 일반적으로 9번째 컬럼 인덱스 8
                market_cap = _parse_number(cols[8]) if len(cols) > 8 else 0
                seen.add(code)
                results.append({'code': code, 'name': name, 'market_cap': market_cap or 0})
                page_count += 1
            if page_count == 0:
                break
        return results
    except Exception as e:
        print(f"Error fetching sector stocks({sector_code}): {e}")
        return []

def _parse_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r'[^0-9.\-]', '', str(value))
    if not cleaned or cleaned in ('-', '.', '-.'):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

def resolve_korea_sector_benchmark(sector_name, market):
    normalized = re.sub(r'\s+', '', sector_name or '')
    for keywords, krx_code, yahoo_symbol, label in KOREA_SECTOR_BENCHMARK_RULES:
        if any(keyword in normalized for keyword in keywords):
            return {
                'name': label,
                'code': krx_code,
                'symbol': yahoo_symbol,
                'source': 'KRX 업종지수'
            }

    market_label = 'KOSDAQ' if market == '코스닥' else 'KOSPI'
    return {
        'name': f'KRX {market_label} 업종지수({sector_name or "미분류"})',
        'code': '',
        'symbol': '',
        'source': 'KRX 업종지수'
    }

def fetch_krx_index_history(index_code, count=500):
    if not index_code:
        return []

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=max(900, count * 3))).strftime('%Y%m%d')
    krx_code = str(index_code).zfill(4)
    url = 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
    payload = {
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT00301',
        'locale': 'ko_KR',
        'indIdx': krx_code[0],
        'indIdx2': krx_code[1:],
        'strtDd': start_date,
        'endDd': end_date,
        'share': '2',
        'money': '3',
        'csvxls_isNo': 'false'
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://data.krx.co.kr',
        'Referer': 'https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0301010103'
    }

    try:
        session = requests.Session()
        # Prime KRX session/cookies before API call
        session.get(
            'https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0301010103',
            headers=headers,
            timeout=7
        )
        res = session.post(url, data=payload, headers=headers, timeout=7)
        if res.status_code != 200 or not res.text.lstrip().startswith('{'):
            # Retry once with a fresh primed session
            session = requests.Session()
            session.get(
                'https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0301010103',
                headers=headers,
                timeout=7
            )
            res = session.post(url, data=payload, headers=headers, timeout=7)
        if res.status_code != 200 or not res.text.lstrip().startswith('{'):
            return []
        data = res.json()
        rows = data.get('output') or data.get('block1') or []
        history = []
        for row in rows:
            raw_date = row.get('TRD_DD') or row.get('basDd') or row.get('BAS_DD') or row.get('일자')
            raw_close = (
                row.get('CLSPRC_IDX') or row.get('IDX_CLSPRC') or row.get('closeIdx') or
                row.get('종가') or row.get('지수종가')
            )
            if not raw_date:
                continue
            date = re.sub(r'[^0-9]', '', str(raw_date))
            close = _parse_number(raw_close)
            if len(date) == 8 and close is not None:
                history.append({
                    'date': date,
                    'open': close,
                    'high': close,
                    'low': close,
                    'close': close,
                    'volume': 0
                })
        return sorted(history, key=lambda x: x['date'])[-count:]
    except Exception as e:
        print(f"Error fetching KRX index {index_code}: {e}")
    return []

def fetch_korea_sector_benchmark_history(benchmark):
    # 1차: KRX 공식 업종지수 API
    krx_history = fetch_krx_index_history(benchmark.get('code'))
    if len(krx_history) >= 120:
        return krx_history

    # 2차: Yahoo Finance ETF 프록시 (KRX 실패 시 fallback)
    yahoo_symbol = benchmark.get('symbol', '')
    if yahoo_symbol:
        try:
            yahoo_history = fetch_yahoo_history(yahoo_symbol)
            if len(yahoo_history) >= 120:
                return yahoo_history
        except Exception as e:
            print(f"Yahoo fallback failed for {yahoo_symbol}: {e}")

    return []

def compute_peer_average_history(base_history, peer_histories):
    aligned_dates = [x['date'] for x in base_history]
    price_maps = {
        p_code: {x['date']: x['close'] for x in p_hist}
        for p_code, p_hist in peer_histories.items()
        if p_hist
    }
    if not aligned_dates or not price_maps:
        return []

    base_date = ''
    valid_codes = []
    for date in aligned_dates:
        valid_codes = [code for code, price_map in price_maps.items() if date in price_map]
        if valid_codes:
            base_date = date
            break
    if not base_date:
        return []

    sector_history = []
    for date in aligned_dates:
        norm_sum = 0
        count = 0
        for code in valid_codes:
            price_map = price_maps.get(code, {})
            base_price = price_map.get(base_date)
            current_price = price_map.get(date)
            if base_price and current_price:
                norm_sum += (current_price / base_price) * 100
                count += 1
        if count > 0:
            sector_history.append({
                'date': date,
                'open': norm_sum / count,
                'high': norm_sum / count,
                'low': norm_sum / count,
                'close': norm_sum / count,
                'volume': 0
            })
    return sector_history

def build_top10_mcap_sector_proxy(base_code, base_history, sector_stocks):
    candidates = []
    for peer in sorted(sector_stocks, key=lambda x: x.get('market_cap', 0), reverse=True):
        pcode = peer.get('code')
        if not pcode or pcode == base_code:
            continue
        ph = get_price_history(pcode, count=500)
        if not ph:
            continue
        candidates.append((pcode, peer.get('market_cap', 0), ph))
    if not candidates:
        return []
    top10 = candidates[:10]
    peer_histories = {code: hist for code, _, hist in top10}
    return compute_peer_average_history(base_history, peer_histories)

def parse_date(date_str):
    date_str = date_str.replace('-', '')
    return datetime.strptime(date_str, '%Y%m%d').date()

def calculate_returns(history, periods):
    if not history:
        return {}
        
    dates = [parse_date(x['date']) for x in history]
    closes = [x['close'] for x in history]
    
    if not dates:
        return {}
        
    latest_date = dates[-1]
    latest_close = closes[-1]
    
    returns = {}
    for period_name, days in periods.items():
        if period_name == '1D':
            if len(closes) >= 2:
                returns['1D'] = {
                    'return': ((closes[-1] - closes[-2]) / closes[-2]) * 100,
                    'past_date': dates[-2].strftime('%Y-%m-%d'),
                    'past_close': closes[-2],
                    'latest_close': latest_close
                }
            else:
                returns['1D'] = {
                    'return': 0.0,
                    'past_date': latest_date.strftime('%Y-%m-%d'),
                    'past_close': latest_close,
                    'latest_close': latest_close
                }
            continue
            
        target_date = latest_date - timedelta(days=days)
        closest_idx = 0
        min_diff = abs((dates[0] - target_date).days)
        
        for i, dt in enumerate(dates):
            diff = abs((dt - target_date).days)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
                
        past_close = closes[closest_idx]
        if past_close == 0:
            period_return = 0.0
        else:
            period_return = ((latest_close - past_close) / past_close) * 100
            
        returns[period_name] = {
            'return': period_return,
            'past_date': dates[closest_idx].strftime('%Y-%m-%d'),
            'past_close': past_close,
            'latest_close': latest_close
        }
    return returns

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify([])
        
    results = []
    
    # 1. Nickname check
    if query in NICKNAMES:
        mapped_name = NICKNAMES[query]
        for s in stocks_db:
            if s['name'].lower() == mapped_name.lower():
                results.append(s)
                break
                
    # 2. Substring matches for KOREAN stocks
    for s in stocks_db:
        if any(r['code'] == s['code'] for r in results):
            continue
        if s['name'].lower().startswith(query) or query in s['name'].lower() or query in s['code']:
            results.append(s)
            if len(results) >= 7:
                break
                
    # 3. Add US Stocks via Yahoo Finance autocomplete
    try:
        us_results = search_us_stocks(query)
        for ur in us_results:
            if len(results) >= 10:
                break
            if not any(r['code'] == ur['code'] for r in results):
                results.append(ur)
    except Exception as e:
        print(f"Error merging US stock search: {e}")
                
    return jsonify(results)

@app.route('/api/performance')
def api_performance():
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({'error': '종목 코드가 제공되지 않았습니다.'}), 400
        
    is_us_stock = not (code.isdigit() and len(code) == 6)
    
    if is_us_stock:
        # --- US STOCK FLOW ---
        try:
            name, market, sector = fetch_us_stock_metadata(code)
            stock = {'code': code, 'name': name, 'market': market, 'sector': sector}
            
            # 1. Fetch US stock history
            stock_history = fetch_yahoo_history(code)
            if not stock_history:
                return jsonify({'error': f'미국 주식 {code}의 주가 이력을 가져오는데 실패했습니다.'}), 404
                
            # 2. Fetch Market index (S&P 500: ^GSPC)
            market_symbol = "S&P 500"
            market_history = fetch_yahoo_history('^GSPC')
            if not market_history:
                return jsonify({'error': 'S&P 500 지수 데이터를 가져오는데 실패했습니다.'}), 404
                
            # 3. Mapped sector ETF/index benchmark
            etf = SECTOR_ETF_MAP.get(sector, '^GSPC')
            sector_history = fetch_yahoo_history(etf)
            sector_benchmark = {
                'name': US_SECTOR_BENCHMARK_NAMES.get(etf, f'{sector} benchmark'),
                'code': etf,
                'symbol': etf,
                'source': '미국 섹터 ETF/지수'
            }
            if not sector_history:
                sector_history = market_history
                sector_benchmark = {
                    'name': 'S&P 500',
                    'code': '^GSPC',
                    'symbol': '^GSPC',
                    'source': '미국 시장지수 대체'
                }
                
            # Define peer US symbols
            peer_symbols = US_PEERS_MAP.get(sector, ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'])
            peers_list = [p for p in peer_symbols if p != code][:4]
                
            # Peers objects for detailed clicks in the frontend
            peers = [{'code': p, 'name': US_TICKER_NAMES.get(p, p)} for p in peers_list]
            sector_name = sector
            sector_code = ""
            foreign_ratio = []
            
        except Exception as e:
            return jsonify({'error': f'미국 주식 분석 처리 중 에러가 발생했습니다: {str(e)}'}), 500
    else:
        # --- KOREAN STOCK FLOW ---
        # Find stock in local DB
        stock = next((s for s in stocks_db if s['code'] == code), None)
        if not stock:
            # Fallback details fetch
            try:
                url = f"https://finance.naver.com/item/main.naver?code={code}"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                name_wrap = soup.find('div', class_='wrap_company')
                if not name_wrap:
                    return jsonify({'error': '종목을 찾을 수 없습니다.'}), 404
                name = name_wrap.find('a').text.strip()
                
                market = "코스피"
                description = soup.find('meta', {'name': 'description'})
                if description and '코스닥' in description.get('content', ''):
                    market = '코스닥'
                    
                stock = {'code': code, 'name': name, 'market': market}
            except Exception as e:
                return jsonify({'error': f'종목 정보를 가져오는데 실패했습니다: {str(e)}'}), 404
    
        market_symbol = "KOSPI" if stock['market'] == "코스피" else "KOSDAQ"

        # 1단계: 독립적인 요청 4개를 병렬로 실행
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                fut_stock   = executor.submit(get_price_history, code)
                fut_market  = executor.submit(get_price_history, market_symbol)
                fut_foreign = executor.submit(get_foreign_ratio_history, code, 250)
                fut_detail  = executor.submit(get_stock_detail, code)

                stock_history          = fut_stock.result()
                market_history         = fut_market.result()
                foreign_ratio          = fut_foreign.result()
                sector_name, sector_code = fut_detail.result()
        except Exception as e:
            return jsonify({'error': f'기본 데이터 로딩 실패: {str(e)}'}), 500

        if not stock_history:
            return jsonify({'error': '주가 이력을 불러올 수 없습니다.'}), 404

        # 2단계: 업종 종목 목록과 업종 벤치마크 히스토리를 병렬로 실행
        sector_benchmark = resolve_korea_sector_benchmark(sector_name, stock['market'])
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                fut_sector_stocks = executor.submit(get_sector_stocks, sector_code) if sector_code else None
                fut_bench_hist    = executor.submit(fetch_korea_sector_benchmark_history, sector_benchmark)

                sector_stocks  = fut_sector_stocks.result() if fut_sector_stocks else []
                sector_history = fut_bench_hist.result()
        except Exception as e:
            sector_stocks  = []
            sector_history = []
            print(f"Error fetching sector data: {e}")

        peers_list = [s for s in sector_stocks if s['code'] != code][:4]
        peers = [{'code': s['code'], 'name': s['name']} for s in peers_list]

        # 3단계: 업종 벤치마크 데이터 없으면 시총 상위 10개 프록시로 대체
        if not sector_history:
            sector_history = build_top10_mcap_sector_proxy(code, stock_history, sector_stocks)
            if sector_history:
                sector_benchmark = {
                    'name': f"{sector_name} 업종 프록시(시총 상위 10개 평균)",
                    'code': sector_code or '',
                    'symbol': '',
                    'source': 'Naver 업종 구성종목(시총 상위 10개)'
                }
            else:
                return jsonify({
                    'error': f"KRX 공식 업종지수 및 시총상위10 프록시 데이터를 불러오지 못했습니다. 기준: {sector_benchmark.get('name', '업종지수')}"
                }), 502
                    
    # 5. Calculate returns for periods
    aligned_dates = [x['date'] for x in stock_history]
    periods = {
        '1D': 1,
        '1W': 7,
        '1M': 30,
        '3M': 90,
        '6M': 180,
        '12M': 365
    }
    
    # Calculate returns for stock, market and sector benchmark
    stock_returns = calculate_returns(stock_history, periods)
    market_returns = calculate_returns(market_history, periods)
    sector_returns = calculate_returns(sector_history, periods)
    
    # Compile performance comparison table
    performance_table = []
    for p in ['1D', '1W', '1M', '3M', '6M', '12M']:
        s_ret = stock_returns.get(p, {}).get('return', 0.0)
        m_ret = market_returns.get(p, {}).get('return', 0.0)
        sec_ret = sector_returns.get(p, {}).get('return', 0.0)
        
        performance_table.append({
            'period': p,
            'stock_return': s_ret,
            'market_return': m_ret,
            'sector_return': sec_ret,
            'vs_market': s_ret - m_ret,
            'vs_sector': s_ret - sec_ret
        })
        
    # Generate interactive chart series data (last 240 trading days ~ 1 year)
    chart_len = min(250, len(stock_history))
    chart_dates = aligned_dates[-chart_len:]
    chart_start_date = chart_dates[0]
    
    chart_stock = []
    chart_market = []
    chart_sector = []
    
    # Maps for easy lookups
    stock_map = {x['date']: x['close'] for x in stock_history}
    market_map = {x['date']: x['close'] for x in market_history}
    sector_map = {x['date']: x['close'] for x in sector_history}
    
    stock_base = next((stock_map[d] for d in chart_dates if d in stock_map), 1.0)
    market_base = next((market_map[d] for d in chart_dates if d in market_map), 1.0)
    sector_base = next((sector_map[d] for d in chart_dates if d in sector_map), 1.0)
    prev_stock = stock_base
    prev_market = market_base
    prev_sector = sector_base
    
    for date in chart_dates:
        prev_stock = stock_map.get(date, prev_stock)
        prev_market = market_map.get(date, prev_market)
        prev_sector = sector_map.get(date, prev_sector)
        s_val = (prev_stock / stock_base) * 100 if stock_base else 100.0
        m_val = (prev_market / market_base) * 100 if market_base else 100.0
        sec_val = (prev_sector / sector_base) * 100 if sector_base else 100.0
        
        formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        
        chart_stock.append({'date': formatted_date, 'value': s_val})
        chart_market.append({'date': formatted_date, 'value': m_val})
        chart_sector.append({'date': formatted_date, 'value': sec_val})
        
    return jsonify({
        'stock': {
            'code': stock['code'],
            'name': stock['name'],
            'market': stock['market'],
            'sector_name': sector_name,
            'sector_code': sector_code
        },
        'benchmark': market_symbol,
        'sector_benchmark': sector_benchmark,
        'peers': peers,
        'table': performance_table,
        'chart': {
            'dates': [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in chart_dates],
            'stock': [x['value'] for x in chart_stock],
            'market': [x['value'] for x in chart_market],
            'sector': [x['value'] for x in chart_sector]
        },
        'ohlc': stock_history,
        'foreign_ratio': foreign_ratio
    })

# Vercel Python runtime entrypoint (looks for 'handler' or 'app')
handler = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
