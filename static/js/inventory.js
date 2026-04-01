async function fetchInventory(targetPage = 1) {
    currentPage = targetPage; 
    
    const brandVal = document.getElementById('f_name').value;
    const sizeVal = document.getElementById('f_size').value;
    
    const params = new URLSearchParams({
        name: brandVal,
        size: sizeVal,
        color: document.getElementById('f_color').value,
        pressure: document.getElementById('f_pressure').value,
        weight: document.getElementById('f_weight') ? document.getElementById('f_weight').value : '',
        status: document.getElementById('f_status').value,
        date: document.getElementById('f_start').value,
        page: currentPage,    
        per_page: 100         
    });

    let useServerGrouping = (brandVal !== '' || sizeVal !== '');
    if (useServerGrouping) params.append('grouped', 'true');

    const tbodySummary = document.getElementById('invSummaryBody');
    const tbodyDetail = document.getElementById('masterBody');
    
    if (!useServerGrouping) {
         tbodyDetail.innerHTML = '<tr><td colspan="9" style="text-align:center;">Loading Page ' + currentPage + '...</td></tr>';
    } else {
         if(tbodySummary) tbodySummary.innerHTML = '<tr><td colspan="6" style="text-align:center;">Loading...</td></tr>';
    }

    try {
        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        const responseData = await res.json();

        if (!useServerGrouping) {
            currentInventoryData = responseData.items; 
            isDetailMode = false; 
            renderDetailTable(responseData.items, true); 
            updatePaginationUI(responseData.page, responseData.total_pages, responseData.total);
        } else {
            currentInventoryData = responseData; 
            isDetailMode = false; 
            let mode = 'default';
            if (brandVal !== '' && sizeVal === '') mode = 'size_centric';
            else if (sizeVal !== '' && brandVal === '') mode = 'brand_centric';
            
            renderSummaryTable(responseData, mode, true);
            const pagControls = document.getElementById('pagination-controls');
            if (pagControls) {
                pagControls.style.display = 'none';
            }
        }
    } catch(e) { console.error(e); }
}

function updatePaginationUI(page, totalPages, totalRecords) {
    const controls = document.getElementById('pagination-controls');
    if (!controls) return;
    
    controls.style.display = 'flex';
    controls.innerHTML = ''; 

    let info = document.createElement('div');
    info.style.width = '100%';
    info.style.textAlign = 'center';
    info.style.marginBottom = '10px';
    info.style.color = '#64748b';
    info.style.fontSize = '0.85rem';
    info.innerHTML = `Showing page <b>${page}</b> of <b>${totalPages}</b> <span style="margin-left:10px;">(Total: ${totalRecords} pipes)</span>`;
    controls.appendChild(info);

    let prevBtn = document.createElement('button');
    prevBtn.className = 'page-btn';
    prevBtn.innerText = '« Prev';
    prevBtn.disabled = (page <= 1);
    prevBtn.onclick = () => fetchInventory(page - 1);
    controls.appendChild(prevBtn);

    let startPage = Math.max(1, page - 2);
    let endPage = Math.min(totalPages, page + 2);

    if (startPage > 1) {
        controls.appendChild(createPageBtn(1, page));
        if (startPage > 2) {
            let ell = document.createElement('span');
            ell.className = 'page-ellipsis'; ell.innerText = '...';
            controls.appendChild(ell);
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        controls.appendChild(createPageBtn(i, page));
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            let ell = document.createElement('span');
            ell.className = 'page-ellipsis'; ell.innerText = '...';
            controls.appendChild(ell);
        }
        controls.appendChild(createPageBtn(totalPages, page));
    }

    let nextBtn = document.createElement('button');
    nextBtn.className = 'page-btn';
    nextBtn.innerText = 'Next »';
    nextBtn.disabled = (page >= totalPages);
    nextBtn.onclick = () => fetchInventory(page + 1);
    controls.appendChild(nextBtn);
}

function createPageBtn(pageNum, currentPage) {
    let btn = document.createElement('button');
    btn.className = 'page-btn' + (pageNum === currentPage ? ' active' : '');
    btn.innerText = pageNum;
    btn.onclick = () => fetchInventory(pageNum);
    return btn;
}

function changePage(direction) {
    fetchInventory(currentPage + direction);
}

