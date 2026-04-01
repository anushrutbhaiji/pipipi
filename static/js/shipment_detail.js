let groupedData = {};
let scannedIds = [];

function initTable() {
    // Read the data safely from the HTML
    const rawDataElement = document.getElementById('rawItemsData');
    if (!rawDataElement) return;
    
    const rawItems = JSON.parse(rawDataElement.textContent);

    // Group the data
    rawItems.forEach(item => {
        let pressure = item.pressure_class || '-';
        let key = `${item.pipe_name}|${item.size}|${item.color}|${pressure}`;
        
        if(!groupedData[key]) {
            groupedData[key] = {
                brand: item.pipe_name, 
                size: item.size, 
                color: item.color, 
                pressure: pressure,
                count: 0, 
                weight: 0, 
                items: [] // Store individual pipes here for the drill-down
            };
        }
        groupedData[key].count++;
        groupedData[key].weight += item.weight_g;
        groupedData[key].items.push(item);
    });

    renderSummary();
}

function renderSummary() {
    document.getElementById('summary-view').style.display = 'block';
    document.getElementById('detail-view').style.display = 'none';

    const tbody = document.getElementById('summaryBody');
    tbody.innerHTML = '';
    let grandTotalWt = 0;

    Object.keys(groupedData).forEach(key => {
        let g = groupedData[key];
        grandTotalWt += g.weight;
        
        tbody.innerHTML += `
            <tr>
                <td style="font-weight: 700; color: #334155;">${g.brand}</td>
                <td>${g.size}</td>
                <td>${g.color}</td>
                <td style="color: #ef4444; font-weight: 600;">${g.pressure !== '-' ? g.pressure : ''}</td>
                <td style="text-align: center; font-weight: bold; font-size: 1.1rem; color: #2563eb;">${g.count}</td>
                <td style="text-align: right;">${(g.weight / g.count).toFixed(3)}</td>
                <td style="text-align: center;" class="no-print">
                    <button class="btn" style="padding: 4px 10px; width: auto; font-size: 0.8rem; background: #e2e8f0; color: #475569;" onclick="viewIds('${key}')">Ids ↗</button>
                </td>
            </tr>
        `;
    });
    
    // Add Grand Total Row
    tbody.innerHTML += `
        <tr style="background: #f1f5f9; font-weight: bold; border-top: 2px solid #cbd5e1;">
            <td colspan="5" style="text-align: right; padding-right: 15px;">GRAND TOTAL WEIGHT:</td>
            <td style="text-align: right; font-size: 1.1rem; color: #2563eb;">${grandTotalWt.toFixed(3)} kg</td>
            <td class="no-print"></td>
        </tr>
    `;
}

function viewIds(key) {
    // Toggle Views
    document.getElementById('summary-view').style.display = 'none';
    document.getElementById('detail-view').style.display = 'block';
    
    let g = groupedData[key];
    let pText = g.pressure !== '-' ? ` | ${g.pressure}` : '';
    document.getElementById('detailTitle').innerText = `📄 ${g.brand} • ${g.size} • ${g.color} ${pText}`;

    const tbody = document.getElementById('detailBody');
    tbody.innerHTML = '';

    // Render the raw IDs
    g.items.forEach((item, index) => {
        tbody.innerHTML += `
            <tr>
                <td style="color: #94a3b8;">${index + 1}</td>
                <td style="font-family: monospace; font-size: 1.1rem; font-weight: 700; color: #475569;">#${item.id}</td>
                <td style="text-align: right;">${item.weight_g.toFixed(3)}</td>
            </tr>
        `;
    });
}

function backToSummary() {
    document.getElementById('summary-view').style.display = 'block';
    document.getElementById('detail-view').style.display = 'none';
}

// Run when page loads
document.addEventListener("DOMContentLoaded", initTable);

// --- ADD PIPES MODAL LOGIC ---
function openModal() {
    document.getElementById('addModal').style.display = 'flex';
    document.getElementById('scanInput').focus();
}

function closeModal() {
    document.getElementById('addModal').style.display = 'none';
    scannedIds = []; 
    renderList();
}

document.addEventListener('keydown', function(event) {
    if (event.key === "Escape") closeModal();
});

function handleScan(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const val = e.target.value.trim();
        if (!val) return;

        const idMatch = val.match(/\d+/);
        if(idMatch) {
            const id = parseInt(idMatch[0]);
            if(scannedIds.includes(id)) {
                alert("⚠️ Pipe #" + id + " is already in the list!");
            } else {
                scannedIds.unshift(id); 
                renderList();
            }
            e.target.value = ''; 
        } else {
            alert("❌ Invalid Barcode Format");
        }
    }
}

function renderList() {
    const ul = document.getElementById('scannedList');
    const countSpan = document.getElementById('pendingCount');
    countSpan.innerText = scannedIds.length;

    if (scannedIds.length === 0) {
        ul.innerHTML = '<li style="padding: 20px; text-align: center; color: #94a3b8; font-style: italic;">No items scanned yet.</li>';
        return;
    }

    ul.innerHTML = scannedIds.map(id => `
        <li class="pending-item">
            <span style="font-weight: 600; color: #334155;">📦 Pipe #${id}</span>
            <button class="del-btn" onclick="removeScan(${id})">Remove</button>
        </li>
    `).join('');
}

function removeScan(id) {
    scannedIds = scannedIds.filter(x => x !== id);
    renderList();
}

async function commitItems() {
    if (scannedIds.length === 0) return alert("Scan some pipes first!");

    // Read the shipment ID injected from the HTML
    const shipmentId = window.CURRENT_SHIPMENT_ID;
    const btn = document.querySelector('.modal-footer .btn:last-child');
    const originalText = btn.innerText;
    
    btn.innerText = "Saving...";
    btn.disabled = true;

    const payload = {
        shipment_id: shipmentId,
        items: scannedIds.map(id => ({ id: id })) 
    };

    try {
        const res = await fetch('/api/dispatch/edit_add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (data.success) {
            location.reload(); 
        } else {
            alert("❌ Error: " + data.message);
            btn.innerText = originalText;
            btn.disabled = false;
        }
    } catch (e) {
        alert("Connection Error");
        console.error(e);
        btn.innerText = originalText;
        btn.disabled = false;
    }
}