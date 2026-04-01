document.addEventListener("DOMContentLoaded", () => {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('f_start').value = '';
    document.getElementById('rep_date').value = today;

    if(sessionStorage.getItem('admin_token')) {
        authenticate(true);
    }
});

function checkUrlFilters() {
    const params = new URLSearchParams(window.location.search);
    if(params.has('brand')) {
        showTab('inventory');
        document.getElementById('f_name').value = params.get('brand') || '';
        document.getElementById('f_size').value = params.get('size') || '';
        document.getElementById('f_color').value = params.get('color') || '';
        document.getElementById('f_status').value = 'stock';
        fetchInventory();
    } else {
        fetchInventory();
    }
}

function startLiveUpdates() {
    if(pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(async () => {
        if(document.hidden) return; 
        try {
            const res = await fetch('/api/stats_summary', { headers: AUTH_HEADER });
            if(res.ok) {
                const data = await res.json();
                updateDashboardUI(data);
            }
        } catch(e) { console.log("Silent refresh failed"); }
    }, 10000); 
}

function showTab(tabId) {
    document.querySelectorAll('.section').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tabId).classList.add('active');

    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const activeBtn = document.querySelector(`.tab-btn[onclick="showTab('${tabId}')"]`);
    if(activeBtn) activeBtn.classList.add('active');

    const header = document.querySelector('.dashboard-header');
    const kpis = document.querySelector('.kpi-row');
    
    if (tabId === 'stock-table') {
        if(header) header.style.display = 'none';
        if(kpis) kpis.style.display = 'none';
    } else {
        if(header) header.style.display = ''; 
        if(kpis) kpis.style.display = ''; 
    }

    if (tabId === 'shipments') fetchShipmentHistory();
}

function switchStockView(mode) {
    currentStockView = mode;
    document.getElementById('btn-view-brand').classList.remove('active');
    document.getElementById('btn-view-size').classList.remove('active');
    document.getElementById('btn-view-' + mode).classList.add('active');
    
    if(latestStockData.length > 0) {
        updateDashboardUI({
            stock_summary: latestStockData,
            total: document.getElementById('kpi-total').innerText,
            stock: document.getElementById('kpi-stock').innerText,
            dispatched: document.getElementById('kpi-dispatch').innerText,
            production_chart: [] 
        });
    }
}