function renderSummaryTable(data, mode) {
    document.getElementById('inv-summary-view').style.display = 'block';
    document.getElementById('inv-detail-view').style.display = 'none';
    
    const thead = document.getElementById('invSummaryHead');
    const tbody = document.getElementById('invSummaryBody');
    tbody.innerHTML = '';

    const brandVal = document.getElementById('f_name').value;
    const sizeVal = document.getElementById('f_size').value;
    const colorVal = document.getElementById('f_color').value;

    let titleParts = [];
    if(brandVal) titleParts.push(brandVal);
    if(sizeVal) titleParts.push(sizeVal);
    if(colorVal) titleParts.push(colorVal);

    const displayTitle = titleParts.length > 0 ? titleParts.join(" • ") : "All Stock";
    const titleEl = document.getElementById('summary-active-filters');
    if(titleEl) titleEl.innerText = displayTitle;

    if(data.length === 0) { 
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No records found.</td></tr>'; 
        return; 
    }

    let groups = {};
    let totalColSpan = 5; 

    if (mode === 'size_centric') {
        thead.innerHTML = `<tr><th>Size</th><th>Color</th><th>Pressure</th><th style="text-align:right;">Std Wt (kg)</th><th style="text-align:center;">Quantity</th><th>Action</th></tr>`;
        totalColSpan = 4; 
    } else if (mode === 'brand_centric') {
        thead.innerHTML = `<tr><th>Brand</th><th>Color</th><th>Pressure</th><th style="text-align:right;">Std Wt (kg)</th><th style="text-align:center;">Quantity</th><th>Action</th></tr>`;
        totalColSpan = 4; 
    } else {
        thead.innerHTML = `<tr><th>Brand</th><th>Size</th><th>Color</th><th>Pressure</th><th style="text-align:right;">Std Wt (kg)</th><th style="text-align:center;">Quantity</th><th>Action</th></tr>`;
        totalColSpan = 5; 
    }

    data.forEach(item => {
        let pressure = item.pressure_class || '-';
        let std_wt = item.weight_g || item.avg_weight || (item.total_weight && item.count ? (item.total_weight / item.count) : 0);

        let key = '';
        if(mode === 'size_centric') key = `${item.size}|${item.color}|${pressure}|${std_wt}`;
        else if(mode === 'brand_centric') key = `${item.pipe_name}|${item.color}|${pressure}|${std_wt}`;
        else key = `${item.pipe_name}|${item.size}|${item.color}|${pressure}|${std_wt}`;

        if(!groups[key]) {
            groups[key] = { 
                brand: item.pipe_name, size: item.size, color: item.color, 
                pressure: pressure, std_weight: std_wt,
                count: 0, weight: 0 
            };
        }
        
        groups[key].count += (item.count !== undefined ? item.count : 1);
        groups[key].weight += (item.total_weight !== undefined ? item.total_weight : (item.weight_g || 0));
    });

    let grandTotalQty = 0;
    let grandTotalWt = 0;
    let colorTotals = {}; 

    Object.values(groups).forEach(g => {
        grandTotalQty += g.count;
        grandTotalWt += g.weight;

        if (!colorTotals[g.color]) {
            colorTotals[g.color] = { count: 0, weight: 0 };
        }
        colorTotals[g.color].count += g.count;
        colorTotals[g.color].weight += g.weight;

        let pressureDisplay = g.pressure !== '-' ? `<span style="color:#ef4444; font-weight:600;">${g.pressure}</span>` : '<span style="color:#cbd5e1;">-</span>';
        let stdWtDisplay = g.std_weight ? parseFloat(g.std_weight).toFixed(3) : '<span style="color:#cbd5e1;">-</span>';
        
        let safePressure = g.pressure === '-' ? '' : g.pressure;
        let safeWeight = g.std_weight || '';

        // Action Buttons
         let actionBtn = `<div style="display:flex; gap:5px; justify-content:center;">
             <button class="btn" style="padding:5px 10px; font-size:0.8rem; background:#cbd5e1; color:#333;" onclick="drillDown('${g.brand}', '${g.size}', '${g.color}', '${safePressure}', '${safeWeight}')">Ids</button>
             <button class="btn" style="padding:5px 10px; font-size:0.8rem; background:rgba(59,130,246,.15); color:#2563eb; border:1px solid rgba(59,130,246,.4);" onclick="openVerify('${g.brand}', '${g.size}', '${g.color}', '${safePressure}', '${safeWeight}')">🔍 Verify</button>
         </div>`;

        let row = '';
        if (mode === 'size_centric') {
            row = `<tr>
                    <td><a href="javascript:void(0)" onclick="drillDown('${g.brand}', '${g.size}', '${g.color}', '${safePressure}', '${safeWeight}')" style="color: #2563eb; font-weight: bold; text-decoration: underline;">${g.size}</a></td>
                    <td>${g.color}</td>
                    <td>${pressureDisplay}</td>
                    <td style="text-align:right; color:#64748b; font-weight:500;">${stdWtDisplay}</td>
                    <td style="text-align:center; font-weight:bold; font-size:1.1rem;">${g.count}</td>
                    <td>${actionBtn}</td>
                   </tr>`;
        } else if (mode === 'brand_centric') {
            row = `<tr>
                    <td><a href="javascript:void(0)" onclick="drillDown('${g.brand}', '${g.size}', '${g.color}', '${safePressure}', '${safeWeight}')" style="color: #2563eb; font-weight: bold; text-decoration: underline;">${g.brand}</a></td>
                    <td>${g.color}</td>
                    <td>${pressureDisplay}</td>
                    <td style="text-align:right; color:#64748b; font-weight:500;">${stdWtDisplay}</td>
                    <td style="text-align:center; font-weight:bold; font-size:1.1rem;">${g.count}</td>
                    <td>${actionBtn}</td>
                   </tr>`;
        } else {
            row = `<tr>
                    <td style="font-weight:bold;">${g.brand}</td>
                    <td><a href="javascript:void(0)" onclick="drillDown('${g.brand}', '${g.size}', '${g.color}', '${safePressure}', '${safeWeight}')" style="color: #2563eb; font-weight: bold; text-decoration: underline;">${g.size}</a></td>
                    <td>${g.color}</td>
                    <td>${pressureDisplay}</td>
                    <td style="text-align:right; color:#64748b; font-weight:500;">${stdWtDisplay}</td>
                    <td style="text-align:center; font-weight:bold; font-size:1.1rem;">${g.count}</td>
                    <td>${actionBtn}</td>
                   </tr>`;
        }
        tbody.innerHTML += row;
    });

    let colorStrings = [];
    Object.keys(colorTotals).sort().forEach(color => {
        let c = colorTotals[color];
        colorStrings.push(`<span style="margin-right:15px;">${color}: <b>${c.count}</b> <span style="color:#64748b; font-size:0.9em;">(${c.weight.toFixed(1)}kg)</span></span>`);
    });
    
    if (colorStrings.length > 0) {
        tbody.innerHTML += `
            <tr style="background-color: #f8fafc; border-top: 2px solid #e2e8f0;">
                <td colspan="${totalColSpan}" style="text-align: right; padding-right: 15px; font-weight:bold; color:#64748b;">Color Wise:</td>
                <td colspan="2" style="text-align: left; font-weight:bold; color:#334155;">
                    ${colorStrings.join(" | ")}
                </td>
            </tr>
        `;
    }

    tbody.innerHTML += `
        <tr style="background-color: #f1f5f9; font-weight: bold; border-top: 2px solid #cbd5e1;">
            <td colspan="${totalColSpan}" style="text-align: right; padding-right: 15px;">GRAND TOTAL QTY:</td>
            <td style="text-align: center; font-size: 1.1rem; color: #2563eb;">${grandTotalQty}</td>
            <td></td>
        </tr>
        <tr style="background-color: #f1f5f9; font-weight: bold;">
            <td colspan="${totalColSpan}" style="text-align: right; padding-right: 15px;">GRAND TOTAL WEIGHT:</td>
            <td colspan="2" style="text-align: center; font-size: 1.1rem; color: #ef4444;">${(grandTotalWt).toFixed(3)} Kg</td>
        </tr>
    `;
}

