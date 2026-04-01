let isAutoEnabled = false;

window.onload = function() { 
    loadCustoms(); 
    loadLastSettings(); // Settings + Auto Button Status load karega
    loadCounter(); 
    updatePreview(); 
}

// --- 1. HELPER: SYNC TO SERVER (Yeh Missing tha) ---
function syncToServer(data) {
    fetch('/api/settings/update', {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    }).catch(e => console.log("Sync failed"));
}

// --- 2. SELECT FUNCTION ---
function select(type, el, val) {
    // 1. Set Value
    let inputId = (type === 'name') ? 'pipe_name' : type;
    document.getElementById(inputId).value = val;
    
    // 2. SAVE TO SERVER (Global Sync)
    let payload = {};
    payload[type] = val;
    syncToServer(payload); // Ab yeh function exist karta hai

    // 3. Visual Update (Blue Buttons)
    let container = document.getElementById('group-'+type);
    if(container) {
        for(let c of container.getElementsByClassName('chip')) {
            if(!c.classList.contains('add-btn')) c.classList.remove('active');
        }
        if (el) {
            el.classList.add('active');
        } else {
            let cleanVal = val.toString().toLowerCase().replace(/\s/g, ''); 
            for(let c of container.getElementsByClassName('chip')) {
                let btnText = c.innerText.toLowerCase().replace(/\s/g, ''); 
                if(cleanVal.includes(btnText) || btnText.includes(cleanVal)) {
                    c.classList.add('active');
                }
            }
        }
    }
    
    updatePreview();
    if (typeof isAutoEnabled !== 'undefined' && isAutoEnabled) updateServerSettings();
}

// --- 3. LOAD SETTINGS (Memory Logic Fixed) ---
function loadLastSettings() {
    fetch('/api/settings/get')
        .then(res => res.json())
        .then(data => {
            // Restore Buttons
            ['operator', 'name', 'size', 'pressure', 'color'].forEach(type => {
                if (data[type]) select(type, null, data[type]);
            });

            // Restore Weight
            if (data.weight) {
                document.getElementById('weight_g').value = data.weight;
                updatePreview();
            }

            // --- RESTORE AUTO BUTTON STATUS (Reboot Proof) ---
            if (data.auto_enabled !== undefined) {
                isAutoEnabled = data.auto_enabled;
                updateAutoButtons(data.auto_enabled);
                
                // Agar ON tha, toh server hardware ko bhi ON signal bhejo
                if (data.auto_enabled) {
                    setTimeout(() => {
                         // Bina status save kiye bas hardware on karo
                         let s = getCurrentSettingsObj();
                         fetch('/api/autoprint/toggle', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ enabled: true, settings: s })
                         }).catch(e=>{});
                    }, 500);
                }
            }
        })
        .catch(err => console.log("Sync Error:", err));
}

// --- 4. SERVER SETTINGS UPDATE ---
function updateServerSettings() {
    let settings = getCurrentSettingsObj();
    fetch('/api/autoprint/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true, settings: settings })
    }).catch(err => console.error("Background update failed", err));
}

function getCurrentSettingsObj() {
    return {
        pipe_name: document.getElementById('pipe_name').value,
        size: document.getElementById('size').value,
        color: document.getElementById('color').value,
        pressure: document.getElementById('pressure').value,
        operator: document.getElementById('operator').value,
        batch: "", // batch will be set to #<counter+1> when printing
        weight_g: document.getElementById('weight_g').value || "0.000"
    };
}

// --- CUSTOM BUTTONS ---
function addCustom(type) {
    let name = prompt("Enter new Name:");
    if (!name) return;
    createChipElement(type, name);
    saveCustom(type, name);
}

function createChipElement(type, val) {
    let container = document.getElementById('group-' + type);
    let btn = document.createElement('div');
    btn.className = 'chip';
    btn.innerHTML = val + '<span class="delete-x" onclick="removeCustom(event, \''+type+'\', \''+val+'\', this.parentNode)">&times;</span>';
    btn.onclick = function(e) { if(e.target.className !== 'delete-x') select(type, this, val); };
    let addBtn = container.querySelector('.add-btn');
    container.insertBefore(btn, addBtn);
}

function removeCustom(event, type, val, btnElement) {
    event.stopPropagation(); 
    if (!confirm("Delete '" + val + "'?")) return;
    let key = 'custom_' + type;
    let exist = JSON.parse(localStorage.getItem(key) || "[]");
    localStorage.setItem(key, JSON.stringify(exist.filter(i => i !== val)));
    btnElement.remove();
}

function saveCustom(type, val) {
    let key = 'custom_' + type;
    let exist = JSON.parse(localStorage.getItem(key) || "[]");
    if (!exist.includes(val)) { exist.push(val); localStorage.setItem(key, JSON.stringify(exist)); }
}

function loadCustoms() {
    ['operator', 'name', 'pressure', 'size'].forEach(type => {
        let saved = JSON.parse(localStorage.getItem('custom_' + type) || "[]");
        saved.forEach(val => createChipElement(type, val));
    });
}

