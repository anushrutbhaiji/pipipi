/* ════════════════════════════════════════════
   STATE
════════════════════════════════════════════ */
let allPipes      = [];          
let scannedSet    = new Set();   
let extraArr      = [];          
let logArr        = [];          
let returnQueue   = [];          
let espTimer      = null;
let sessionStart  = Date.now();
let filterParams  = {};
let logIdCounter  = 0;

/* ════════════════════════════════════════════
   BOOT
════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  filterParams = Object.fromEntries(new URLSearchParams(location.search));
  const parts = [
    filterParams.pipe_name,
    filterParams.size,
    filterParams.color,
    filterParams.pressure ? filterParams.pressure + ' class' : null
  ].filter(Boolean);
  const label = parts.length ? '🔍 Verifying: ' + parts.join(' · ') : '🔍 Verifying: All in-stock pipes';
  document.getElementById('filterLabel').textContent = label;
  document.getElementById('resSub').textContent      = label;

  document.getElementById('scanInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); processScan(); }
  });
  document.getElementById('returnInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addReturn(); }
  });

  setInterval(tickTimer, 1000);
  loadPipes();
});

/* ════════════════════════════════════════════
   LOAD PIPES FROM API
════════════════════════════════════════════ */
async function loadPipes() {
  const p = new URLSearchParams(filterParams);
  p.set('status', 'stock');
  p.set('per_page', '5000');
  p.set('page', '1');

  try {
    const res  = await fetch('/api/verify/pipes?' + p.toString());
    const data = await res.json();
    allPipes   = data.items || [];

    if (!allPipes.length) {
      document.getElementById('pipeBody').innerHTML =
        '<div class="empty"><div class="icon">📭</div>No stock pipes found for this filter.</div>';
    } else {
      renderPipeList(allPipes);
    }
    updateStats();
  } catch(err) {
    document.getElementById('pipeBody').innerHTML =
      '<div class="empty" style="color:var(--red)"><div class="icon">❌</div>Failed to load. Check server connection.</div>';
  }
}

/* ════════════════════════════════════════════
   RENDER PIPE LIST
════════════════════════════════════════════ */
function renderPipeList(pipes) {
  const body = document.getElementById('pipeBody');
  if (!pipes.length) {
    body.innerHTML = '<div class="empty"><div class="icon">🔎</div>No results for search.</div>';
    document.getElementById('pipeCount').textContent = '0 pipes';
    return;
  }

  body.innerHTML = pipes.map(p => {
    const ok    = scannedSet.has(p.id);
    const extra = extraArr.includes(p.id);
    const stCls = ok ? 'state-scanned' : extra ? 'state-extra' : '';
    const tick  = ok ? '<div class="tick tick-ok">✓</div>'
                     : '<div class="tick tick-pending" style="font-size:0.65rem">#</div>';
    const badge = ok   ? '<span class="pipe-badge chip-green" style="background:var(--green-dim);color:var(--green);border-radius:8px;padding:1px 7px;font-size:0.65rem;font-weight:700">SCANNED</span>'
                : extra ? '<span class="pipe-badge chip-yellow">EXTRA</span>' : '';
    return `
    <div class="pipe-row ${stCls}" id="pr-${p.id}">
      <div id="tk-${p.id}">${tick}</div>
      <div class="pipe-info">
        <div class="pipe-id">ID #${p.id} ${badge}</div>
        <div class="pipe-meta">${p.pipe_name||'—'} · ${p.size||'—'} · ${p.color||'—'} · ${p.weight_g||'—'}g · ${p.batch||'—'}</div>
      </div>
      <div style="font-size:0.75rem;color:var(--text-light);flex-shrink:0;font-weight:500;">
        ${(p.created_at||'').substring(0,10)}
      </div>
    </div>`;
  }).join('');

  document.getElementById('pipeCount').textContent = pipes.length + ' pipes';
}