async function drillDown(brand, size, color, targetPressure = null, targetWeight = null) {
    isDetailMode = true;
    
    const isReportTab = document.getElementById('tab-reports').classList.contains('active');
    if (typeof showTab === 'function') {
        showTab('inventory');
    }

    document.getElementById('inv-summary-view').style.display = 'none';
    document.getElementById('inv-detail-view').style.display = 'block';
    document.getElementById('masterTable').style.display = 'table'; 
    document.getElementById('detail-nav-header').style.display = 'flex';
    
    let title = `📄 ${brand} ${size} ${color}`;
    if (targetPressure && targetPressure !== '-') title += ` (${targetPressure})`;
    if (targetWeight) title += ` [${parseFloat(targetWeight).toFixed(3)} Kg]`;
    
    document.getElementById('masterBody').innerHTML = '<tr><td colspan="10" style="text-align:center;">Fetching IDs from server...</td></tr>';

    const activePressure = targetPressure || document.getElementById('f_pressure').value;
    const activeWeight = targetWeight || (document.getElementById('f_weight') ? document.getElementById('f_weight').value : '');

    let fetchStatus = document.getElementById('f_status').value;
    let fetchDate = document.getElementById('f_start').value;
    let fetchReportType = 'inventory';
    let fetchTimeRange = '';

    if (isReportTab) {
        fetchReportType = currentReportType; 
        fetchDate = document.getElementById('rep_date').value;
        fetchTimeRange = document.getElementById('rep_range').value;
        fetchStatus = 'all'; 
        if(fetchDate) title += ` (Date: ${fetchDate})`; 
    }
    
    document.getElementById('detail-view-title').innerText = title;

    const params = new URLSearchParams({
        name: brand,
        size: size,
        color: color,
        pressure: activePressure === '-' ? '' : activePressure, 
        weight: activeWeight,
        status: fetchStatus,            
        report_type: fetchReportType,   
        date: fetchDate,                
        time_range: fetchTimeRange,     
        grouped: 'false',  
        page: 1,           
        per_page: 1000     
    });

    try {
        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        const freshData = await res.json();
        renderDetailTable(freshData.items, false);
        
        const paginationEl = document.getElementById('pagination-controls');
        if (paginationEl) paginationEl.style.display = 'none';

    } catch(e) {
        console.error(e);
        alert("Failed to load details.");
        document.getElementById('masterBody').innerHTML = '<tr><td colspan="10" style="text-align:center; color:red;">Error loading data.</td></tr>';
    }
}