function updateDashboardUI(data) {
    if (data.stock_summary) {
        data.stock_summary = data.stock_summary.filter(item => item.stock > 0);
    }

    document.getElementById('kpi-total').innerText = data.total;
    document.getElementById('kpi-stock').innerText = data.stock;
    document.getElementById('kpi-dispatch').innerText = data.dispatched;
    
    latestStockData = data.stock_summary;
    renderStockTableTab(latestStockData);
    const container = document.getElementById('visualWarehouse');
    if(container) {
        container.innerHTML = '';
        let groups = {};

        data.stock_summary.forEach(row => {
            let key = '';
            if (currentStockView === 'brand') {
                key = row.pipe_name; 
            } else {
                key = row.size; 
            }
            if(!groups[key]) groups[key] = [];
            groups[key].push(row);
        });

        let sortedKeys = Object.keys(groups);
        
        if(currentStockView === 'size') {
            sortedKeys.sort((a,b) => parseInt(a) - parseInt(b));
        } else {
            sortedKeys.sort();
        }

        for(let groupTitle of sortedKeys) {
            let items = groups[groupTitle];
            if(currentStockView === 'brand') {
                items.sort((a,b) => parseInt(a.size) - parseInt(b.size));
            } else {
                items.sort((a,b) => a.pipe_name.localeCompare(b.pipe_name));
            }

            let displayTitle = (currentStockView === 'brand') ? `🏭 ${groupTitle}` : `📏 ${groupTitle}`;
            let shelfHtml = `<div class="brand-shelf"><div class="brand-title"><span>${displayTitle}</span> <span style="font-size:1.1rem; opacity:0.6;">${items.length} Variants</span></div><div class="pipe-grid">`;
            
            items.forEach(item => {
                let visualSize = 65; 
                let borderColor = item.color.toLowerCase().includes('blue') ? '#2563eb' : '#64748b';
                let isLow = item.stock < 50;
                let glowClass = isLow ? 'low-stock-glow' : '';
                let cardMainText = (currentStockView === 'brand') ? item.size : item.pipe_name;
                let pressureText = item.pressure_class ? item.pressure_class : '';
                let avgWt = item.avg_weight ? parseFloat(item.avg_weight).toFixed(3) : '0.000';
                
                shelfHtml += `
                <div class="pipe-card" onclick="goToInventory('${item.pipe_name}', '${item.size}', '${item.color}', '${item.pressure_class || ''}')">
                    <div class="pipe-visual ${glowClass}" style="width:${visualSize}px; height:${visualSize}px; border-width:6px; border-color:${borderColor}; font-size: 1.5rem;">
                        ${item.stock}
                    </div>
                    <div style="font-weight:700; font-size:1.1rem; color:#334155; line-height: 1.2;">${cardMainText}</div>
                    <div style="font-weight:700; font-size:0.9rem; color:#ef4444; margin: 2px 0;">${pressureText}</div>
                    <div style="font-size:0.9rem; font-weight:700; color:${borderColor};">${item.color}</div>
                    <div style="font-size: 0.75rem; color: #64748b; margin-top: 6px; border-top: 1px solid #e2e8f0; padding-top: 4px;">
                        Avg: <b>${avgWt}</b> kg
                    </div>
                    ${isLow ? '<div style="color:red; font-size:0.8rem; font-weight:bold; margin-top:5px;">⚠️ LOW</div>' : ''}
                </div>`;
            });
            shelfHtml += `</div></div>`;
            container.innerHTML += shelfHtml;
        }
    }

    const dBody = document.getElementById('deadStockBody');
    if (dBody && data.dead_stock) {
        dBody.innerHTML = '';
        if (data.dead_stock.length === 0) {
            dBody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#10b981; font-weight:bold; padding: 20px;">🎉 Great job! No dead stock found.</td></tr>';
        } else {
            data.dead_stock.forEach(row => {
                let pressure = row.pressure_class ? row.pressure_class : '-';
                dBody.innerHTML += `
                    <tr style="background-color: #f8fafc;">
                        <td style="font-weight:bold; color:#334155;">${row.pipe_name}</td>
                        <td>${row.size}</td>
                        <td>${row.color}</td>
                        <td style="font-weight:600; color:#64748b;">${pressure}</td>
                        <td style="text-align:center; font-weight:bold; font-size: 1.1rem; color: #4B576A;">${row.qty}</td>
                        <td style="text-align:right; font-weight:bold; color:#ef4444;">⏳ ${row.days_old} Days</td>
                        <td style="text-align:center;">
                            <a href="javascript:void(0)" 
                               onclick="openDeadStockWindow('${row.pipe_name}', '${row.size}', '${row.color}', '${row.pressure_class || ''}')"
                               style="color: #2563eb; text-decoration: underline; font-weight: 600; font-size: 0.9rem;">
                               View IDs ↗
                            </a>
                        </td>
                    </tr>
                `;
            });
        }
    }
    
    if(data.production_chart && data.production_chart.length > 0) {
        if(window.myChart) window.myChart.destroy();
        const ctx = document.getElementById('prodChart').getContext('2d');
        window.myChart = new Chart(ctx, {
            type: 'line', 
            data: { 
                labels: data.production_chart.map(d => d.day), 
                datasets: [{ 
                    label: 'Production', 
                    data: data.production_chart.map(d => d.count), 
                    borderColor: '#2563eb', 
                    tension: 0.3, 
                    fill: true, 
                    backgroundColor: 'rgba(37,99,235,0.1)' 
                }] 
            }, 
            options: { responsive: true, maintainAspectRatio: false }
        });
    }
    // =========================================================
    // DAY/NIGHT SHIFT: SCROLLABLE, COLORED PULSE GRAPHS
    // =========================================================
    if(data.recent_timestamps && data.recent_timestamps.length > 0) {
        
        let dayLabels = [], dayGaps = [], dayColors = [], dayDetails = [];
        let nightLabels = [], nightGaps = [], nightColors = [], nightDetails = [];
        
        let lastDayTime = null;
        let lastNightTime = null;

        // Helper to convert DB color names to CSS hex colors for the dots
        const getColorHex = (c) => {
            let clr = c ? c.toLowerCase() : '';
            if(clr.includes('blue')) return '#3b82f6';
            if(clr.includes('orange')) return '#f59e0b';
            if(clr.includes('red')) return '#ef4444';
            if(clr.includes('green')) return '#10b981';
            if(clr.includes('yellow')) return '#eab308';
            if(clr.includes('black')) return '#1e293b';
            if(clr.includes('white')) return '#f8fafc';
            return '#94a3b8'; // default gray if unknown
        };

        data.recent_timestamps.forEach(pipe => {
            let date = new Date(pipe.created_at);
            let hour = date.getHours();
            let timeStr = date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            // Prepare detail object for the tooltip
            let details = {
                id: pipe.id,
                name: pipe.pipe_name,
                size: pipe.size,
                weight: pipe.weight_g,
                colorName: pipe.color
            };

            let dotColor = getColorHex(pipe.color);

            if (hour >= 9 && hour < 21) {
                // --- DAY SHIFT ---
                let gap = 0;
                if (lastDayTime) gap = (date - lastDayTime) / 60000;
                
                dayLabels.push(timeStr);
                dayGaps.push(gap.toFixed(1));
                dayColors.push(dotColor);
                dayDetails.push(details);
                lastDayTime = date;
            } else {
                // --- NIGHT SHIFT ---
                let gap = 0;
                if (lastNightTime) gap = (date - lastNightTime) / 60000;
                
                nightLabels.push(timeStr);
                nightGaps.push(gap.toFixed(1));
                nightColors.push(dotColor);
                nightDetails.push(details);
                lastNightTime = date;
            }
        });

        // Stretch the inner canvas wrappers to make it scrollable based on pipe count
        // 35 pixels per pipe dot guarantees comfortable spacing!
        const dayWidth = Math.max(800, dayLabels.length * 35);
        const nightWidth = Math.max(800, nightLabels.length * 35);
        document.getElementById('dayCanvasWrapper').style.width = dayWidth + 'px';
        document.getElementById('nightCanvasWrapper').style.width = nightWidth + 'px';

        // Custom Tooltip Plugin for Chart.js
        const customTooltip = {
            callbacks: {
                title: (ctx) => `Time: ${ctx[0].label}`,
                label: (ctx) => {
                    let idx = ctx.dataIndex;
                    let pipe = ctx.dataset.customData[idx]; // Retrieve our custom details
                    return [
                        `Gap: ${ctx.raw} mins`,
                        `ID: #${pipe.id}`,
                        `Pipe: ${pipe.name} | ${pipe.size}`,
                        `Color: ${pipe.colorName}`,
                        `Weight: ${pipe.weight}Kg`
                    ];
                }
            }
        };

        const pulseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: { 
                y: { beginAtZero: true, title: { display: true, text: 'Gap (Minutes)' } },
                x: { title: { display: true, text: 'Time of Production' } }
            },
            plugins: { tooltip: customTooltip },
            elements: {
                line: { tension: 0.1, borderWidth: 2, borderColor: '#e2e8f0' }, // Light gray linking line
                point: { radius: 6, hoverRadius: 9, borderWidth: 2, borderColor: '#fff' } // Colored dots
            }
        };

        // Render Day Shift
        if(window.dayChart) window.dayChart.destroy();
        window.dayChart = new Chart(document.getElementById('dayShiftChart').getContext('2d'), {
            type: 'line',
            data: {
                labels: dayLabels,
                datasets: [{
                    label: 'Day Shift Pulse',
                    data: dayGaps,
                    pointBackgroundColor: dayColors, // Array of actual pipe colors
                    customData: dayDetails, // Pass the details so the tooltip can read it
                    fill: false
                }]
            },
            options: pulseOptions
        });

        // Render Night Shift
        if(window.nightChart) window.nightChart.destroy();
        window.nightChart = new Chart(document.getElementById('nightShiftChart').getContext('2d'), {
            type: 'line',
            data: {
                labels: nightLabels,
                datasets: [{
                    label: 'Night Shift Pulse',
                    data: nightGaps,
                    pointBackgroundColor: nightColors, // Array of actual pipe colors
                    customData: nightDetails, // Pass the details so the tooltip can read it
                    fill: false
                }]
            },
            options: pulseOptions
        });
    }
}