/* ════════════════════════════════════════════
   FILTER SEARCH
════════════════════════════════════════════ */
function filterList(q) {
  const lo = q.toLowerCase();
  const filtered = allPipes.filter(p =>
    String(p.id).includes(lo) ||
    (p.pipe_name||'').toLowerCase().includes(lo) ||
    (p.batch||'').toLowerCase().includes(lo) ||
    (p.operator||'').toLowerCase().includes(lo) ||
    (p.size||'').toLowerCase().includes(lo)
  );
  renderPipeList(filtered);
}

/* ════════════════════════════════════════════
   SCAN PROCESSING (Upgraded with API Fetch)
════════════════════════════════════════════ */
async function processScan() {
  const inp = document.getElementById('scanInput');
  const raw = inp.value.trim();
  inp.value = '';
  inp.focus();
  if (!raw) return;

  let id = null;
  try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.id) id = parseInt(parsed.id, 10);
  } catch(e) {}
  
  if (!id) {
      const numMatch = raw.match(/\d+/);
      if (numMatch) id = parseInt(numMatch[0], 10);
  }

  if (!id || isNaN(id)) {
    flashInput('err');
    addLog(raw, 'INVALID', '⚠ Invalid scan format');
    return;
  }

  if (scannedSet.has(id) || extraArr.includes(id)) {
    flashInput('err');
    addLog('#' + id, 'DUP', '🔁 Already scanned in this session');
    beep(false);
    return;
  }

  const pipe = allPipes.find(p => p.id === id);

  if (pipe) {
    scannedSet.add(id);
    markRow(id, 'ok');
    addLog('#' + id, 'OK', `✅ ${pipe.pipe_name||''} ${pipe.size||''} ${pipe.color||''}`);
    flashInput('ok');
    beep(true);
    document.getElementById('lastScanInfo').textContent = `Last: #${id}`;
    logArr.push(id);
    updateStats();
  } else {
    flashInput('err');
    beep(false);
    addLog('#' + id, 'EXTRA', '⏳ Fetching unknown pipe details...');
    
    try {
        const token = localStorage.getItem('admin_token');
        const headers = token ? { 'Authorization': 'Basic ' + token } : {};
        
        const res = await fetch(`/api/labels/${id}`, { headers: headers });
        if (!res.ok) throw new Error("Not found");
        
        const item = await res.json();
        extraArr.push(id);
        
        let errText = "⚠ Not in Filter";
        let actionBtn = ""; // ✨ NEW: Prepare the button
        
        if(item.dispatched_at) {
            errText = "🚨 DISPATCHED PIPE!";
            // ✨ NEW: Create the Quick Return button for the log
            actionBtn = `<button class="btn btn-warning btn-sm mt-2 w-100" style="padding: 4px; font-weight: bold;" onclick="quickReturn(${id}, this.closest('.log-entry'))">📥 Quick Return to Stock</button>`;
        }
        
        document.getElementById('logBody').firstChild.remove();
        
        // ✨ NEW: Pass the actionBtn to the log
        addLog('#' + id, 'EXTRA', `${errText} (${item.pipe_name} ${item.size})`, actionBtn);
        
        const body = document.getElementById('pipeBody');
        const div  = document.createElement('div');
        div.className = 'pipe-row state-extra';
        div.id = 'pr-' + id;
        div.innerHTML = `
          <div class="tick tick-extra">⚠</div>
          <div class="pipe-info">
            <div class="pipe-id">ID #${id} <span style="font-size:0.7rem;color:var(--yellow);margin-left:6px">[${errText}]</span></div>
            <div class="pipe-meta">${item.pipe_name} · ${item.size} · ${item.color}</div>
          </div>`;
        body.insertBefore(div, body.firstChild);

    } catch(err) {
        console.error(err);
        addLog('#' + id, 'INVALID', '❌ Pipe not found');
    }
    
    logArr.push(id);
    updateStats();
  }
}

function markRow(id, state) {
  const row  = document.getElementById('pr-' + id);
  const tkWr = document.getElementById('tk-' + id);
  if (!row || !tkWr) return;

  row.classList.add('state-scanned');
  tkWr.innerHTML = '<div class="tick tick-ok">✓</div>';
  row.scrollIntoView({ behavior:'smooth', block:'nearest' });
}