function renderDetailTable(data, isMainView) {
    document.getElementById('inv-summary-view').style.display = 'none';
    document.getElementById('inv-detail-view').style.display = 'block';

    const navHeader = document.getElementById('detail-nav-header');
    
    if (isMainView) {
        if (navHeader) navHeader.style.display = 'none'; 
    } else {
        if (navHeader) navHeader.style.display = 'flex'; 
    }

    const tbody = document.getElementById('masterBody');
    tbody.innerHTML = '';

    if(data.length === 0) { 
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;">No records.</td></tr>'; 
        return; 
    }

    data.forEach(row => {
        let statusHtml = "";
        if (row.dispatched_by === 'rejected') {
            statusHtml = `<span style="background:#fee2e2; color:#ef4444; padding:3px 8px; border-radius:6px; font-weight:700; font-size:0.85rem;">Rejected</span>`;
        } else if (row.dispatched_at) {
            let dispatchInfo = "";
            if (row.challan_no) {
                dispatchInfo = `<span style="font-weight:700;">CH: ${row.challan_no}</span>`;
            } else {
                dispatchInfo = `Time: ${row.dispatched_at.slice(11, 16)}`;
            }
            statusHtml = `<span class="status-dispatch" title="Dispatched at ${row.dispatched_at}">${dispatchInfo}</span>`;
        } else {
            statusHtml = `<span class="status-stock">Stock</span>`;
        }

        tbody.innerHTML += `
            <tr>
                <td class="delete-col" style="text-align: center;">
                    <input type="checkbox" class="row-checkbox" value="${row.id}" onchange="updateDeleteButtonState()" style="transform: scale(1.2); cursor: pointer;">
                </td>
                <td>#${String(row.id).padStart(4,'0')}</td>
                <td>${row.pipe_name}</td>
                <td>${row.size}</td>
                <td>${row.color}</td>
                <td style="font-weight:bold; color:#64748b;">${row.pressure_class || '-'}</td>
                <td>${(row.weight_g).toFixed(3)}</td>
                <td>${row.operator || '-'}</td>
                <td>${row.created_at.slice(0,16)}</td>
                <td>${statusHtml}</td>
            </tr>`;
    });
}

function viewIds(brand, size, color, pressure, weight) {
    if (typeof showTab === 'function') showTab('inventory');

    document.getElementById('f_name').value = brand || '';
    document.getElementById('f_size').value = size || '';
    document.getElementById('f_color').value = color || '';
    
    const pressureDropdown = document.getElementById('f_pressure');
    if (!pressure || pressure === '-' || pressure === 'null' || pressure === 'undefined') {
        pressureDropdown.value = ''; 
    } else {
        let cleanPressure = String(pressure).toLowerCase().replace(/\s/g, '');
        let optionExists = Array.from(pressureDropdown.options).some(opt => opt.value === cleanPressure);
        pressureDropdown.value = optionExists ? cleanPressure : '';
    }

    let weightInput = document.getElementById('f_weight');
    if (!weightInput) {
        weightInput = document.createElement('input');
        weightInput.type = 'hidden';
        weightInput.id = 'f_weight';
        document.body.appendChild(weightInput);
    }
    weightInput.value = weight ? String(weight).replace(/[^0-9.]/g, '') : '';
    document.getElementById('f_status').value = 'stock'; 

    fetchInventory();
}