// --- COUNTER LOGIC ---
setInterval(fetchCounter, 5000); // Check every 5 secs (Optimized)

async function fetchCounter() {
    try {
        const res = await fetch('/api/counter');
        document.getElementById('pipeCounterDisplay').innerText = (await res.json()).count;
    } catch (e) {}
}
function loadCounter() { fetchCounter(); }

async function resetCounter() {
    if(confirm("Reset Counter?")) {
        await fetch('/api/counter/reset', { method: 'POST' });
        fetchCounter();
    }
}

// --- NUMPAD & FORM ---
function addNum(val) {
    let field = document.getElementById('weight_g');
    if(val === '.' && field.value.includes('.')) return;
    if(field.value.length > 7) return; 
    field.value += val;
    
    // Sync Weight
    syncToServer({ weight: field.value });

    updatePreview();
    if (isAutoEnabled) updateServerSettings();
}

function clearWeight() {
    document.getElementById('weight_g').value = '';
    syncToServer({ weight: '' });
    updatePreview();
}

function submitForm() { document.getElementById('realSubmitBtn').click(); }

function updatePreview(qrBase64 = null) {
    const s = getCurrentSettingsObj();
    let qrHtml = qrBase64 ? `<img src="${qrBase64}">` : `<span style="color:#ccc; font-size:12px;">QR Code</span>`;

    document.getElementById('previewArea').innerHTML = `
    <div class="label-visual">
        <div class="lbl-header">
            <div class="lbl-brand">${s.pipe_name}</div>
            <div class="lbl-detail">${s.size}mm | ${s.color}</div>
        </div>
        <div class="lbl-qr-zone">${qrHtml}</div>
        <div class="lbl-weight-zone">${s.weight_g} Kg</div>
        <div class="lbl-meta">
            <span>Op: ${s.operator} | <b>${s.pressure}</b> ${s.batch ? '| ' + s.batch : ''}</span>
            <span>Date: ${new Date().toLocaleDateString()}</span>
        </div>
    </div>`; 
}

document.getElementById('labelForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    let wt = parseFloat(document.getElementById('weight_g').value);
    if (isNaN(wt) || wt <= 0) { alert("Enter Weight!"); return; }

    let payload = getCurrentSettingsObj();
    try {
        // Get current counter and use next number for batch
        try {
            const cntRes = await fetch('/api/counter');
            if (cntRes.ok) {
                const cntData = await cntRes.json();
                payload.batch = `#${cntData.count + 1}`;
            } else {
                payload.batch = payload.batch || '#1';
            }
        } catch (e) {
            payload.batch = payload.batch || '#1';
        }

        const res = await fetch('/api/labels', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
        const data = await res.json();
        if (data.success) {
            updatePreview(data.qr_image);
            await fetch('/api/print', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ id: data.label.id, pressure: payload.pressure }) });
            fetchCounter();
        }
    } catch (e) { alert("Error Printing"); }
});

// --- AUTO MODE LOGIC (Fixed) ---
function setAutoMode(turnOn) {
    isAutoEnabled = turnOn;
    updateAutoButtons(turnOn);
    
    // 1. Save Status to Memory (Reboot Proof)
    syncToServer({ auto_enabled: turnOn });

    // 2. Hardware Toggle
    let payload = { enabled: turnOn };
    if (turnOn) payload.settings = getCurrentSettingsObj();

    fetch('/api/autoprint/toggle', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).catch(e => console.error("Auto toggle failed"));
}

function updateAutoButtons(isOn) {
    isAutoEnabled = isOn;
    const btnOn = document.getElementById('btn-auto-on');
    const btnOff = document.getElementById('btn-auto-off');
    if (isOn) {
        btnOn.classList.add('active-green');
        btnOff.classList.remove('active-red');
    } else {
        btnOn.classList.remove('active-green');
        btnOff.classList.add('active-red');
    }
}

// --- LIVE SYNC (Also syncs Auto Button status) ---
setInterval(function() {
    fetch('/api/settings/get')
        .then(res => res.json())
        .then(remote => {
            // Sync Chips
            const fields = ['name', 'size', 'pressure', 'color', 'operator'];
            fields.forEach(type => {
                let inputId = (type === 'name') ? 'pipe_name' : type;
                let currentVal = document.getElementById(inputId).value;
                if (remote[type] && remote[type] !== currentVal) select(type, null, remote[type]);
            });

            // Sync Weight
            let currentWt = document.getElementById('weight_g').value;
            if (remote.weight && remote.weight !== currentWt && document.activeElement.id !== 'weight_g') {
                document.getElementById('weight_g').value = remote.weight;
                updatePreview();
            }

            // Sync Auto Button (Taaki doosre device pe dikhe)
            if (remote.auto_enabled !== undefined && remote.auto_enabled !== isAutoEnabled) {
                isAutoEnabled = remote.auto_enabled;
                updateAutoButtons(isAutoEnabled);
            }
        })
        .catch(e => {});
}, 12000);