/* ════════════════════════════════════════════
   UNDO
════════════════════════════════════════════ */
function undoLast() {
  if (!logArr.length) return;
  const lastId = logArr.pop();

  if (scannedSet.has(lastId)) {
    scannedSet.delete(lastId);
    const row  = document.getElementById('pr-' + lastId);
    const tkWr = document.getElementById('tk-' + lastId);
    if (row)  row.classList.remove('state-scanned');
    if (tkWr) tkWr.innerHTML = '<div class="tick tick-pending">#</div>';
  } else {
    const ei = extraArr.indexOf(lastId);
    if (ei > -1) {
      extraArr.splice(ei, 1);
      document.getElementById('pr-' + lastId)?.remove();
    }
  }

  const logBody = document.getElementById('logBody');
  if (logBody.firstChild?.classList?.contains('log-entry'))
    logBody.firstChild.remove();

  updateStats();
}

/* ════════════════════════════════════════════
   SCAN LOG
════════════════════════════════════════════ */
function addLog(display, type, msg, extraHtml = '') {
  const logBody = document.getElementById('logBody');
  if (logBody.querySelector('.empty')) logBody.innerHTML = '';

  const tagClass = {OK:'tag-ok',DUP:'tag-dup',EXTRA:'tag-extra',INVALID:'tag-invalid'}[type] || 'tag-invalid';
  const el = document.createElement('div');
  el.className = 'log-entry';
  el.innerHTML = `
    <div class="log-row">
      <div><span class="log-id">${display}</span>
        <span class="log-tag ${tagClass}">${type}</span></div>
      <span class="log-time">${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="log-msg">${msg}</div>
    ${extraHtml}`; // ✨ NEW: Injects the button if it exists
  logBody.insertBefore(el, logBody.firstChild);
}
function clearLog() {
  document.getElementById('logBody').innerHTML =
    '<div class="empty"><div class="icon">📡</div>Log cleared</div>';
}

/* ════════════════════════════════════════════
   STATS
════════════════════════════════════════════ */
function updateStats() {
  const exp     = allPipes.length;
  const scanned = scannedSet.size;
  const missing = Math.max(0, exp - scanned);
  const extra   = extraArr.length;
  const pct     = exp > 0 ? Math.round((scanned / exp) * 100) : 0;

  document.getElementById('sExp').textContent     = exp;
  document.getElementById('sScanned').textContent = scanned;
  document.getElementById('sMissing').textContent = missing;
  document.getElementById('sExtra').textContent   = extra;

  document.getElementById('bbCount').textContent   = scanned;
  document.getElementById('bbMissing').textContent = missing;
  document.getElementById('bbExtra').textContent   = extra;

  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progLabel').textContent = `${scanned} / ${exp} scanned`;
  document.getElementById('progPct').textContent   = pct + '%';
}

/* ════════════════════════════════════════════
   ESP MODE
════════════════════════════════════════════ */
async function fetchESP() {
    try {
        const token = localStorage.getItem('admin_token');
        const headers = token ? { 'Authorization': 'Basic ' + token } : {};
        const res = await fetch('/api/esp/fetch', { headers: headers });
        const ids = await res.json();
        for (let id of ids) {
            document.getElementById('scanInput').value = String(id);
            processScan();
        }
    } catch (e) { }
}

function toggleEsp(el) {
  const status = document.getElementById('espStatus');
  if (el.checked) {
    espTimer = setInterval(fetchESP, 1000);
    status.classList.add('active');
  } else {
    clearInterval(espTimer); espTimer = null;
    status.classList.remove('active');
  }
}

/* ════════════════════════════════════════════
   SESSION TIMER
════════════════════════════════════════════ */
function tickTimer() {
  const sec = Math.floor((Date.now() - sessionStart) / 1000);
  const mm  = String(Math.floor(sec / 60)).padStart(2, '0');
  const ss  = String(sec % 60).padStart(2, '0');
  document.getElementById('sessionTimer').textContent = `⏱ ${mm}:${ss}`;
}