function resetFilters() {
    document.getElementById('f_name').value = '';
    document.getElementById('f_size').value = '';
    document.getElementById('f_color').value = '';
    document.getElementById('f_pressure').value = '';
    document.getElementById('f_status').value = 'stock'; 
    document.getElementById('f_start').value = '';

    if (document.getElementById('f_weight')) {
        document.getElementById('f_weight').value = '';
    }

    if (typeof isDeleteMode !== 'undefined') {
        isDeleteMode = false; 
    }
    
    const table = document.getElementById('masterTable');
    if (table) table.classList.remove('delete-mode-active');
    
    const enterBtn = document.getElementById('enter-delete-mode-btn');
    if (enterBtn) enterBtn.style.display = 'inline-block';
    
    const cancelBtn = document.getElementById('cancel-delete-mode-btn');
    if (cancelBtn) cancelBtn.style.display = 'none';
    
    const executeBtn = document.getElementById('bulk-delete-btn');
    if (executeBtn) executeBtn.style.display = 'none';

    fetchInventory(1);
}

function backToSummary() {
    if (typeof isDeleteMode !== 'undefined' && isDeleteMode) {
        toggleDeleteMode(); 
    }
    fetchInventory();
}

function printSummary() {
    const content = document.getElementById('summaryTable').outerHTML;
    printContent(content, "Detailed Stock Summary");
}

function downloadSummaryCSV() {
    if(!latestStockData || latestStockData.length === 0) return showToast("No Data", true);
    let csv = "Brand,Size,Color,Total Production,In Stock\n";
    latestStockData.forEach(row => {
        csv += `${row.pipe_name},${row.size},${row.color},${row.total},${row.stock}\n`;
    });
    downloadFile(csv, "stock_summary.csv");
}

function filterSummary() {
    const filter = document.getElementById('summarySearch').value.toLowerCase();
    const rows = document.getElementById('summaryTable').getElementsByTagName('tr');
    for (let i = 1; i < rows.length; i++) { 
        let text = rows[i].textContent || rows[i].innerText;
        rows[i].style.display = text.toLowerCase().indexOf(filter) > -1 ? "" : "none";
    }
}

function printInventory() {
    const content = document.getElementById('masterTable').outerHTML;
    const filters = `Brand: ${document.getElementById('f_name').value || 'All'} | Size: ${document.getElementById('f_size').value || 'All'} | Color: ${document.getElementById('f_color').value || 'All'} | Status: ${document.getElementById('f_status').value || 'All'}`;
    printContent(content, "Inventory List", filters);
}

function downloadInventoryCSV() {
    const params = newSearchParams({
        name: document.getElementById('f_name').value,
        size: document.getElementById('f_size').value,
        color: document.getElementById('f_color').value,
        pressure: document.getElementById('f_pressure').value,
        status: document.getElementById('f_status').value,
        start: document.getElementById('f_start').value,
        report_type: currentReportType,
        date: document.getElementById('rep_date').value,
        time_range: document.getElementById('rep_range').value,
        grouped: (currentReportType === 'production') ? 'true' : 'false'
    });
    downloadFileWithAuth(`/api/export?${params}`, 'report.csv');
}
// --- NEW HELPER: Jump to Verification Hub ---
function openVerify(brand, size, color, pressure, weight) {
    const params = new URLSearchParams();
    
    if (brand) {
        params.set('name', brand);      // Tells the backend database to filter by brand
        params.set('pipe_name', brand); // Tells the UI to print the brand in the title
    }
    if (size) params.set('size', size);
    if (color) params.set('color', color);
    if (pressure && pressure !== '-') params.set('pressure', pressure);
    
    // Parse and clean weight - remove non-numeric chars except decimal point
    if (weight) {
        let cleanWeight = String(weight).replace(/[^0-9.]/g, '');
        if (cleanWeight) params.set('weight', cleanWeight);
    }
    
    // Open the new tab with the correctly formatted filters!
    window.open('/verify?' + params.toString(), '_blank');
}