function renderStockTableTab(dataList) {
    const container = document.getElementById('stock-table-container');
    if(!container) return; 
    
    if(!dataList || dataList.length === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align:center; color:#64748b;">No stock data found.</div>';
        return;
    }

    let groupedBySize = {};
    dataList.forEach(item => {
        let sizeKey = item.size;
        if(!groupedBySize[sizeKey]) groupedBySize[sizeKey] = [];
        groupedBySize[sizeKey].push(item);
    });

    let sortedSizes = Object.keys(groupedBySize).sort((a,b) => parseInt(a) - parseInt(b));
    let fullHtml = '';

    sortedSizes.forEach(sizeKey => {
        let items = groupedBySize[sizeKey];
        items.sort((a,b) => a.pipe_name.localeCompare(b.pipe_name));

        fullHtml += `
        <div style="margin-bottom: 30px; background: #fff; padding: 20px; border-radius: 12px; box-shadow: var(--shadow-sm);">
            <h3 style="color: #334155; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 15px; margin-top:0;">
                📏 Size: ${sizeKey} 
                <span style="font-size: 0.9rem; color: #64748b; font-weight: normal; margin-left: 10px;">(${items.length} Variants)</span>
            </h3>
            <div class="table-responsive">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f8fafc; color: #64748b; text-align: left;">
                            <th style="padding: 12px;">Brand</th>
                            <th style="padding: 12px;">Color</th>
                            <th style="padding: 12px;">Pressure</th>
                            <th style="padding: 12px;">Avg Weight</th>
                            <th style="padding: 12px; text-align: center;">In Stock</th>
                            <th style="padding: 12px; text-align: center;">IDs</th>
                        </tr>
                    </thead>
                    <tbody>`;
        
        items.forEach(row => {
            let pressure = row.pressure_class ? row.pressure_class : ''; 
            let pressureDisplay = pressure ? `<span style="color:#ef4444; font-weight:600;">${pressure}</span>` : '<span style="color:#cbd5e1;">-</span>';
            let avgWt = row.avg_weight ? parseFloat(row.avg_weight).toFixed(3) + ' Kg' : '<span style="color:#cbd5e1;">-</span>';
            let stockStyle = row.stock < 50 ? 'color: #ef4444;' : 'color: #10b981;';
            let rawWeight = row.avg_weight || row.weight_g || '';
            fullHtml += `
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 12px; font-weight: 700; color: #334155;">${row.pipe_name}</td>
                            <td style="padding: 12px;">${row.color}</td>
                            <td style="padding: 12px;">${pressureDisplay}</td>
                            <td style="padding: 12px; color:#64748b;">${avgWt}</td>
                            <td style="padding: 12px; text-align: center; font-size: 1.1rem; font-weight: 800; ${stockStyle}">${row.stock}</td>
                            <td style="padding: 12px; text-align: center;">
                                <a href="javascript:void(0)" 
                                onclick="viewIds('${row.pipe_name}', '${row.size}', '${row.color}', '${row.pressure_class}', '${rawWeight}')"
                                   style="color: #2563eb; text-decoration: underline; font-weight: 600; font-size: 0.9rem;">
                                   View List ↗
                                </a>
                            </td>
                        </tr>`;
        });
        fullHtml += `</tbody></table></div></div>`;
    });
    container.innerHTML = fullHtml;
}