function resetSession() {
  if (!confirm('Reset session? All scans will be lost.')) return;
  scannedSet.clear();
  extraArr.length = 0;
  logArr.length   = 0;
  sessionStart    = Date.now();
  renderPipeList(allPipes);
  clearLog();
  updateStats();
}

/* ════════════════════════════════════════════
   RESULTS MODAL
════════════════════════════════════════════ */
function openResults() {
  const missingPipes = allPipes.filter(p => !scannedSet.has(p.id));
  const scannedPipes = allPipes.filter(p =>  scannedSet.has(p.id));

  document.getElementById('rScanned').textContent  = scannedPipes.length;
  document.getElementById('rMissing').textContent  = missingPipes.length;
  document.getElementById('rExtra').textContent    = extraArr.length;
  document.getElementById('missBadge').textContent = missingPipes.length;
  document.getElementById('extraBadge').textContent= extraArr.length;
  document.getElementById('scannedBadge').textContent = scannedPipes.length;

  document.getElementById('missingTable').innerHTML = missingPipes.length
    ? buildTable(missingPipes, 'var(--red)')
    : '<div class="empty" style="padding:16px;color:var(--green)">✅ All pipes physically accounted for!</div>';

  if (extraArr.length) {
    const rows = extraArr.map(id =>
      `<tr><td>#${id}</td><td style="color:var(--yellow);font-weight:600;">⚠ Not in Filter</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>`
    ).join('');
    document.getElementById('extraTable').innerHTML =
      `<table class="mt"><thead><tr><th>ID</th><th>Status</th><th>Name</th><th>Size</th><th>Color</th><th>Weight</th></tr></thead><tbody>${rows}</tbody></table>`;
  } else {
    document.getElementById('extraTable').innerHTML =
      '<div class="empty" style="padding:14px;color:var(--text-light)">No extra pipes scanned.</div>';
  }

  document.getElementById('scannedTable').innerHTML = scannedPipes.length
    ? buildTable(scannedPipes, 'var(--green)')
    : '<div class="empty" style="padding:14px;color:var(--text-light)">Nothing scanned yet.</div>';

  document.getElementById('resultsOverlay').classList.add('open');
}

function closeResults() {
  document.getElementById('resultsOverlay').classList.remove('open');
}

function buildTable(pipes, color) {
  const rows = pipes.map(p => `
    <tr>
      <td style="color:${color};font-weight:700">#${p.id}</td>
      <td>${p.pipe_name||'—'}</td>
      <td>${p.size||'—'}</td>
      <td>${p.color||'—'}</td>
      <td>${p.weight_g||'—'}g</td>
      <td>${p.batch||'—'}</td>
    </tr>`).join('');
  return `<table class="mt">
    <thead><tr><th>ID</th><th>Name</th><th>Size</th><th>Color</th><th>Weight</th><th>Batch</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

async function saveVoucher() {
  const btn = document.getElementById('saveBtn');
  btn.textContent = '⏳ Saving…';
  btn.disabled = true;

  const missingPipes = allPipes.filter(p => !scannedSet.has(p.id));
  const scannedPipes = allPipes.filter(p =>  scannedSet.has(p.id));

  try {
    const res = await fetch('/api/verify/voucher', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filter        : filterParams,
        expected_ids  : allPipes.map(p => p.id),
        scanned_ids   : scannedPipes.map(p => p.id),
        missing_ids   : missingPipes.map(p => p.id),
        extra_ids     : [...extraArr],
        notes         : document.getElementById('verifyNotes').value
      })
    });
    const data = await res.json();
    if (data.success) {
      closeResults();
      toast(`✅ Voucher #${data.voucher_id} saved successfully!`, 'ok');
    } else {
      toast('❌ Save failed: ' + (data.message || 'Unknown'), 'err');
    }
  } catch { toast('❌ Network error — check server', 'err'); }
  finally {
    btn.textContent = '💾 SAVE VERIFICATION VOUCHER';
    btn.disabled = false;
  }
}

/* ════════════════════════════════════════════
   RETURN MODAL
════════════════════════════════════════════ */
function openReturn() {
  returnQueue = [];
  renderReturnList();
  document.getElementById('returnOverlay').classList.add('open');
  setTimeout(() => document.getElementById('returnInput').focus(), 80);
}
function closeReturn() {
  document.getElementById('returnOverlay').classList.remove('open');
}

