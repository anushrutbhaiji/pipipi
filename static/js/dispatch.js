document.addEventListener('DOMContentLoaded', function() {
    const fetchChallanBtn = document.getElementById('fetch-challan-btn');
    const challanLabel = document.getElementById('challan-label');
    const scanInput = document.getElementById('scan-input');
    const scanStatus = document.getElementById('scan-status');
    const tableBody = document.getElementById('dispatch-table-body');
    const totalPipesEl = document.getElementById('total-pipes');
    const totalWeightEl = document.getElementById('total-weight');
    const dispatchBtn = document.getElementById('dispatch-btn');
    const clearBtn = document.getElementById('clear-btn');
    const printBtn = document.getElementById('print-btn');

    const metaForm = document.getElementById('shipment-meta-form');
    
    // Form Elements
    const vehicleInput = document.getElementById('vehicle-no');
    const driverMobileInput = document.getElementById('driver-mobile');
    const challanNoInput = document.getElementById('challan-no');

    // Add these right below your detailsModal variable declarations
    const proformaModal = new bootstrap.Modal(document.getElementById('proformaModal'));
    const confirmDispatchBtn = document.getElementById('confirm-dispatch-btn');
    const detailsModal = new bootstrap.Modal(document.getElementById('detailsModal'));
    const detailsModalTitle = document.getElementById('detailsModalTitle');
    const detailsModalList = document.getElementById('detailsModalList');
    const btnReturnMode = document.getElementById('btn-return-mode');
    let isReturnMode = false; 
    // -----------------------
    let scannedItems = []; // Array of full pipe objects
    let scannedIds = new Set(); // Set of IDs for quick lookup

    let scanLogEntries = []; // stores each scan box input
    const scanLogList = document.getElementById('scan-log-list');
    const logbookEmpty = document.getElementById('logbook-empty');
    const clearLogBtn = document.getElementById('clear-log-btn');

    function saveLog() {
        localStorage.setItem('dispatchScanLog', JSON.stringify(scanLogEntries));
    }

    function renderScanLog() {
        scanLogList.innerHTML = '';
        if (!scanLogEntries.length) {
            logbookEmpty.style.display = 'block';
            return;
        }
        logbookEmpty.style.display = 'none';

        scanLogEntries.slice().reverse().forEach(entry => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `<small class="text-muted">${entry.time}</small><br><strong>${entry.input}</strong><br><span class="text-${entry.statusType}">${entry.status}</span>`;
            
            // ✨ THE FIX: Add the Quick Return Button if this item was already dispatched
            if (entry.returnableItem) {
                const btn = document.createElement('button');
                btn.className = 'btn btn-sm btn-warning mt-2 w-100 fw-bold';
                btn.innerHTML = '📥 Quick Return to Stock';
                btn.onclick = () => quickReturnPipe(entry);
                li.appendChild(btn);
            }

            scanLogList.appendChild(li);
        });
    }

    // ✨ THE FIX: The function that handles the quick return
    async function quickReturnPipe(entry) {
        if (!confirm(`Are you sure you want to return Pipe #${entry.returnableItem.id} back to stock?`)) return;
        
        try {
            const res = await fetch('/api/returns/create', {
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ items: [entry.returnableItem] }) // Send just this one pipe
            });
            const d = await res.json();
            
            if (d.success) {
                alert(`✅ Pipe #${entry.returnableItem.id} is back in stock! You can now scan it for dispatch.`);
                
                // Update the log entry so it turns green and the button disappears
                entry.status = "Restocked successfully";
                entry.statusType = "success";
                delete entry.returnableItem; 
                
                saveLog();
                renderScanLog();
            } else {
                alert("Error: " + d.message);
            }
        } catch(e) {
            alert("Connection error: " + e.message);
        }
    }

    function loadLog() {
        const saved = JSON.parse(localStorage.getItem('dispatchScanLog') || '[]');
        scanLogEntries = Array.isArray(saved) ? saved : [];
        renderScanLog();
    }

    function addLogEntry(input, status, statusType='secondary') {
        const entry = {
            input: String(input || '').trim(),
            status,
            statusType,
            time: new Date().toLocaleString()
        };
        scanLogEntries.push(entry);
        saveLog();
        renderScanLog();
        return entry;
    }

    clearLogBtn.addEventListener('click', () => {
        if (!confirm('Clear scan log?')) return;
        scanLogEntries = [];
        saveLog();
        renderScanLog();
    });

    // --- Persistence Logic ---
    function saveState() {
        const state = {
            meta: {
                driver_mobile: driverMobileInput.value,
                challan_no: challanNoInput.value,
                vehicle: vehicleInput.value,
            },
            items: scannedItems
        };
        localStorage.setItem('dispatchSheet', JSON.stringify(state));
    }

    function loadState() {
        const state = JSON.parse(localStorage.getItem('dispatchSheet'));
        if (state) {
            // Load meta data
            if (state.meta) {
                driverMobileInput.value = state.meta.driver_mobile || '';
                challanNoInput.value = state.meta.challan_no || '';
                vehicleInput.value = state.meta.vehicle || '';
            }
            
            let rawItems = state.items || [];
            
            // --- FIX 2: AUTO-CLEANUP ON LOAD ---
            // This removes any duplicates that are already saved
            const uniqueMap = new Map();
            rawItems.forEach(item => {
                if(!uniqueMap.has(item.id)) {
                    uniqueMap.set(item.id, item);
                }
            });
            scannedItems = Array.from(uniqueMap.values());
            // -----------------------------------

            scannedItems.forEach(item => scannedIds.add(item.id));
            renderTable();
        }
    }
    // --- NEW: RETURN MODE TOGGLE ---
    // --- NEW: RETURN MODE TOGGLE ---
    btnReturnMode.addEventListener('click', () => {
        isReturnMode = !isReturnMode; // Toggle status

        if (isReturnMode) {
            // Switch to Red/Return UI
            document.body.style.backgroundColor = "#fff5f5";
            document.querySelector('.card-header').style.backgroundColor = "#fee2e2";
            document.querySelector('.card-header h3').innerText = "🔄 RETURN VOUCHER";
            document.querySelector('.card-header h3').style.color = "#dc2626";
            
            btnReturnMode.innerText = "❌ Cancel Return Mode";
            btnReturnMode.classList.replace('btn-danger', 'btn-secondary');
            
            dispatchBtn.innerText = "⚠️ Confirm Return & Restock";
            dispatchBtn.classList.replace('btn-success', 'btn-danger');
            
            // Show auto-fetch button
            challanLabel.innerHTML = 'Source Challan <span class="text-danger">*</span>';
            fetchChallanBtn.style.display = 'block';
            
            // Clear list so we don't mix shipments with returns
            scannedItems = []; scannedIds.clear(); renderTable();
            alert("RETURN MODE ON: Type the Challan Number and press 'Fetch Pipes' to auto-load them.");
        } else {
            // Switch back to Normal
            location.reload(); 
        }
    });

    // --- Core Logic ---
    function renderTable() {
        let totalWeight = 0;
        tableBody.innerHTML = '';

        // Display scanned items in ascending order by ID
        const displayItems = scannedItems.slice().sort((a, b) => {
            const aId = Number(a.id);
            const bId = Number(b.id);
            if (!Number.isNaN(aId) && !Number.isNaN(bId)) {
                return aId - bId;
            }
            return String(a.id).localeCompare(String(b.id), undefined, { numeric: true, sensitivity: 'base' });
        });

        displayItems.forEach((item, index) => {
            totalWeight += parseFloat(item.weight_g || 0);

            // (Inside your renderTable loop)
            const colorDot = `<span class="color-dot" style="background-color: ${item.color.toLowerCase() === 'blue' ? '#2563eb' : '#64748b'};"></span>`;
            
            // Format the pressure nicely
            const pressureDisplay = item.pressure_class ? `<span style="color:#ef4444; font-weight:600;">${item.pressure_class}</span>` : '<span style="color:#cbd5e1;">-</span>';

            const rowNum = index + 1;

            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${rowNum}</td>
                <td><strong>${item.id}</strong></td>
                <td>${item.pipe_name}</td>
                <td>${item.size}</td>
                <td>${colorDot} ${item.color}</td>
                <td>${pressureDisplay}</td> <!-- ADDED PRESSURE -->
                <td class="text-end">${parseFloat(item.weight_g || 0).toFixed(3)}</td>
                <td class="text-center no-print">
                    <button class="btn-action remove-btn" title="Remove ID ${item.id}">🗑️</button>
                </td>
            `;

            // The trash can now directly removes this specific ID (No more popup modal needed!)
            row.querySelector('.remove-btn').addEventListener('click', (e) => {
                e.stopPropagation(); 
                if (confirm(`Remove Pipe ID ${item.id} from this shipment?`)) {
                    removeItem(item.id);
                }
            });

            tableBody.appendChild(row);
        });

        // Update the KPI blocks at the top
        totalPipesEl.textContent = scannedItems.length;
        totalWeightEl.textContent = (totalWeight).toFixed(2);
        updatePrintableHeader();
    }

    function showDetails(groupKey, groupedData) {
        const group = groupedData[groupKey];
        detailsModalTitle.textContent = `Details for: ${group.pipe_name} ${group.size} (${group.color})`;
        detailsModalList.innerHTML = '';
        group.items.forEach(item => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `
                <span>ID: ${item.id} | Weight: ${(item.weight_g).toFixed(3)} kg</span>
                <button class="btn btn-sm btn-outline-danger no-print" data-item-id="${item.id}">Remove</button>
            `;
            li.querySelector('button').addEventListener('click', (e) => {
                e.stopPropagation(); // prevent row click
                removeItem(item.id);
                detailsModal.hide();
            });
            detailsModalList.appendChild(li);
        });
        detailsModal.show();
    }

    function removeItem(itemId) {
        scannedItems = scannedItems.filter(item => item.id !== itemId);
        scannedIds.delete(itemId);
        setStatus(`Removed pipe ID ${itemId}.`, 'info');
        saveState();
        renderTable();
    }

    function removeGroup(groupKey, groupData) {
        if (confirm(`Are you sure you want to remove all ${groupData.quantity} items of ${groupData.pipe_name} ${groupData.size}?`)) {
            const idsToRemove = new Set(groupData.items.map(item => item.id));
            
            scannedItems = scannedItems.filter(item => !idsToRemove.has(item.id));
            idsToRemove.forEach(id => scannedIds.delete(id));
            
            setStatus(`Removed ${idsToRemove.size} items.`, 'info');
            saveState();
            renderTable();
        }
    }

    function setStatus(message, type = 'success') {
        scanStatus.textContent = message;
        scanStatus.className = `form-text status-message mt-2 text-${type}`;
        setTimeout(() => scanStatus.textContent = '', 4000);
    }

    async function handleScan(qrData) {
        let pipeId = null;
        const trimmedData = String(qrData || '').trim();

        const activeLog = addLogEntry(trimmedData, 'Processing...', 'info');

        // 1. Try to parse as a full JSON object (standard QR code)
        try {
            const pipeInfo = JSON.parse(trimmedData);
            if (pipeInfo && pipeInfo.id) {
                pipeId = pipeInfo.id;
            }
        } catch (e) {
            // Not a valid JSON object
        }

        // 2. If not JSON, check if it's a plain number
        if (pipeId === null) {
            const numericId = parseInt(trimmedData, 10);
            if (!isNaN(numericId) && String(numericId) === trimmedData) {
                pipeId = numericId;
            }
        }

        // 3. Try to find an ID pattern
        if (pipeId === null) {
            const match = trimmedData.match(/"id":\s*(\d+)/);
            if (match && match[1]) {
                pipeId = parseInt(match[1], 10);
            }
        }

        if (pipeId === null) {
            setStatus("Invalid QR code or ID format.", "danger");
            speakResponse("गलत बारकोड"); // 🔊 AUDIO ADDED
            activeLog.status = "Invalid format";
            activeLog.statusType = "danger";
            saveLog(); renderScanLog();
            return;
        }

        if (scannedIds.has(pipeId)) {
            setStatus(`Pipe ID ${pipeId} is already in this sheet.`, "warning");
            speakResponse("डुप्लीकेट स्कैन") // 🔊 AUDIO ADDED
            activeLog.status = `Duplicate ID ${pipeId}`;
            activeLog.statusType = "warning";
            saveLog(); renderScanLog();
            return;
        }
        try {
            const response = await fetch(`/api/labels/${pipeId}`);
            if (!response.ok) throw new Error(`Pipe ID ${pipeId} not found in database.`);
            
            const item = await response.json();

            // --- FIX 1: DOUBLE CHECK (The Safety Guard) ---
            if (scannedIds.has(item.id)) {
                console.warn(`Duplicate blocked for ID ${item.id}`); // Silent block
                return; 
            }
            // ----------------------------------------------

            if (isReturnMode) {
                if (!item.dispatched_at) {
                    setStatus("Error: Already in Stock!", "danger");
                    speakResponse("स्टॉक में पहले से है"); // 🔊 AUDIO ADDED
                    activeLog.status = "Already in stock";
                    activeLog.statusType = "danger";
                    saveLog(); renderScanLog();
                    return;
                }
            } else {
                if (item.dispatched_at) {
                    setStatus("Error: Already Dispatched!", "danger");
                    speakResponse("डिस्पैच हो चुका है"); // 🔊 AUDIO ADDED
                    activeLog.status = "Already dispatched";
                    activeLog.statusType = "danger";
                    saveLog(); renderScanLog();
                    return;
                }
            }

            scannedItems.push(item);
            scannedIds.add(item.id);
            speakResponse("हो गया"); // 🔊 AUDIO ADDED
            
            setStatus(`Added: ${item.pipe_name} ${item.size}`, 'success');
            activeLog.status = `Added: ${item.pipe_name} ${item.size}`;
            activeLog.statusType = 'success';
            saveLog(); renderScanLog();
            saveState();
            renderTable();

        } catch (error) {
            setStatus(error.message, 'danger');
            speakResponse("Error, pipe not found"); // 🔊 AUDIO ADDED
            activeLog.status = `Error: ${error.message}`;
            activeLog.statusType = 'danger';
            saveLog(); renderScanLog();
        }
    }

    // --- Event Listeners ---
    scanInput.addEventListener('paste', (e) => {
        e.preventDefault();
        const text = e.clipboardData.getData('text/plain');
        scanInput.value = '';
        handleScan(text);
    });

    scanInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (scanInput.value.trim()) {
                handleScan(scanInput.value.trim());
                scanInput.value = '';
            }
        }
    });

    metaForm.addEventListener('input', () => {
        saveState();
        updatePrintableHeader();
    });

    clearBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear the entire dispatch sheet?')) {
            scannedItems = [];
            scannedIds.clear();
            localStorage.removeItem('dispatchSheet');
            renderTable();
            setStatus('Sheet cleared.', 'info');
        }
    });

    dispatchBtn.addEventListener('click', async () => {
        // --- 1. RETURN MODE LOGIC (Kept exactly the same) ---
        if (isReturnMode) {
            if (scannedItems.length === 0) { alert('Scan items first.'); return; }
            if(!confirm(`⚠️ RETURNS: Put ${scannedItems.length} pipes back into Stock?`)) return;
            try {
                const res = await fetch('/api/returns/create', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ items: scannedItems })
                });
                const d = await res.json();
                if(d.success) {
                    alert("✅ Items returned to stock.");
                    localStorage.removeItem('dispatchSheet'); 
                    scannedItems = []; scannedIds.clear();
                    scanLogEntries = [];
                    saveLog();
                    renderScanLog();
                    location.reload(); 
                } else { alert(d.message); }
            } catch(e) { alert(e.message); }
            return; 
        }

        // --- 2. PREPARE NORMAL DISPATCH (The Proforma Preview) ---
        if (!challanNoInput.value) { alert('Please enter a Challan Number before dispatching.'); return; }
        if (scannedItems.length === 0) { alert('Cannot dispatch an empty sheet. Please scan items first.'); return; }

        // Group the items just like your old table used to do
        // --- Group the items for the Invoice ---
        const grouped = {};
        let totalWeight = 0;

        scannedItems.forEach(item => {
            // ADD PRESSURE TO THE UNIQUE KEY so 4kgf and 10kgf don't mix!
            const pressure = item.pressure_class || '-';
            const key = `${item.pipe_name}|${item.size}|${item.color}|${pressure}`;
            
            if (!grouped[key]) {
                grouped[key] = { 
                    pipe_name: item.pipe_name, 
                    size: item.size, 
                    color: item.color, 
                    pressure: pressure, // Save it here
                    quantity: 0, 
                    weight: 0 
                };
            }
            grouped[key].quantity++;
            grouped[key].weight += parseFloat(item.weight_g || 0);
            totalWeight += parseFloat(item.weight_g || 0);
        });

        // Populate the Modal Header details
        document.getElementById('prof-challan').textContent = challanNoInput.value;
        document.getElementById('prof-vehicle').textContent = vehicleInput.value || 'N/A';
        document.getElementById('prof-driver').textContent = driverMobileInput.value || 'N/A';
        document.getElementById('prof-weight').textContent = totalWeight.toFixed(2);

        // Populate the Modal Table
        const profBody = document.getElementById('proforma-table-body');
        profBody.innerHTML = '';
        for (const key in grouped) {
            const g = grouped[key];
            
            // Format the pressure for the invoice
            let pressureDisplay = g.pressure !== '-' ? `<span style="color:#ef4444; font-weight:600;">${g.pressure}</span>` : '<span style="color:#cbd5e1;">-</span>';

            profBody.innerHTML += `
                <tr>
                    <td><strong>${g.pipe_name}</strong></td>
                    <td>${g.size}</td>
                    <td>
                        <span class="color-dot" style="background-color: ${g.color.toLowerCase() === 'blue' ? '#2563eb' : '#64748b'};"></span>
                        ${g.color}
                    </td>
                    <td>${pressureDisplay}</td> <!-- ADDED PRESSURE -->
                    <td class="text-center" style="font-size: 1.1rem;"><strong>${g.quantity}</strong></td>
                    <td class="text-end">${g.weight.toFixed(3)}</td>
                </tr>
            `;
        }

        // Open the Proforma Invoice Preview!
        proformaModal.show();
    });

    // --- 3. FINAL CONFIRMATION BUTTON (Inside the Modal) ---
    confirmDispatchBtn.addEventListener('click', async () => {
        // Disable button so the user doesn't double-click it by accident
        confirmDispatchBtn.disabled = true;
        confirmDispatchBtn.innerText = "Processing...";

        const payload = {
            meta: {
                vehicle: vehicleInput.value,
                driver_mobile: driverMobileInput.value,
                challan_no: challanNoInput.value
            },
            items: scannedItems
        };

        try {
            const response = await fetch('/api/shipments/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.message || 'Dispatch failed.');

            alert(`Success! ${result.message}`);
            
            // Cleanup for Normal Dispatch
            proformaModal.hide();
            scannedItems = [];
            scannedIds.clear();
            localStorage.removeItem('dispatchSheet');

            vehicleInput.value = '';
            driverMobileInput.value = '';
            challanNoInput.value = '';

            scanLogEntries = [];
            saveLog();
            renderScanLog();

            renderTable();
            saveState();

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            // Re-enable the button just in case there was an error and they need to try again
            confirmDispatchBtn.disabled = false;
            confirmDispatchBtn.innerText = "🚀 Confirm & Dispatch";
        }
    });
    function updatePrintableHeader() {
        document.getElementById('print-driver-mobile').textContent = driverMobileInput.value || 'N/A';
        document.getElementById('print-challan').textContent = challanNoInput.value || 'N/A';
        document.getElementById('print-vehicle').textContent = vehicleInput.value || 'N/A';
        document.getElementById('print-date').textContent = new Date().toLocaleString();
    }

    printBtn.addEventListener('click', () => {
        updatePrintableHeader();
        window.print();
    });

    // --- Initial Load ---
    loadState();
    loadLog();
    scanInput.focus();

    // ================= ESP AUTO SCAN =================
    async function fetchESP() {
        try {
            const res = await fetch('/api/esp/fetch');
            const ids = await res.json();
            for (let id of ids) {
                // Directly use existing scan logic
                handleScan(String(id));
            }
        } catch (e) {
            console.log("ESP Fetch Error:", e);
        }
    }

    let espMode = false;
    let espInterval = null;
    const espBtn = document.getElementById('esp-toggle-btn');

    function loadEspState() {
        const saved = localStorage.getItem("esp_mode");
        if (saved === "ON") {
            enableESP();
        } else {
            disableESP();
        }
    }

    function enableESP() {
        espMode = true;
        localStorage.setItem("esp_mode", "ON");

        espBtn.innerText = "📡 ESP Mode: ON";
        espBtn.classList.remove("btn-outline-primary");
        espBtn.classList.add("btn-success");

        // Start polling
        espInterval = setInterval(fetchESP, 1000);

        setStatus("ESP Mode Activated", "success");
    }

    function disableESP() {
        espMode = false;
        localStorage.setItem("esp_mode", "OFF");

        espBtn.innerText = "📡 ESP Mode: OFF";
        espBtn.classList.remove("btn-success");
        espBtn.classList.add("btn-outline-primary");

        if (espInterval) {
            clearInterval(espInterval);
            espInterval = null;
        }

        setStatus("ESP Mode Disabled", "warning");
    }

    espBtn.addEventListener("click", () => {
        if (espMode) {
            disableESP();
        } else {
            enableESP();
        }
    });

    // POLLING START (every 1 sec)
    loadEspState();

    // Optional: Sound feedback on successful scan
    function beep() {
        const audio = new Audio('https://www.soundjay.com/buttons/sounds/button-3.mp3');
        audio.play();
    }

    // Optional: Visual flash effect on successful scan
    function flashScreen() {
        document.body.style.background = "#dcfce7";
        setTimeout(() => {
            document.body.style.background = "";
        }, 150);
    }

// --- AUTO FETCH PIPES LOGIC ---
    async function fetchChallanPipes(challan) {
        if (!challan) return;
        try {
            fetchChallanBtn.innerText = "⏳ Loading...";
            fetchChallanBtn.disabled = true;

            const res = await fetch('/api/dispatch/search_full/' + encodeURIComponent(challan));
            const data = await res.json();
            
            if (res.ok && data.success && data.data && data.data.items) {
                let added = 0;
                data.data.items.forEach(item => {
                    if (!scannedIds.has(item.id)) {
                        scannedItems.push(item);
                        scannedIds.add(item.id);
                        added++;
                    }
                });
                
                // Pre-fill vehicle and driver to match the original shipment
                if (data.data.meta) {
                    vehicleInput.value = data.data.meta.vehicle_no || vehicleInput.value;
                    driverMobileInput.value = data.data.meta.driver_mobile || driverMobileInput.value;
                }
                
                setStatus(`✅ Auto-Fetched ${added} pipes from Challan ${challan}.`, 'success');
                saveState();
                renderTable();
            } else {
                alert("Challan not found or no pipes associated with it.");
            }
        } catch(e) {
            alert("Error fetching challan details: " + e.message);
        } finally {
            fetchChallanBtn.innerText = "📥 Fetch Pipes";
            fetchChallanBtn.disabled = false;
        }
    }

    fetchChallanBtn.addEventListener('click', () => {
        fetchChallanPipes(challanNoInput.value.trim());
    });

    challanNoInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && isReturnMode) {
            e.preventDefault();
            fetchChallanPipes(challanNoInput.value.trim());
        }
    });
});
function speakResponse(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); // पहले की आवाज़ बंद करें
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'hi-IN'; // 🇮🇳 भाषा को हिंदी में सेट करें
        utterance.rate = 1.1;     // हिंदी के लिए स्पीड थोड़ी सामान्य रखें
        utterance.pitch = 1.0; 
        window.speechSynthesis.speak(utterance);
    }
}
 