function goToInventory(brand, size, color, pressure) {
    viewIds(brand, size, color, pressure);
}

async function openDeadStockWindow(brand, size, color, pressure) {
    if (typeof showTab === 'function') {
        showTab('inventory');
    }

    isDetailMode = true;
    
    document.getElementById('inv-summary-view').style.display = 'none';
    document.getElementById('inv-detail-view').style.display = 'block';
    document.getElementById('masterTable').style.display = 'table'; 
    document.getElementById('detail-nav-header').style.display = 'flex';
    
    let title = ` Old Stock: ${brand} ${size} ${color}`;
    if (pressure && pressure !== '-' && pressure !== 'null') title += ` (${pressure})`;
    document.getElementById('detail-view-title').innerText = title;
    
    document.getElementById('masterBody').innerHTML = '<tr><td colspan="10" style="text-align:center;">Fetching Old Stock IDs...</td></tr>';

    const params = new URLSearchParams({
        name: brand,
        size: size,
        color: color,
        pressure: pressure || '', 
        status: 'stock',
        dead_stock: 'true', 
        grouped: 'false',
        page: 1,           
        per_page: 1000     
    });

    try {
        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        if (!res.ok) throw new Error("Server error");
        
        const freshData = await res.json();
        renderDetailTable(freshData.items, false);
        
        const paginationEl = document.getElementById('pagination-controls');
        if (paginationEl) paginationEl.style.display = 'none';

    } catch(e) {
        console.error(e);
        document.getElementById('masterBody').innerHTML = '<tr><td colspan="10" style="text-align:center; color:red;">Failed to fetch IDs from server.</td></tr>';
    }
}