function addReturn() {
  const inp = document.getElementById('returnInput');
  const raw = inp.value.trim();
  inp.value = ''; inp.focus();
  if (!raw) return;
  let id = null;
  try { id = parseInt(JSON.parse(raw).id); } catch { id = parseInt(raw); }
  if (!id || isNaN(id) || returnQueue.includes(id)) return;
  returnQueue.push(id);
  renderReturnList();
}

function renderReturnList() {
  const el = document.getElementById('returnList');
  document.getElementById('returnQtyLabel').textContent = returnQueue.length;
  if (!returnQueue.length) {
    el.innerHTML = '<div class="empty" style="padding:20px"><div class="icon">📭</div>No pipes queued</div>';
    return;
  }
  el.innerHTML = returnQueue.map((id, i) => `
    <div class="return-item">
      <span style="font-weight:700">ID #${id}</span>
      <button onclick="returnQueue.splice(${i},1);renderReturnList();"
        style="background:none;border:none;color:var(--red);cursor:pointer;font-size:1.2rem;font-weight:bold;">✕</button>
    </div>`).join('');
}

async function submitReturn() {
  if (!returnQueue.length) return;
  try {
    const res  = await fetch('/api/returns/create', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ items: returnQueue.map(id => ({ id })) })
    });
    const data = await res.json();
    if (data.success) {
      closeReturn();
      toast('↩ ' + data.message, 'ok');
      await loadPipes(); // Refresh list
    } else {
      toast('❌ Return failed: ' + (data.message||''), 'err');
    }
  } catch { toast('❌ Network error', 'err'); }
}

/* ════════════════════════════════════════════
   HELPERS
════════════════════════════════════════════ */
function flashInput(type) {
  const inp = document.getElementById('scanInput');
  inp.classList.remove('flash-ok', 'flash-err');
  void inp.offsetWidth;
  inp.classList.add(type === 'ok' ? 'flash-ok' : 'flash-err');
  setTimeout(() => inp.classList.remove('flash-ok', 'flash-err'), 500);
}

function beep(ok) {
  try {
    const ctx  = new (window.AudioContext || window.webkitAudioContext)();
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = ok ? 1000 : 200;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
    osc.start(); osc.stop(ctx.currentTime + 0.18);
  } catch {}
}

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

/* ════════════════════════════════════════════
   QUICK RETURN LOGIC
════════════════════════════════════════════ */
async function quickReturn(id, logElement) {
    if (!confirm(`Are you sure you want to return Pipe #${id} back to stock?`)) return;
    
    try {
        const token = localStorage.getItem('admin_token');
        const headers = token ? { 'Authorization': 'Basic ' + token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
        
        const res = await fetch('/api/returns/create', {
            method: 'POST', 
            headers: headers,
            body: JSON.stringify({ items: [{ id: id }] }) // Send just this one pipe
        });
        const d = await res.json();
        
        if (d.success) {
            toast(`✅ Pipe #${id} is back in stock!`, 'ok');
            
            // 1. Update the log entry visually to show success
            if (logElement) {
                logElement.querySelector('.log-msg').innerHTML = `✅ Restocked Successfully!`;
                logElement.querySelector('.log-tag').className = 'log-tag tag-ok';
                logElement.querySelector('.log-tag').innerText = 'RESTOCKED';
                
                // Remove the button so it can't be clicked twice
                const btn = logElement.querySelector('button');
                if (btn) btn.remove();
            }

            // 2. Update the red warning on the pipe row list
            const pipeRow = document.getElementById('pr-' + id);
            if (pipeRow) {
                const badge = pipeRow.querySelector('.pipe-id span');
                if (badge) {
                    badge.innerText = "[RESTOCKED]";
                    badge.style.color = "var(--green)";
                }
            }
            
        } else {
            toast("Error: " + d.message, 'err');
        }
    } catch(e) {
        toast("Connection error: " + e.message, 'err');
    }
}