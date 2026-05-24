/* ==========================================================================
   Antigravity Stock Relative Returns Dashboard - Frontend Controller
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const searchInput = document.getElementById('stock-search');
    const autocompleteList = document.getElementById('autocomplete-list');
    const clearSearchBtn = document.getElementById('clear-search-btn');
    const spinner = document.getElementById('loading-spinner');
    const recentSearchesContainer = document.getElementById('recent-searches-container');
    const recentSearchesList = document.getElementById('recent-searches-list');
    const holdingContainer = document.getElementById('holding-container');
    const holdingList = document.getElementById('holding-list');
    const favoriteContainer = document.getElementById('favorite-container');
    const favoriteList = document.getElementById('favorite-list');
    const holdingInput = document.getElementById('holding-input');
    const holdingAutocompleteList = document.getElementById('holding-autocomplete-list');
    const favoriteInput = document.getElementById('favorite-input');
    const favoriteAutocompleteList = document.getElementById('favorite-autocomplete-list');
    const addHoldingBtn = document.getElementById('add-holding-btn');
    const addFavoriteBtn = document.getElementById('add-favorite-btn');
    
    // Views
    const welcomeView = document.getElementById('welcome-view');
    const mainDashboard = document.getElementById('main-dashboard');
    
    // Stock Header Elements
    const stockNameEl = document.getElementById('stock-name');
    const stockCodeBadge = document.getElementById('stock-code-badge');
    const marketBadge = document.getElementById('market-badge');
    const sectorBadge = document.getElementById('sector-badge');
    
    // Table Elements
    const performanceTbody = document.getElementById('performance-tbody');
    const sellWarningMessage = document.getElementById('sell-warning-message');
    
    // Peers Elements
    const peersListContainer = document.getElementById('peers-list');
    const sectorBenchmarkDesc = document.getElementById('sector-benchmark-desc');
    
    // Chart Elements
    const periodButtons = document.querySelectorAll('.period-btn');
    let relativeChart = null; // Chart.js instance holder
    
    // State Variables
    let rawChartData = null; // Stores { dates:[], stock:[], market:[], sector:[] }
    let benchmarkSymbol = '지수';
    let sectorBenchmarkLabel = '업종지수';
    let rawOhlcData = [];    // Raw OHLC data for daily candlestick
    let rawForeignRatioData = [];
    let candleTimeframe = 'day'; // day | week | month
    let candleWindowOffset = 0;  // 0 = latest window, positive = moved to past
    let candleChartInstance = null; // ApexCharts instance holder
    let volumeChartInstance = null; // ApexCharts volume instance holder
    let macdChartInstance = null;   // ApexCharts MACD instance holder
    let foreignChartInstance = null;
    let candleDragState = null;
    
    // Recent Searches Storage Engine
    function saveToRecentSearches(code, name) {
        if (!code || !name) return;
        let recent = JSON.parse(localStorage.getItem('recent_searches') || '[]');
        // Remove duplicate to bring it to the front
        recent = recent.filter(item => item.code !== code);
        // Add to front
        recent.unshift({ code, name });
        // Keep only top 10 recent searches
        recent = recent.slice(0, 10);
        localStorage.setItem('recent_searches', JSON.stringify(recent));
        renderRecentSearches();
    }

    function renderRecentSearches() {
        const recent = JSON.parse(localStorage.getItem('recent_searches') || '[]');
        if (recent.length === 0) {
            recentSearchesContainer.classList.add('hidden');
            return;
        }

        recentSearchesList.innerHTML = '';
        recent.forEach(item => {
            const btn = document.createElement('button');
            btn.className = 'recent-badge';
            btn.textContent = item.name;
            btn.addEventListener('click', () => {
                searchInput.value = item.name;
                loadStockPerformance(item.code);
            });
            recentSearchesList.appendChild(btn);
        });
        recentSearchesContainer.classList.remove('hidden');
    }

    function saveNamedList(key, name) {
        const val = (name || '').trim();
        if (!val) return;
        let arr = JSON.parse(localStorage.getItem(key) || '[]');
        arr = arr.filter(x => x !== val);
        arr.unshift(val);
        arr = arr.slice(0, 10);
        localStorage.setItem(key, JSON.stringify(arr));
    }

    async function openNamedStock(name) {
        const q = (name || '').trim();
        if (!q) return;
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            if (!res.ok) return;
            const items = await res.json();
            if (items.length > 0) {
                searchInput.value = items[0].name;
                loadStockPerformance(items[0].code);
            }
        } catch (err) {
            console.error(err);
        }
    }

    function renderNamedList(key, container, listEl) {
        const arr = JSON.parse(localStorage.getItem(key) || '[]');
        listEl.innerHTML = '';
        if (!arr.length) {
            container.classList.add('hidden');
            return;
        }
        arr.forEach((name) => {
            const btn = document.createElement('button');
            btn.className = 'recent-badge';
            btn.innerHTML = `<span>${name}</span><span class="named-remove">×</span>`;
            btn.addEventListener('click', async () => {
                await openNamedStock(name);
            });
            const removeEl = btn.querySelector('.named-remove');
            removeEl?.addEventListener('click', (e) => {
                e.stopPropagation();
                const next = arr.filter(x => x !== name);
                localStorage.setItem(key, JSON.stringify(next));
                renderNamedList(key, container, listEl);
            });
            listEl.appendChild(btn);
        });
        container.classList.remove('hidden');
    }

    // Initialize Recent Searches
    renderRecentSearches();
    renderNamedList('holding_stocks', holdingContainer, holdingList);
    renderNamedList('favorite_stocks', favoriteContainer, favoriteList);
    if (addHoldingBtn) {
        addHoldingBtn.addEventListener('click', () => {
            saveNamedList('holding_stocks', holdingInput.value);
            holdingInput.value = '';
            if (holdingAutocompleteList) holdingAutocompleteList.classList.add('hidden');
            renderNamedList('holding_stocks', holdingContainer, holdingList);
        });
    }
    if (addFavoriteBtn) {
        addFavoriteBtn.addEventListener('click', () => {
            saveNamedList('favorite_stocks', favoriteInput.value);
            favoriteInput.value = '';
            renderNamedList('favorite_stocks', favoriteContainer, favoriteList);
        });
    }

    // Popular Queries Clicks
    const popularBtns = document.querySelectorAll('.popular-btn');
    popularBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            searchInput.value = btn.textContent;
            triggerSearch(btn.textContent);
        });
    });

    // 1. Clear Search Bar Event
    clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        searchInput.focus();
        clearSearchBtn.style.display = 'none';
        autocompleteList.classList.add('hidden');
    });

    // 2. Search Input Keyup Event (Debounced Autocomplete)
    let debounceTimer;
    searchInput.addEventListener('keyup', (e) => {
        const query = searchInput.value.trim();
        
        // Toggle Clear button visibility
        if (query.length > 0) {
            clearSearchBtn.style.display = 'block';
        } else {
            clearSearchBtn.style.display = 'none';
            autocompleteList.classList.add('hidden');
            return;
        }

        // Detect Enter Key
        if (e.key === 'Enter') {
            triggerSearch(query);
            return;
        }

        // Live autocomplete search after 200ms debounce
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            fetchAutocomplete(query);
        }, 200);
    });

    // Close autocomplete when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !autocompleteList.contains(e.target)) {
            autocompleteList.classList.add('hidden');
        }
        if (
            holdingAutocompleteList &&
            !holdingInput.contains(e.target) &&
            !holdingAutocompleteList.contains(e.target)
        ) {
            holdingAutocompleteList.classList.add('hidden');
        }
        if (
            favoriteAutocompleteList &&
            !favoriteInput.contains(e.target) &&
            !favoriteAutocompleteList.contains(e.target)
        ) {
            favoriteAutocompleteList.classList.add('hidden');
        }
    });

    if (holdingInput && holdingAutocompleteList) {
        let holdingDebounce;
        holdingInput.addEventListener('keyup', (e) => {
            const query = holdingInput.value.trim();
            if (e.key === 'Enter') {
                saveNamedList('holding_stocks', holdingInput.value);
                holdingInput.value = '';
                holdingAutocompleteList.classList.add('hidden');
                renderNamedList('holding_stocks', holdingContainer, holdingList);
                return;
            }
            if (!query) {
                holdingAutocompleteList.classList.add('hidden');
                return;
            }
            clearTimeout(holdingDebounce);
            holdingDebounce = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                    if (!res.ok) throw new Error('holding search failed');
                    const items = await res.json();
                    holdingAutocompleteList.innerHTML = '';
                    if (!items.length) {
                        holdingAutocompleteList.classList.add('hidden');
                        return;
                    }
                    items.slice(0, 8).forEach((item) => {
                        const li = document.createElement('li');
                        li.className = 'autocomplete-item';
                        li.innerHTML = `<div class="ac-name-wrapper"><span class="ac-name">${item.name}</span><span class="ac-code">${item.code}</span></div>`;
                        li.addEventListener('click', () => {
                            holdingInput.value = item.name;
                            saveNamedList('holding_stocks', item.name);
                            holdingInput.value = '';
                            holdingAutocompleteList.classList.add('hidden');
                            renderNamedList('holding_stocks', holdingContainer, holdingList);
                        });
                        holdingAutocompleteList.appendChild(li);
                    });
                    holdingAutocompleteList.classList.remove('hidden');
                } catch (err) {
                    console.error(err);
                }
            }, 180);
        });
    }
    if (favoriteInput && favoriteAutocompleteList) {
        let favoriteDebounce;
        favoriteInput.addEventListener('keyup', (e) => {
            const query = favoriteInput.value.trim();
            if (e.key === 'Enter') {
                saveNamedList('favorite_stocks', favoriteInput.value);
                favoriteInput.value = '';
                favoriteAutocompleteList.classList.add('hidden');
                renderNamedList('favorite_stocks', favoriteContainer, favoriteList);
                return;
            }
            if (!query) {
                favoriteAutocompleteList.classList.add('hidden');
                return;
            }
            clearTimeout(favoriteDebounce);
            favoriteDebounce = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                    if (!res.ok) throw new Error('favorite search failed');
                    const items = await res.json();
                    favoriteAutocompleteList.innerHTML = '';
                    if (!items.length) {
                        favoriteAutocompleteList.classList.add('hidden');
                        return;
                    }
                    items.slice(0, 8).forEach((item) => {
                        const li = document.createElement('li');
                        li.className = 'autocomplete-item';
                        li.innerHTML = `<div class="ac-name-wrapper"><span class="ac-name">${item.name}</span><span class="ac-code">${item.code}</span></div>`;
                        li.addEventListener('click', () => {
                            favoriteInput.value = item.name;
                            saveNamedList('favorite_stocks', item.name);
                            favoriteInput.value = '';
                            favoriteAutocompleteList.classList.add('hidden');
                            renderNamedList('favorite_stocks', favoriteContainer, favoriteList);
                        });
                        favoriteAutocompleteList.appendChild(li);
                    });
                    favoriteAutocompleteList.classList.remove('hidden');
                } catch (err) {
                    console.error(err);
                }
            }, 180);
        });
    }

    // 3. Fetch Autocomplete Suggestions
    async function fetchAutocomplete(query) {
        if (!query) return;
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            if (!res.ok) throw new Error('Search failed');
            const data = await res.json();
            renderAutocomplete(data);
        } catch (err) {
            console.error('Autocomplete fetch error:', err);
        }
    }

    // 4. Render Autocomplete Dropdown
    function renderAutocomplete(items) {
        autocompleteList.innerHTML = '';
        if (items.length === 0) {
            autocompleteList.classList.add('hidden');
            return;
        }

        items.forEach(item => {
            const li = document.createElement('li');
            li.className = 'autocomplete-item';
            
            let marketClass = 'ac-market-kospi';
            if (item.market === '코스닥') {
                marketClass = 'ac-market-kosdaq';
            } else if (item.market === 'NASDAQ' || item.market === 'NYSE' || item.market === 'US') {
                marketClass = 'ac-market-us';
            }
            
            li.innerHTML = `
                <div class="ac-name-wrapper">
                    <span class="ac-name">${item.name}</span>
                    <span class="ac-code">${item.code}</span>
                </div>
                <span class="ac-market ${marketClass}">${item.market}</span>
            `;
            
            li.addEventListener('click', () => {
                searchInput.value = item.name;
                autocompleteList.classList.add('hidden');
                loadStockPerformance(item.code);
            });
            
            autocompleteList.appendChild(li);
        });
        
        autocompleteList.classList.remove('hidden');
    }

    // 5. Trigger Search when Enter is hit or Popular Queries is clicked
    async function triggerSearch(query) {
        if (!query) return;
        autocompleteList.classList.add('hidden');
        showLoading(true);
        
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            if (data.length > 0) {
                // If there's a match, load the first one
                searchInput.value = data[0].name;
                loadStockPerformance(data[0].code);
            } else {
                showLoading(false);
                alert(`'${query}'에 매칭되는 종목을 찾을 수 없습니다. 종목명이나 코드를 확인해 주세요.`);
            }
        } catch (err) {
            showLoading(false);
            console.error('Search trigger failed:', err);
            alert('종목 검색 도중 오류가 발생했습니다.');
        }
    }

    // 6. Fetch Stock Performance and Render Dashboard
    async function loadStockPerformance(code) {
        showLoading(true);
        welcomeView.classList.add('hidden');
        mainDashboard.classList.add('hidden');
        
        try {
            const res = await fetch(`/api/performance?code=${code}`);
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.error || '실패');
            }
            const data = await res.json();
            
            // Set State
            rawChartData = data.chart;
            benchmarkSymbol = data.benchmark;
            sectorBenchmarkLabel = data.sector_benchmark?.name || data.stock.sector_name || '업종지수';
            rawOhlcData = data.ohlc || [];
            rawForeignRatioData = data.foreign_ratio || [];
            
            renderDashboard(data);
            
            // Save search to recent searches list
            saveToRecentSearches(data.stock.code, data.stock.name);
        } catch (err) {
            showLoading(false);
            welcomeView.classList.remove('hidden');
            alert(`수익률 로딩 오류: ${err.message}`);
        }
    }

    // 7. Toggle Loading Spinner
    function showLoading(isLoading) {
        if (isLoading) {
            spinner.classList.remove('hidden');
        } else {
            spinner.classList.add('hidden');
        }
    }

    // 8. Render Dashboard UI
    function renderDashboard(data) {
        // A. Set Header Meta
        stockNameEl.textContent = data.stock.name;
        stockCodeBadge.textContent = data.stock.code;
        
        marketBadge.textContent = data.stock.market;
        marketBadge.className = 'stock-badge ' + (data.stock.market === '코스피' ? 'market-badge-kospi' : 'market-badge-kosdaq');
        
        sectorBadge.textContent = data.stock.sector_name;
        
        // B. Populate Table
        renderPerformanceTable(data.table);
        
        // C. Render Sector Benchmark and references
        renderPeersList(data.peers, data.sector_benchmark);
        
        // D. Setup and Draw Chart
        renderChart(12); // Default to 12 months chart
        
        // E. Render Daily Candlestick Chart
        renderCandleChart();
        
        // Reset period buttons active state
        periodButtons.forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-months') === '12') {
                btn.classList.add('active');
            }
        });
        
        // Show Dashboard and Hide Spinner
        showLoading(false);
        mainDashboard.classList.remove('hidden');
    }

    // 9. Render Performance Table Helper
    function renderPerformanceTable(tableRows) {
        performanceTbody.innerHTML = '';
        if (sellWarningMessage) {
            sellWarningMessage.classList.add('hidden');
            sellWarningMessage.textContent = '';
        }

        const weeklyRow = tableRows.find(row => row.period === '1W');
        const monthlyRow = tableRows.find(row => row.period === '1M');
        const marketSellSignal = weeklyRow?.vs_market <= -5.0 && monthlyRow?.vs_market <= -5.0;
        const sectorSellSignal = weeklyRow?.vs_sector <= -5.0 && monthlyRow?.vs_sector <= -5.0;
        if (sellWarningMessage && (marketSellSignal || sectorSellSignal)) {
            const reasons = [];
            if (marketSellSignal) reasons.push('시장 지수 대비 1주일/1개월 동시 경고');
            if (sectorSellSignal) reasons.push('업종지수 대비 1주일/1개월 동시 경고');
            sellWarningMessage.textContent = `매도 추천: ${reasons.join(', ')}`;
            sellWarningMessage.classList.remove('hidden');
        }
        
        tableRows.forEach(row => {
            const tr = document.createElement('tr');
            
            // Helpers to style performance returns
            const formatPct = (val) => `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;
            const formatRelative = (val) => `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;
            const getBadgeClass = (val) => val > 0 ? 'badge-pos' : (val < 0 ? 'badge-neg' : 'zero-val');
            const getMarketBadgeClass = (val) => val > 0 ? 'badge-market-pos' : (val < 0 ? 'badge-market-neg' : 'zero-val');
            
            const periodLabels = {
                '1D': '당일',
                '1W': '1주일',
                '1M': '1개월',
                '3M': '3개월',
                '6M': '6개월',
                '12M': '12개월'
            };
            
            const isWarningPeriod = ['1W', '1M'].includes(row.period);
            const isMarketWarning = isWarningPeriod && row.vs_market <= -5.0;
            const isSectorWarning = isWarningPeriod && row.vs_sector <= -5.0;
            
            let marketBadgeContent = '';
            if (isMarketWarning) {
                tr.classList.add('underperform-row');
                marketBadgeContent = `<span class="${getBadgeClass(row.vs_market)}">${formatRelative(row.vs_market)}</span> <span class="warning-badge">⚠️ 경고</span>`;
            } else {
                marketBadgeContent = `<span class="${getMarketBadgeClass(row.vs_market)}">${formatRelative(row.vs_market)}</span>`;
            }

            let sectorBadgeContent = '';
            if (isSectorWarning) {
                tr.classList.add('underperform-row');
                sectorBadgeContent = `<span class="${getBadgeClass(row.vs_sector)}">${formatRelative(row.vs_sector)}</span> <span class="warning-badge">⚠️ 경고</span>`;
            } else {
                sectorBadgeContent = `<span class="${getBadgeClass(row.vs_sector)}">${formatRelative(row.vs_sector)}</span>`;
            }
            
            tr.innerHTML = `
                <td class="period-cell">${periodLabels[row.period] || row.period}</td>
                <td class="return-val"><span class="${getBadgeClass(row.stock_return)}">${formatPct(row.stock_return)}</span></td>
                <td class="relative-cell">${marketBadgeContent}</td>
                <td class="relative-cell">${sectorBadgeContent}</td>
            `;
            
            performanceTbody.appendChild(tr);
        });
    }

    // 9B. Helper to calculate Moving Averages (MA)
    function calculateMA(ohlcList, period) {
        const ma = [];
        for (let i = 0; i < ohlcList.length; i++) {
            if (i < period - 1) {
                ma.push({ x: ohlcList[i].date, y: null });
            } else {
                let sum = 0;
                for (let j = 0; j < period; j++) {
                    sum += ohlcList[i - j].close;
                }
                ma.push({ x: ohlcList[i].date, y: parseFloat((sum / period).toFixed(2)) });
            }
        }
        return ma;
    }

    // 9B-2. Helper to calculate MACD (12, 26, 9)
    function calculateMACD(ohlcList) {
        const closes = ohlcList.map(item => item.close);
        
        const getEMA = (prices, period) => {
            const k = 2 / (period + 1);
            const ema = [];
            let currentEma = prices[0] || 0;
            for (let i = 0; i < prices.length; i++) {
                if (i === 0) {
                    currentEma = prices[0] || 0;
                } else {
                    currentEma = prices[i] * k + currentEma * (1 - k);
                }
                ema.push(i < period - 1 ? null : parseFloat(currentEma.toFixed(4)));
            }
            return ema;
        };
        
        const ema12 = getEMA(closes, 12);
        const ema26 = getEMA(closes, 26);
        
        const macdLine = [];
        for (let i = 0; i < closes.length; i++) {
            if (ema12[i] === null || ema26[i] === null) {
                macdLine.push(null);
            } else {
                macdLine.push(parseFloat((ema12[i] - ema26[i]).toFixed(4)));
            }
        }
        
        const signalLine = [];
        const k9 = 2 / (9 + 1);
        let currentSignal = null;
        for (let i = 0; i < closes.length; i++) {
            if (macdLine[i] === null) {
                signalLine.push(null);
            } else {
                if (currentSignal === null) {
                    currentSignal = macdLine[i];
                    signalLine.push(null);
                } else {
                    currentSignal = macdLine[i] * k9 + currentSignal * (1 - k9);
                    signalLine.push(parseFloat(currentSignal.toFixed(4)));
                }
            }
        }
        
        // Nullify the first 8 valid MACD points of the Signal line to prevent starting bias
        let validMacdCount = 0;
        for (let i = 0; i < closes.length; i++) {
            if (macdLine[i] !== null) {
                validMacdCount++;
                if (validMacdCount < 9) {
                    signalLine[i] = null;
                }
            }
        }
        
        const histogram = [];
        for (let i = 0; i < closes.length; i++) {
            if (macdLine[i] === null || signalLine[i] === null) {
                histogram.push(null);
            } else {
                histogram.push(parseFloat((macdLine[i] - signalLine[i]).toFixed(4)));
            }
        }
        
        return {
            macd: macdLine,
            signal: signalLine,
            histogram: histogram
        };
    }

    function aggregateOHLC(ohlcList, timeframe) {
        if (timeframe === 'day') return ohlcList.slice();
        const grouped = new Map();
        for (const item of ohlcList) {
            const y = item.date.slice(0, 4);
            const m = item.date.slice(4, 6);
            const d = item.date.slice(6, 8);
            const dateObj = new Date(`${y}-${m}-${d}T00:00:00`);
            let key = '';
            if (timeframe === 'week') {
                const day = (dateObj.getDay() + 6) % 7;
                const monday = new Date(dateObj);
                monday.setDate(dateObj.getDate() - day);
                key = `${monday.getFullYear()}${String(monday.getMonth() + 1).padStart(2, '0')}${String(monday.getDate()).padStart(2, '0')}`;
            } else {
                key = `${y}${m}01`;
            }
            if (!grouped.has(key)) {
                grouped.set(key, {
                    date: key,
                    open: item.open,
                    high: item.high,
                    low: item.low,
                    close: item.close,
                    volume: item.volume
                });
            } else {
                const g = grouped.get(key);
                g.high = Math.max(g.high, item.high);
                g.low = Math.min(g.low, item.low);
                g.close = item.close;
                g.volume += item.volume;
            }
        }
        return Array.from(grouped.values()).sort((a, b) => a.date.localeCompare(b.date));
    }

    // 9C. Render Daily Candlestick and Moving Averages
    function renderCandleChart() {
        const chartDiv = document.getElementById('candle-chart');
        if (!chartDiv) return;
        
        if (!rawOhlcData || rawOhlcData.length === 0) {
            chartDiv.innerHTML = '<div style="padding: 3rem; text-align: center; color: var(--text-secondary);">캔들 차트 데이터가 없거나 로딩 중입니다.</div>';
            return;
        }
        
        // Read user input days
        let daysToDisplay = 120;
        const daysInput = document.getElementById('candle-days-input');
        if (daysInput) {
            const parsedVal = parseInt(daysInput.value);
            if (parsedVal >= 10 && parsedVal <= 400) {
                daysToDisplay = parsedVal;
            }
        }
        const sourceOhlcData = aggregateOHLC(rawOhlcData, candleTimeframe);
        candleWindowOffset = Math.max(0, Math.min(candleWindowOffset, Math.max(0, sourceOhlcData.length - daysToDisplay)));
        const maxStart = Math.max(0, sourceOhlcData.length - daysToDisplay);
        const visibleStart = Math.max(0, maxStart - candleWindowOffset);
        const visibleEnd = Math.min(sourceOhlcData.length - 1, visibleStart + daysToDisplay - 1);
        const visibleOhlcData = sourceOhlcData.slice(visibleStart, visibleEnd + 1);
        
        // Calculate Moving Averages (MA) on the complete dataset so the beginning of the display window is accurate!
        const ma5 = calculateMA(sourceOhlcData, 5);
        const ma10 = calculateMA(sourceOhlcData, 10);
        const ma20 = calculateMA(sourceOhlcData, 20);
        const ma60 = calculateMA(sourceOhlcData, 60);
        const ma120 = calculateMA(sourceOhlcData, 120);
        const ma240 = calculateMA(sourceOhlcData, 240);
        
        // Helper to format YYYYMMDD -> YYYY.MM.DD
        const formatDate = (str) => {
            if (!str) return str;
            const m = str.match(/^(\d{4})(\d{2})(\d{2})$/);
            return m ? `${m[1]}.${m[2]}.${m[3]}` : str;
        };

        // Format only the visible window so all three subcharts share the exact same period.
        const candleSeriesData = visibleOhlcData.map(item => ({
            x: formatDate(item.date),
            y: [item.open, item.high, item.low, item.close]
        }));
        
        const ma5SeriesData = ma5.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        const ma10SeriesData = ma10.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        const ma20SeriesData = ma20.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        const ma60SeriesData = ma60.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        const ma120SeriesData = ma120.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        const ma240SeriesData = ma240.slice(visibleStart).map(item => ({ x: formatDate(item.x), y: item.y }));
        
        // Destroy past charts to prevent double-draw instances
        if (candleChartInstance) {
            candleChartInstance.destroy();
            candleChartInstance = null;
        }
        if (volumeChartInstance) {
            volumeChartInstance.destroy();
            volumeChartInstance = null;
        }
        if (macdChartInstance) {
            macdChartInstance.destroy();
            macdChartInstance = null;
        }
        if (foreignChartInstance) {
            foreignChartInstance.destroy();
            foreignChartInstance = null;
        }

        const chartGroupId = 'stock-charts';
        const volumeChartHeight = 188;
        const macdChartHeight = 314;
        const foreignChartHeight = 180;
        const positiveColor = '#dc2626';
        const negativeColor = '#2563eb';
        const hoverLineColor = '#0f172a';
        const sharedCrosshair = {
            show: true,
            width: 1,
            position: 'front',
            opacity: 0.75,
            stroke: {
                color: hoverLineColor,
                width: 1,
                dashArray: 4
            }
        };
        const getPlotMetrics = (target, fallbackLeft = 84, fallbackRight = 24) => {
            const targetRect = target.getBoundingClientRect();
            const grid = target.querySelector('.apexcharts-grid');
            if (!grid) {
                return {
                    left: fallbackLeft,
                    right: fallbackRight,
                    width: Math.max(1, targetRect.width - fallbackLeft - fallbackRight)
                };
            }
            const gridRect = grid.getBoundingClientRect();
            const left = Math.max(0, gridRect.left - targetRect.left);
            const right = Math.max(0, targetRect.right - gridRect.right);
            return {
                left,
                right,
                width: Math.max(1, gridRect.width)
            };
        };
        
        // Detect crossovers and prepare annotations
        const candleCrossMarkers = [];
        const detectCrosses = (short, long, name, lane = 0) => {
            for (let i = 1; i < short.length; i++) {
                const prevShort = short[i - 1].y;
                const prevLong = long[i - 1].y;
                const curShort = short[i].y;
                const curLong = long[i].y;
                if (prevShort == null || prevLong == null || curShort == null || curLong == null) continue;
                const isGolden = prevShort < prevLong && curShort > curLong;
                const isDead = prevShort > prevLong && curShort < curLong;
                if (isGolden || isDead) {
                    const labelColor = isGolden ? positiveColor : negativeColor;
                    candleCrossMarkers.push({
                        index: i,
                        text: name,
                        lane,
                        isGolden,
                        color: labelColor,
                        background: 'rgba(255, 255, 255, 0.16)'
                    });
                }
            }
        };
        // Detect crosses on full datasets so annotations are visible when panning
        detectCrosses(ma5, ma20, '5/20', 0);
        detectCrosses(ma5, ma60, '5/60', 1);
        detectCrosses(ma20, ma60, '20/60', 2);

        // Prepare Volume series data
        const volumeSeriesData = visibleOhlcData.map(item => ({
            x: formatDate(item.date),
            y: item.volume
        }));

        // Prepare MACD series data
        const macdData = calculateMACD(sourceOhlcData);
        const macdSeriesData = macdData.macd.slice(visibleStart).map((val, idx) => ({
            x: formatDate(visibleOhlcData[idx].date),
            y: val
        }));
        const signalSeriesData = macdData.signal.slice(visibleStart).map((val, idx) => ({
            x: formatDate(visibleOhlcData[idx].date),
            y: val
        }));
        const histogramSeriesData = macdData.histogram.slice(visibleStart).map((val, idx) => ({
            x: formatDate(visibleOhlcData[idx].date),
            y: val
        }));

        const macdFiniteValues = [
            ...macdData.macd,
            ...macdData.signal,
            ...macdData.histogram
        ].filter((val) => Number.isFinite(val));
        const macdMin = macdFiniteValues.length ? Math.min(...macdFiniteValues) : -1;
        const macdMax = macdFiniteValues.length ? Math.max(...macdFiniteValues) : 1;
        const macdSpan = Math.max(1, macdMax - macdMin);

        const macdCrossAnnotations = [];
        for (let i = Math.max(1, visibleStart); i < sourceOhlcData.length; i++) {
            const prevMacd = macdData.macd[i - 1];
            const prevSignal = macdData.signal[i - 1];
            const curMacd = macdData.macd[i];
            const curSignal = macdData.signal[i];
            if (prevMacd == null || prevSignal == null || curMacd == null || curSignal == null) continue;

            const isGolden = prevMacd < prevSignal && curMacd > curSignal;
            const isDead = prevMacd > prevSignal && curMacd < curSignal;
            if (!isGolden && !isDead) continue;

            const goldenOffset = macdSpan * 0.07;
            const deadOffset = macdSpan * 0.006;
            const topLine = Math.max(curMacd, curSignal);
            const bottomLine = Math.min(curMacd, curSignal);
            macdCrossAnnotations.push({
                x: formatDate(sourceOhlcData[i].date),
                y: isGolden ? bottomLine - goldenOffset : topLine + deadOffset,
                marker: {
                    size: 0
                },
                label: {
                    text: isGolden ? '▲' : '▼',
                    offsetY: isGolden ? 12 : 0,
                    borderColor: 'transparent',
                    borderWidth: 0,
                    style: {
                        color: isGolden ? positiveColor : negativeColor,
                        background: 'rgba(255, 255, 255, 0)',
                        fontSize: '18px',
                        fontWeight: 900,
                        padding: { top: 0, bottom: 0, left: 2, right: 2 }
                    }
                }
            });
        }

        const buildMacdBackgroundBands = () => {
            const bands = [];
            let activeSign = null;
            let startIndex = null;

            const pushBand = (fromIndex, toIndex, sign) => {
                if (fromIndex == null || toIndex == null || toIndex < fromIndex || !sign) return;
                bands.push({
                    x: formatDate(sourceOhlcData[fromIndex].date),
                    x2: formatDate(sourceOhlcData[toIndex].date),
                    fillColor: sign === 'positive' ? '#fecaca' : '#bfdbfe',
                    opacity: 0.28,
                    label: {
                        text: '',
                        style: {
                            background: 'transparent'
                        }
                    }
                });
            };

            for (let i = visibleStart; i < macdData.macd.length; i++) {
                const value = macdData.macd[i];
                if (value == null) continue;
                const sign = value >= 0 ? 'positive' : 'negative';

                if (activeSign === null) {
                    activeSign = sign;
                    startIndex = i;
                    continue;
                }

                if (sign !== activeSign) {
                    pushBand(startIndex, i, activeSign);
                    activeSign = sign;
                    startIndex = i;
                }
            }

            pushBand(startIndex, macdData.macd.length - 1, activeSign);
            return bands;
        };

        const macdBackgroundBands = buildMacdBackgroundBands();
        const candleBackgroundBands = macdBackgroundBands.map((band) => ({
            ...band,
            opacity: 0.32,
            label: { text: '' }
        }));
        const macdZeroLine = [{
            y: 0,
            borderColor: '#94a3b8',
            strokeDashArray: 4
        }];

        const renderSyncedHoverOverlay = (chartId, dataPointIndex) => {
            const target = document.getElementById(chartId);
            if (!target || dataPointIndex < 0 || !sourceOhlcData[dataPointIndex]) return;

            if (dataPointIndex < visibleStart || dataPointIndex > visibleEnd) return;

            const oldOverlay = target.querySelector('.synced-hover-overlay');
            if (oldOverlay) oldOverlay.remove();

            const visibleSpan = Math.max(1, visibleEnd - visibleStart);
            const xPercent = ((dataPointIndex - visibleStart) / visibleSpan) * 100;
            const date = formatDate(sourceOhlcData[dataPointIndex].date);

            target.style.position = 'relative';
            const plotMetrics = getPlotMetrics(target);
            const overlay = document.createElement('div');
            overlay.className = 'synced-hover-overlay';
            Object.assign(overlay.style, {
                position: 'absolute',
                top: '0',
                bottom: '0',
                left: `${plotMetrics.left}px`,
                right: `${plotMetrics.right}px`,
                pointerEvents: 'none',
                zIndex: '14'
            });

            const line = document.createElement('div');
            Object.assign(line.style, {
                position: 'absolute',
                left: `${xPercent}%`,
                top: '10px',
                bottom: '24px',
                borderLeft: `1px dashed ${hoverLineColor}`,
                opacity: '0.75',
                transform: 'translateX(-50%)'
            });

            const label = document.createElement('span');
            label.textContent = date;
            Object.assign(label.style, {
                position: 'absolute',
                left: `${xPercent}%`,
                bottom: '2px',
                transform: 'translateX(-50%)',
                whiteSpace: 'nowrap',
                padding: '2px 5px',
                borderRadius: '4px',
                background: hoverLineColor,
                color: '#ffffff',
                fontSize: '10px',
                fontWeight: '700'
            });

            overlay.append(line, label);
            target.appendChild(overlay);
        };

        const clearSyncedHoverOverlay = (chartId) => {
            const target = document.getElementById(chartId);
            const oldOverlay = target?.querySelector('.synced-hover-overlay');
            if (oldOverlay) oldOverlay.remove();
        };

        let syncedHoverIndex = null;
        const syncSubChartsByIndex = (dataPointIndex) => {
            if (dataPointIndex == null || dataPointIndex < 0 || !sourceOhlcData[dataPointIndex]) return;
            if (syncedHoverIndex === dataPointIndex) return;
            syncedHoverIndex = dataPointIndex;

            if (!chartDiv.querySelector('.ma-cross-overlay')) {
                renderCandleCrossOverlay();
            }
            renderSyncedHoverOverlay('candle-chart', dataPointIndex);
            renderSyncedHoverOverlay('volume-chart', dataPointIndex);
            renderSyncedHoverOverlay('macd-chart', dataPointIndex);
        };

        const clearSyncedHover = () => {
            if (syncedHoverIndex === null) return;
            syncedHoverIndex = null;
            clearSyncedHoverOverlay('candle-chart');
            clearSyncedHoverOverlay('volume-chart');
            clearSyncedHoverOverlay('macd-chart');
        };

        const indexFromMouseEvent = (event) => {
            if (!event || typeof event.clientX !== 'number') return -1;
            const rect = chartDiv.getBoundingClientRect();
            const plotMetrics = getPlotMetrics(chartDiv);
            const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left - plotMetrics.left) / plotMetrics.width));
            return Math.round(ratio * Math.max(0, visibleOhlcData.length - 1));
        };

        const renderCandleCrossOverlay = () => {
            chartDiv.style.position = 'relative';
            const oldOverlay = chartDiv.querySelector('.ma-cross-overlay');
            if (oldOverlay) oldOverlay.remove();

            const visibleSpan = Math.max(1, visibleEnd - visibleStart);
            const visibleMarkers = candleCrossMarkers.filter((marker) => (
                marker.index >= visibleStart && marker.index <= visibleEnd
            ));

            if (!visibleMarkers.length) return;

            const overlay = document.createElement('div');
            overlay.className = 'ma-cross-overlay';
            const plotMetrics = getPlotMetrics(chartDiv);
            Object.assign(overlay.style, {
                position: 'absolute',
                top: '34px',
                bottom: '30px',
                left: `${plotMetrics.left}px`,
                right: `${plotMetrics.right}px`,
                pointerEvents: 'none',
                zIndex: '12'
            });

            const visibleLows = visibleOhlcData.map((d) => d.low).filter((v) => Number.isFinite(v));
            const visibleHighs = visibleOhlcData.map((d) => d.high).filter((v) => Number.isFinite(v));
            const priceMin = visibleLows.length ? Math.min(...visibleLows) : 0;
            const priceMax = visibleHighs.length ? Math.max(...visibleHighs) : 1;
            const priceRange = Math.max(1e-9, priceMax - priceMin);
            const priceToTopPercent = (price) => ((priceMax - price) / priceRange) * 100;

            visibleMarkers.forEach((marker) => {
                const xPercent = ((marker.index - visibleStart) / visibleSpan) * 100;
                const localIdx = marker.index - visibleStart;
                const candle = visibleOhlcData[localIdx];
                if (!candle) return;
                const tag = document.createElement('span');
                tag.textContent = marker.text;
                Object.assign(tag.style, {
                    position: 'absolute',
                    left: `${xPercent}%`,
                    transform: 'translateX(-50%)',
                    whiteSpace: 'nowrap',
                    padding: '1px 4px',
                    border: `1px solid ${marker.color}40`,
                    borderRadius: '4px',
                    background: marker.background,
                    color: marker.color,
                    fontSize: '9px',
                    fontWeight: '700',
                    boxShadow: 'none'
                });
                const anchorPrice = marker.isGolden ? candle.low : candle.high;
                const topPct = priceToTopPercent(anchorPrice);
                if (marker.isGolden) {
                    tag.style.top = `${Math.min(97, topPct + 7 + marker.lane * 2)}%`;
                    tag.style.color = '#dc2626';
                    tag.style.border = '1px solid rgba(220, 38, 38, 0.35)';
                    tag.style.background = 'rgba(220, 38, 38, 0.08)';
                } else {
                    tag.style.top = `${Math.max(2, topPct - 13 - marker.lane * 2)}%`;
                    tag.style.color = '#2563eb';
                    tag.style.border = '1px solid rgba(37, 99, 235, 0.35)';
                    tag.style.background = 'rgba(37, 99, 235, 0.08)';
                }
                overlay.appendChild(tag);
            });

            chartDiv.appendChild(overlay);
        };

        const renderCandleBackgroundOverlay = () => {
            chartDiv.style.position = 'relative';
            const oldBg = chartDiv.querySelector('.candle-bg-overlay');
            if (oldBg) oldBg.remove();
            if (!macdBackgroundBands.length) return;

            const overlay = document.createElement('div');
            overlay.className = 'candle-bg-overlay';
            const plotMetrics = getPlotMetrics(chartDiv);
            Object.assign(overlay.style, {
                position: 'absolute',
                top: '34px',
                bottom: '30px',
                left: `${plotMetrics.left}px`,
                right: `${plotMetrics.right}px`,
                pointerEvents: 'none',
                zIndex: '1'
            });

            const visibleSpan = Math.max(1, visibleEnd - visibleStart);
            const dateToIndex = {};
            sourceOhlcData.forEach((d, i) => { dateToIndex[formatDate(d.date)] = i; });

            macdBackgroundBands.forEach((band) => {
                const fromIdx = dateToIndex[band.x];
                const toIdx = dateToIndex[band.x2];
                if (fromIdx == null || toIdx == null) return;
                const start = Math.max(visibleStart, Math.min(fromIdx, toIdx));
                const end = Math.min(visibleEnd, Math.max(fromIdx, toIdx));
                if (end < start) return;
                const leftPct = ((start - visibleStart) / visibleSpan) * 100;
                const rightPct = ((end - visibleStart) / visibleSpan) * 100;
                const segment = document.createElement('div');
                Object.assign(segment.style, {
                    position: 'absolute',
                    left: `${leftPct}%`,
                    width: `${Math.max(0.8, rightPct - leftPct)}%`,
                    top: '0',
                    bottom: '0',
                    background: band.fillColor === '#fecaca'
                        ? 'rgba(254, 202, 202, 0.38)'
                        : 'rgba(191, 219, 254, 0.38)'
                });
                overlay.appendChild(segment);
            });

            chartDiv.appendChild(overlay);
        };

        // 1. Candlestick Chart Options
        const candleOptions = {
            series: [
                {
                    name: '캔들스틱',
                    type: 'candlestick',
                    data: candleSeriesData
                },
                {
                    name: '5일선',
                    type: 'line',
                    data: ma5SeriesData
                },
                {
                    name: '10일선',
                    type: 'line',
                    data: ma10SeriesData
                },
                {
                    name: '20일선',
                    type: 'line',
                    data: ma20SeriesData
                },
                {
                    name: '60일선',
                    type: 'line',
                    data: ma60SeriesData
                },
                {
                    name: '120일선',
                    type: 'line',
                    data: ma120SeriesData
                },
                {
                    name: '240일선',
                    type: 'line',
                    data: ma240SeriesData
                }
            ],
            chart: {
                id: 'candle-chart',
                group: chartGroupId,
                height: 320,
                type: 'line',
                events: {
                    mouseMove: function(event, chartContext, opts) {
                        const localIndex = opts?.dataPointIndex >= 0
                            ? opts.dataPointIndex
                            : indexFromMouseEvent(event);
                        const pointIndex = localIndex >= 0 ? visibleStart + localIndex : -1;
                        syncSubChartsByIndex(pointIndex);
                    },
                    mouseLeave: function() {
                        clearSyncedHover();
                    }
                },
                zoom: {
                    enabled: true,
                    type: 'x',
                    autoScaleYaxis: true,
                    allowMouseWheelZoom: false
                },
                toolbar: {
                    show: false,
                    autoSelected: 'pan',
                    tools: {
                        download: false,
                        selection: false,
                        zoom: false,
                        zoomin: false,
                        zoomout: false,
                        pan: true,
                        reset: false
                    }
                },
                animations: {
                    enabled: false
                },
                fontFamily: 'Outfit, Inter, sans-serif'
            },
            plotOptions: {
                candlestick: {
                    colors: {
                        upward: '#dc2626',   // 양봉 (Red)
                        downward: '#2563eb'  // 음봉 (Blue)
                    },
                    wick: {
                        useFillColor: true
                    }
                }
            },
            stroke: {
                width: [1, 1.5, 1.5, 1.5, 2, 2.2, 2.5],
                curve: 'smooth'
            },
            colors: [
                '#808080', // Candle base outline placeholder color
                '#eab308', // MA5: Gold
                '#f97316', // MA10: Orange
                '#ec4899', // MA20: Pink
                '#10b981', // MA60: Green
                '#8b5cf6', // MA120: Purple
                '#64748b'  // MA240: Slate
            ],
            xaxis: {
                type: 'category',
                labels: {
                    show: false // Hide X-axis labels to avoid duplication
                },
                crosshairs: sharedCrosshair,
                axisBorder: { show: false },
                axisTicks: { show: false },
                tooltip: { enabled: false }
            },
            yaxis: {
                labels: {
                    minWidth: 80,
                    formatter: function(val) {
                        const isUS = !/^[0-9]+$/.test(stockCodeBadge.textContent);
                        return isUS ? '$' + val.toFixed(2) : val.toLocaleString() + '원';
                    },
                    style: {
                        colors: '#64748b',
                        fontSize: '11px',
                        fontWeight: 500
                    }
                }
            },
            tooltip: {
                shared: true,
                intersect: false,
                custom: function({ seriesIndex, dataPointIndex, w }) {
                    const ohlc = w.config.series[0].data[dataPointIndex];
                    if (!ohlc) return '';
                    
                    const date = ohlc.x;
                    const [open, high, low, close] = ohlc.y;
                    
                    const isUS = !/^[0-9]+$/.test(stockCodeBadge.textContent);
                    const formatPrice = (p) => isUS ? '$' + p.toFixed(2) : p.toLocaleString() + '원';
                    
                    let html = `<div class="apexcharts-custom-tooltip" style="padding: 10px; font-family: 'Outfit'; font-size: 12px; background: rgba(255,255,255,0.95); border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);">`;
                    html += `<div style="font-weight: 700; color: #1e293b; margin-bottom: 6px;">📅 날짜: ${date}</div>`;
                    html += `<div style="display: grid; grid-template-columns: auto auto; gap: 4px 15px; color: #475569;">`;
                    html += `<span>시가:</span><span style="font-weight:600; text-align:right;">${formatPrice(open)}</span>`;
                    html += `<span>고가:</span><span style="font-weight:600; text-align:right; color:#dc2626;">${formatPrice(high)}</span>`;
                    html += `<span>저가:</span><span style="font-weight:600; text-align:right; color:#2563eb;">${formatPrice(low)}</span>`;
                    html += `<span>종가:</span><span style="font-weight:600; text-align:right; color:#1e293b;">${formatPrice(close)}</span>`;
                    
                    for (let s = 1; s < w.config.series.length; s++) {
                        const val = w.config.series[s].data[dataPointIndex].y;
                        if (val !== null) {
                            html += `<span>${w.config.series[s].name}:</span><span style="font-weight:600; text-align:right; color:${w.config.colors[s]};">${formatPrice(val)}</span>`;
                        }
                    }
                    html += `</div></div>`;
                    return html;
                }
            },
            legend: {
                position: 'top',
                horizontalAlign: 'center',
                labels: {
                    colors: '#475569'
                }
            },
            annotations: {
                position: 'back',
                xaxis: candleBackgroundBands
            }
        };

        // 2. Volume Chart Options
        const volumeOptions = {
            series: [
                {
                    name: '거래량',
                    data: volumeSeriesData
                }
            ],
            annotations: {
                xaxis: []
            },
            chart: {
                id: 'volume-chart',
                group: chartGroupId,
                height: volumeChartHeight,
                type: 'bar',
                zoom: {
                    enabled: true,
                    type: 'x',
                    allowMouseWheelZoom: false
                },
                toolbar: {
                    show: false,
                    autoSelected: 'pan',
                    tools: {
                        download: false,
                        selection: false,
                        zoom: false,
                        zoomin: false,
                        zoomout: false,
                        pan: true,
                        reset: false
                    }
                },
                animations: {
                    enabled: false
                },
                fontFamily: 'Outfit, Inter, sans-serif'
            },
            dataLabels: {
                enabled: false
            },
            plotOptions: {
                bar: {
                    columnWidth: '80%'
                }
            },
            colors: [
                function({ value, seriesIndex, dataPointIndex, w }) {
                    const rawIndex = visibleStart + dataPointIndex;
                    if (rawIndex === 0) return positiveColor;
                    const item = rawOhlcData[rawIndex];
                    const prev = rawOhlcData[rawIndex - 1];
                    if (!item || !prev) return '#808080';
                    return item.volume >= prev.volume ? positiveColor : negativeColor;
                }
            ],
            xaxis: {
                type: 'category',
                labels: {
                    show: false // Hide X-axis labels to avoid duplication
                },
                crosshairs: sharedCrosshair,
                axisBorder: { show: false },
                axisTicks: { show: false },
                tooltip: { enabled: false }
            },
            yaxis: {
                labels: {
                    minWidth: 80,
                    formatter: function(val) {
                        if (val >= 1000000) {
                            return (val / 1000000).toFixed(1) + 'M';
                        } else if (val >= 1000) {
                            return (val / 1000).toFixed(0) + 'K';
                        }
                        return val.toLocaleString();
                    },
                    style: {
                        colors: '#64748b',
                        fontSize: '11px',
                        fontWeight: 500
                    }
                }
            },
            tooltip: {
                shared: true,
                intersect: false,
                custom: function({ seriesIndex, dataPointIndex, w }) {
                    const item = rawOhlcData[visibleStart + dataPointIndex];
                    if (!item) return '';
                    const date = formatDate(item.date);
                    let html = `<div class="apexcharts-custom-tooltip" style="padding: 10px; font-family: 'Outfit'; font-size: 12px; background: rgba(255,255,255,0.95); border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);">`;
                    html += `<div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">📅 날짜: ${date}</div>`;
                    html += `<div style="color: #475569;">거래량: <span style="font-weight:600; color:#1e293b;">${item.volume.toLocaleString()}주</span></div>`;
                    html += `</div>`;
                    return html;
                }
            },
            legend: {
                show: false
            }
        };

        // 3. MACD Chart Options
        const macdOptions = {
            series: [
                {
                    name: 'MACD',
                    type: 'line',
                    data: macdSeriesData
                },
                {
                    name: 'Signal',
                    type: 'line',
                    data: signalSeriesData
                },
                {
                    name: 'Histogram',
                    type: 'bar',
                    data: histogramSeriesData
                }
            ],
            annotations: {
                xaxis: macdBackgroundBands.map((band) => ({ ...band })),
                yaxis: macdZeroLine,
                points: macdCrossAnnotations
            },
            chart: {
                id: 'macd-chart',
                group: chartGroupId,
                height: macdChartHeight,
                type: 'line',
                zoom: {
                    enabled: true,
                    type: 'x',
                    allowMouseWheelZoom: false
                },
                toolbar: {
                    show: false,
                    autoSelected: 'pan',
                    tools: {
                        download: false,
                        selection: false,
                        zoom: false,
                        zoomin: false,
                        zoomout: false,
                        pan: true,
                        reset: false
                    }
                },
                animations: {
                    enabled: false
                },
                fontFamily: 'Outfit, Inter, sans-serif'
            },
            plotOptions: {
                bar: {
                    columnWidth: '80%'
                }
            },
            stroke: {
                width: [1.5, 1.5, 0],
                curve: 'smooth'
            },
            colors: [
                function({ value, seriesIndex, dataPointIndex, w }) {
                    if (seriesIndex === 0) return '#0284c7';
                    if (seriesIndex === 1) return '#f59e0b';
                    return value >= 0 ? '#dc2626' : '#2563eb';
                }
            ],
            xaxis: {
                type: 'category',
                labels: {
                    style: {
                        colors: '#64748b',
                        fontSize: '11px',
                        fontWeight: 500
                    },
                    rotate: -45,
                    rotateAlways: false
                },
                tickAmount: Math.min(10, visibleOhlcData.length),
                crosshairs: sharedCrosshair
            },
            yaxis: {
                labels: {
                    minWidth: 80,
                    formatter: function(val) {
                        return val !== null ? val.toFixed(2) : '';
                    },
                    style: {
                        colors: '#64748b',
                        fontSize: '11px',
                        fontWeight: 500
                    }
                }
            },
            tooltip: {
                shared: true,
                intersect: false,
                custom: function({ seriesIndex, dataPointIndex, w }) {
                    const item = rawOhlcData[visibleStart + dataPointIndex];
                    if (!item) return '';
                    const date = formatDate(item.date);
                    const macdVal = macdSeriesData[dataPointIndex].y;
                    const signalVal = signalSeriesData[dataPointIndex].y;
                    const histVal = histogramSeriesData[dataPointIndex].y;
                    
                    let html = `<div class="apexcharts-custom-tooltip" style="padding: 10px; font-family: 'Outfit'; font-size: 12px; background: rgba(255,255,255,0.95); border: 1px solid rgba(0,0,0,0.1); border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.08);">`;
                    html += `<div style="font-weight: 700; color: #1e293b; margin-bottom: 6px;">📅 날짜: ${date}</div>`;
                    html += `<div style="display: grid; grid-template-columns: auto auto; gap: 4px 15px; color: #475569;">`;
                    if (macdVal !== null) {
                        html += `<span>MACD:</span><span style="font-weight:600; text-align:right; color:#0284c7;">${macdVal.toFixed(2)}</span>`;
                    }
                    if (signalVal !== null) {
                        html += `<span>Signal:</span><span style="font-weight:600; text-align:right; color:#f59e0b;">${signalVal.toFixed(2)}</span>`;
                    }
                    if (histVal !== null) {
                        const histColor = histVal >= 0 ? '#dc2626' : '#2563eb';
                        html += `<span>Histogram:</span><span style="font-weight:600; text-align:right; color:${histColor};">${histVal.toFixed(2)}</span>`;
                    }
                    html += `</div></div>`;
                    return html;
                }
            },
            legend: {
                position: 'top',
                horizontalAlign: 'center',
                labels: {
                    colors: '#475569'
                }
            }
        };

        const isKoreanStock = /^[0-9]{6}$/.test(stockCodeBadge.textContent || '');
        const foreignRatioMap = {};
        rawForeignRatioData.forEach((r) => { foreignRatioMap[r.date] = r.ratio; });
        const foreignSeriesData = isKoreanStock ? visibleOhlcData.map((item) => ({
            x: formatDate(item.date),
            y: Object.prototype.hasOwnProperty.call(foreignRatioMap, item.date) ? foreignRatioMap[item.date] : null
        })) : [];

        const foreignOptions = {
            series: [{ name: '외국인 비율(%)', data: foreignSeriesData }],
            chart: {
                id: 'foreign-chart',
                group: chartGroupId,
                height: foreignChartHeight,
                type: 'line',
                zoom: { enabled: true, type: 'x', allowMouseWheelZoom: false },
                toolbar: { show: false },
                animations: { enabled: false },
                fontFamily: 'Outfit, Inter, sans-serif'
            },
            stroke: { width: 1.8, curve: 'smooth' },
            colors: ['#7c3aed'],
            xaxis: { type: 'category', labels: { show: false }, crosshairs: sharedCrosshair },
            yaxis: {
                labels: {
                    minWidth: 80,
                    formatter: (v) => (v == null ? '' : `${v.toFixed(2)}%`),
                    style: { colors: '#64748b', fontSize: '11px', fontWeight: 500 }
                }
            },
            tooltip: { shared: false, intersect: false },
            legend: { show: true, position: 'top', labels: { colors: '#475569' } }
        };

        // Render All Synchronized Charts

        candleChartInstance = new ApexCharts(document.getElementById('candle-chart'), candleOptions);
        Promise.resolve(candleChartInstance.render()).then(() => {
            window.setTimeout(renderCandleBackgroundOverlay, 0);
            window.setTimeout(renderCandleCrossOverlay, 0);
            window.setTimeout(renderCandleBackgroundOverlay, 250);
            window.setTimeout(renderCandleCrossOverlay, 250);
        });

        volumeChartInstance = new ApexCharts(document.getElementById('volume-chart'), volumeOptions);
        Promise.resolve(volumeChartInstance.render()).then(() => {
            const volumeDiv = document.getElementById('volume-chart');
            volumeDiv?.addEventListener('mousemove', (ev) => {
                const rect = volumeDiv.getBoundingClientRect();
                const plotMetrics = getPlotMetrics(volumeDiv);
                const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left - plotMetrics.left) / plotMetrics.width));
                const localIndex = Math.round(ratio * Math.max(0, visibleOhlcData.length - 1));
                syncSubChartsByIndex(visibleStart + localIndex);
            });
            volumeDiv?.addEventListener('mouseleave', clearSyncedHover);
        });

        macdChartInstance = new ApexCharts(document.getElementById('macd-chart'), macdOptions);
        Promise.resolve(macdChartInstance.render()).then(() => {
            const macdDiv = document.getElementById('macd-chart');
            macdDiv?.addEventListener('mousemove', (ev) => {
                const rect = macdDiv.getBoundingClientRect();
                const plotMetrics = getPlotMetrics(macdDiv);
                const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left - plotMetrics.left) / plotMetrics.width));
                const localIndex = Math.round(ratio * Math.max(0, visibleOhlcData.length - 1));
                syncSubChartsByIndex(visibleStart + localIndex);
            });
            macdDiv?.addEventListener('mouseleave', clearSyncedHover);
        });

        const foreignDiv = document.getElementById('foreign-chart');
        if (foreignDiv) {
            if (isKoreanStock) {
                foreignDiv.style.display = '';
                foreignChartInstance = new ApexCharts(foreignDiv, foreignOptions);
                Promise.resolve(foreignChartInstance.render()).then(() => {
                    foreignDiv?.addEventListener('mousemove', (ev) => {
                        const rect = foreignDiv.getBoundingClientRect();
                        const plotMetrics = getPlotMetrics(foreignDiv);
                        const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left - plotMetrics.left) / plotMetrics.width));
                        const localIndex = Math.round(ratio * Math.max(0, visibleOhlcData.length - 1));
                        syncSubChartsByIndex(visibleStart + localIndex);
                    });
                    foreignDiv?.addEventListener('mouseleave', clearSyncedHover);
                });
            } else {
                foreignDiv.style.display = 'none';
            }
        }

        chartDiv.onmousedown = (ev) => {
            candleDragState = {
                startX: ev.clientX,
                startOffset: candleWindowOffset,
                visibleCount: visibleOhlcData.length,
                totalCount: sourceOhlcData.length
            };
        };
        window.onmouseup = () => {
            candleDragState = null;
        };
        window.onmousemove = (ev) => {
            if (!candleDragState) return;
            const dx = ev.clientX - candleDragState.startX;
            const pxPerBar = Math.max(4, chartDiv.clientWidth / Math.max(1, candleDragState.visibleCount));
            const movedBars = Math.round(dx / pxPerBar);
            const maxOffset = Math.max(0, candleDragState.totalCount - daysToDisplay);
            const nextOffset = Math.max(0, Math.min(maxOffset, candleDragState.startOffset - movedBars));
            if (nextOffset !== candleWindowOffset) {
                candleWindowOffset = nextOffset;
                renderCandleChart();
            }
        };
    }

    // 10. Render Peer Badges
    function renderPeersList(peers, benchmark = null) {
        peersListContainer.innerHTML = '';
        const benchmarkName = benchmark?.name || sectorBenchmarkLabel || '업종지수';
        const benchmarkCode = benchmark?.code || benchmark?.symbol || '';
        const benchmarkSource = benchmark?.source || '업종 벤치마크';

        if (sectorBenchmarkDesc) {
            const codeText = benchmarkCode ? ` (${benchmarkCode})` : '';
            sectorBenchmarkDesc.textContent = `${benchmarkName}${codeText}를 해당 종목의 업종 평균(업종지수) 비교 기준으로 사용합니다. 예: 삼성전자는 KRX 전기전자 업종 기준으로 비교합니다. 기준 출처: ${benchmarkSource}.`;
        }

        const benchmarkSpan = document.createElement('span');
        benchmarkSpan.className = 'peer-tag benchmark-tag';
        benchmarkSpan.textContent = benchmarkCode ? `${benchmarkName} (${benchmarkCode})` : benchmarkName;
        peersListContainer.appendChild(benchmarkSpan);

        return;
    }

    // 11. Chart Period Selectors Click Event
    periodButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            periodButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const months = parseInt(btn.getAttribute('data-months'));
            renderChart(months);
        });
    });

    // 11B. Candlestick Chart Duration Control listeners
    const candleDaysInput = document.getElementById('candle-days-input');
    const updateCandleBtn = document.getElementById('update-candle-btn');
    const timeframeButtons = document.querySelectorAll('.timeframe-btn');
    if (updateCandleBtn) {
        updateCandleBtn.addEventListener('click', () => {
            candleWindowOffset = 0;
            renderCandleChart();
        });
    }
    if (candleDaysInput) {
        candleDaysInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                candleWindowOffset = 0;
                renderCandleChart();
            }
        });
    }

    timeframeButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
            const tf = btn.getAttribute('data-timeframe') || 'day';
            candleTimeframe = tf;
            candleWindowOffset = 0;
            timeframeButtons.forEach((b) => b.classList.remove('active'));
            btn.classList.add('active');
            renderCandleChart();
        });
    });

    // 12. Render Interactive Comparative Chart
    function renderChart(months) {
        if (!rawChartData || !rawChartData.dates.length) return;
        
        // A. Calculate Slicing Indexes
        let tradingDays = 250; // default to 1 year
        if (months === 6) tradingDays = 120;
        else if (months === 3) tradingDays = 60;
        else if (months === 1) tradingDays = 20;
        
        const len = rawChartData.dates.length;
        const startIdx = Math.max(0, len - tradingDays);
        
        const datesSlice = rawChartData.dates.slice(startIdx);
        const stockSlice = rawChartData.stock.slice(startIdx);
        const marketSlice = rawChartData.market.slice(startIdx);
        const sectorSlice = rawChartData.sector.slice(startIdx);
        
        // B. Re-normalize to 100% on the start date of this sub-period
        const stockBase = stockSlice[0];
        const marketBase = marketSlice[0];
        const sectorBase = sectorSlice[0];
        
        const normStock = stockSlice.map(v => stockBase ? (v / stockBase) * 100 : 100);
        const normMarket = marketSlice.map(v => marketBase ? (v / marketBase) * 100 : 100);
        const normSector = sectorSlice.map(v => sectorBase ? (v / sectorBase) * 100 : 100);
        
        // C. Clean and recreate Chart canvas
        const ctx = document.getElementById('relative-chart').getContext('2d');
        
        if (relativeChart) {
            relativeChart.destroy();
        }
        
        // D. Create beautiful gradient objects for lines
        // E. Chart.js Config
        relativeChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: datesSlice,
                datasets: [
                    {
                        label: '종목 (Stock)',
                        data: normStock,
                        borderColor: '#111827',
                        borderWidth: 2.5,
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.15,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointHoverBackgroundColor: '#111827',
                        pointHoverBorderColor: '#ffffff',
                        pointHoverBorderWidth: 1.5
                    },
                    {
                        label: `지수 (${benchmarkSymbol})`,
                        data: normMarket,
                        borderColor: '#dc2626',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBackgroundColor: '#dc2626',
                        pointHoverBorderColor: '#ffffff',
                        pointHoverBorderWidth: 1.5
                    },
                    {
                        label: `업종지수 (${sectorBenchmarkLabel})`,
                        data: normSector,
                        borderColor: '#2563eb',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.15,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBackgroundColor: '#2563eb',
                        pointHoverBorderColor: '#ffffff',
                        pointHoverBorderWidth: 1.5
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#475569',
                            font: {
                                family: 'Inter',
                                size: 11
                            },
                            boxWidth: 12,
                            boxHeight: 6,
                            padding: 15
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(255, 255, 255, 0.98)',
                        titleColor: '#0f172a',
                        bodyColor: '#334155',
                        borderColor: 'rgba(0, 0, 0, 0.08)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: {
                            family: 'Outfit',
                            weight: '600'
                        },
                        bodyFont: {
                            family: 'Inter'
                        },
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    label += `${context.parsed.y.toFixed(2)}%`;
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(0, 0, 0, 0.04)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#64748b',
                            font: {
                                size: 10,
                                family: 'Outfit'
                            },
                            maxRotation: 0,
                            autoSkip: true,
                            autoSkipPadding: 40
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(0, 0, 0, 0.04)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#64748b',
                            font: {
                                size: 10,
                                family: 'Outfit'
                            },
                            callback: function(value) {
                                return value.toFixed(0) + '%';
                            }
                        }
                    }
                }
            }
        });
    }
});
