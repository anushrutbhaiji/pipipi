async function previewReport(type) {
    currentReportType = type;
    const date = document.getElementById('rep_date').value;
    const range = document.getElementById('rep_range').value;
    
    let grouped = 'true'; 
    const params = new URLSearchParams({ report_type: type, date: date, time_range: range, grouped: grouped });
    
    try {
        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        let data = await res.json();
        
        const container = document.getElementById('reportPreviewContainer');
        const thead = document.getElementById('reportHead');
        const tbody = document.getElementById('reportBody');
        
        document.getElementById('reportTitle').innerText = (type === 'production' ? '📊 Production Summary' : '🚚 Dispatch Summary');
        container.style.display = 'block';
        tbody.innerHTML = '';

        if(data.length > 0 && data[0].count === undefined) {
            let groups = {};
            data.forEach(item => {
                let pressure = item.pressure_class || '-';
                let stdWt = item.weight_g || 0;
                let key = `${item.pipe_name}_${item.size}_${item.color}_${pressure}_${stdWt}`;
                if(!groups[key]) {
                    groups[key] = { 
                        pipe_name: item.pipe_name, size: item.size, color: item.color, 
                        pressure_class: pressure, weight_g: stdWt, count: 0, total_weight: 0 
                    };
                }
                groups[key].count += 1;
                groups[key].total_weight += (item.weight_g || 0);
            });
            data = Object.values(groups);
        }

        thead.innerHTML = `<tr><th>Brand</th><th>Size</th><th>Color</th><th>Pressure</th><th style="text-align:right;">Std Wt (Kg)</th><th style="text-align:center;">Quantity</th><th style="text-align:right;">Total Wt (Kg)</th><th style="text-align:center;">Action</th></tr>`;
        
        let grandTotalQty = 0; let grandTotalWt = 0;
        
        if(data.length === 0) { tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;">No records found.</td></tr>`; return; }
        
        data.forEach(r => {
            let qty = r.count || 0;
            let wt = r.total_weight || 0;
            
            grandTotalQty += qty; 
            grandTotalWt += wt; 
            
            let pressureDisplay = r.pressure_class && r.pressure_class !== '-' ? `<span style="color:#ef4444; font-weight:600;">${r.pressure_class}</span>` : '<span style="color:#cbd5e1;">-</span>';
            
            let exactWt = r.weight_g || r.avg_weight || (qty > 0 ? (wt/qty) : 0);
            let stdWtDisplay = parseFloat(exactWt).toFixed(3);
            
            let safePressure = r.pressure_class === '-' ? '' : (r.pressure_class || '');
            let safeWeight = exactWt || '';

            let actionBtn = `<button class="btn" style="padding:5px 10px; font-size:0.8rem; width:auto; background:#cbd5e1; color:#333;" onclick="drillDown('${r.pipe_name}', '${r.size}', '${r.color}', '${safePressure}', '${safeWeight}')">Ids</button>`;

            tbody.innerHTML += `<tr>
                <td style="font-weight:bold;">${r.pipe_name}</td>
                <td>${r.size}</td>
                <td>${r.color}</td>
                <td>${pressureDisplay}</td>
                <td style="text-align:right; color:#64748b; font-weight:500;">${stdWtDisplay}</td>
                <td style="text-align:center; font-weight:bold; font-size:1.1rem;">${qty}</td>
                <td style="text-align:right;">${(wt).toFixed(3)}</td>
                <td style="text-align:center;">${actionBtn}</td>
            </tr>`;
        });
        
        tbody.innerHTML += `<tr style="background:#f1f5f9; font-weight:bold; border-top:2px solid #cbd5e1;"><td colspan="5" style="text-align:right;">GRAND TOTAL:</td><td style="text-align:center; font-size:1.1rem; color:#2563eb;">${grandTotalQty}</td><td style="text-align:right; color:#ef4444;">${(grandTotalWt).toFixed(3)}</td><td></td></tr>`;
        
    } catch(e) { console.error(e); alert("Error loading report data."); }
}

async function fetchShipmentHistory() {
    const container = document.getElementById('tab-shipments');
    
    if(container.innerHTML.trim() !== '') return;

    container.innerHTML = `
        <div class="filter-bar" style="margin-bottom: 1rem; display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
            <input type="text" id="shipmentSearch" onkeyup="filterShipments()" 
                   placeholder="🔍 Search ID, Challan..." 
                   style="flex: 1; min-width: 150px; padding: 10px; border: 1px solid #ccc; border-radius: 6px;">
            <input type="date" id="historyDateFilter" onchange="filterHistoryByDate('date')" style="padding: 9px; border: 1px solid #ccc; border-radius: 6px;">
            <button class="btn" style="width:auto; padding:9px 12px; font-size:0.85rem; background:#64748b;" onclick="filterHistoryByDate('3')">3 Days</button>
            <button class="btn" style="width:auto; padding:9px 12px; font-size:0.85rem; background:#64748b;" onclick="filterHistoryByDate('7')">Week</button>
            <button class="btn" style="width:auto; padding:9px 12px; font-size:0.85rem; background:#64748b;" onclick="filterHistoryByDate('30')">Month</button>
            <button class="btn" style="width:auto; padding:9px 12px; font-size:0.85rem; background:#ef4444;" onclick="filterHistoryByDate('all')">Clear</button>
            <div class="d-flex justify-content-end align-items-center mb-3 pt-3 pb-2 px-3 bg-white border-bottom shadow-sm rounded">
                <a href="/admin/returns" class="btn btn-outline-danger shadow-sm d-flex align-items-center gap-2"><span>📜</span><span>View Return Vouchers</span></a>
            </div>
            <div style="margin-left:auto; background:#eff6ff; color:#1d4ed8; padding:8px 15px; border-radius:20px; font-weight:bold; border:1px solid #bfdbfe; white-space:nowrap;">
                Total Pipes: <span id="totalVisiblePipes" style="font-size:1.1rem;">0</span>
            </div>
        </div>
        <div class="data-table-container">
            <div class="table-responsive">
                <table id="shipmentHistoryTable"><thead></thead><tbody><tr><td colspan="6" style="text-align:center;">Loading...</td></tr></tbody></table>
            </div>
        </div>`;

    const thead = container.querySelector('thead');
    const tbody = container.querySelector('tbody');

    thead.innerHTML = `<tr><th>ID</th><th>Challan No.</th><th>Vehicle</th><th>Date</th><th class="text-center">Pipes</th><th class="text-end">Weight (kg)</th></tr>`;
    
    try {
        const res = await fetch('/api/admin/shipments', { headers: AUTH_HEADER });
        let data = await res.json();
        data = data.filter(shipment => shipment.total_pipes > 0);
        tbody.innerHTML = '';
        
        if(data.length === 0) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No shipment history found.</td></tr>'; return; }
        
        data.forEach(shipment => {
            const date = new Date(shipment.created_at).toLocaleString();
            tbody.innerHTML += `
                <tr data-date="${shipment.created_at}">
                    <td>#${shipment.id}</td>
                    <td><a href="/shipment/${shipment.id}" target="_blank"><strong>${shipment.challan_no || 'N/A'}</strong></a></td>
                    <td>${shipment.vehicle_no || 'N/A'}</td>
                    <td>${date}</td>
                    <td class="text-center">${shipment.total_pipes}</td>
                    <td class="text-end">${(shipment.total_weight).toFixed(2)}</td>
                </tr>`;
        });
        recalcShipmentTotal();
    } catch(e) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:red;">Failed to load history.</td></tr>'; }
}

function filterShipments() {
    const input = document.getElementById('shipmentSearch');
    const filter = input.value.toLowerCase();
    const table = document.getElementById('shipmentHistoryTable');
    const tr = table.getElementsByTagName('tr');

    for (let i = 1; i < tr.length; i++) {
        const rowContent = tr[i].textContent || tr[i].innerText;
        if (rowContent.toLowerCase().indexOf(filter) > -1) {
            tr[i].style.display = "";
        } else {
            tr[i].style.display = "none";
        }
    }
    recalcShipmentTotal();
}

function filterHistoryByDate(type) {
    document.getElementById('shipmentSearch').value = '';
    const rows = document.querySelectorAll('#shipmentHistoryTable tbody tr');
    const today = new Date(); today.setHours(23, 59, 59, 999);

    let startDate = new Date();
    let isSpecificDay = false;

    if (type === 'all') {
        document.getElementById('historyDateFilter').value = ''; 
        rows.forEach(row => row.style.display = ''); 
        recalcShipmentTotal();
        return;
    } 
    else if (type === 'date') {
        const val = document.getElementById('historyDateFilter').value;
        if (!val) return;
        startDate = new Date(val);
        isSpecificDay = true;
    } 
    else {
        const days = parseInt(type);
        startDate = new Date(); 
        startDate.setDate(today.getDate() - days);
        startDate.setHours(0, 0, 0, 0); 
        document.getElementById('historyDateFilter').value = ''; 
    }

    rows.forEach(row => {
        const dateStr = row.getAttribute('data-date');
        if (!dateStr) return; 
        
        const rowDate = new Date(dateStr);
        let shouldShow = false;

        if (isSpecificDay) {
            shouldShow = rowDate.toDateString() === startDate.toDateString();
        } else {
            shouldShow = rowDate >= startDate;
        }
        row.style.display = shouldShow ? '' : 'none';
    });
    recalcShipmentTotal();
}

function recalcShipmentTotal() {
    const rows = document.querySelectorAll('#shipmentHistoryTable tbody tr');
    let total = 0;
    
    rows.forEach(row => {
        if (row.style.display !== 'none') {
            const cells = row.getElementsByTagName('td');
            if (cells.length > 4) {
                total += parseInt(cells[4].innerText) || 0;
            }
        }
    });
    document.getElementById('totalVisiblePipes').innerText = total;
}

function downloadCSV() { downloadInventoryCSV(); }
function printReportPDF() { const content = document.getElementById('reportTable').outerHTML; printContent(content, document.getElementById('reportTitle').innerText); }