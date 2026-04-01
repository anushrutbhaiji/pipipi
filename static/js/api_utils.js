// --- GLOBAL VARIABLES ---
let AUTH_HEADER = {};
let pollingInterval = null;
let latestStockData = []; 
let currentReportType = '';
let currentStockView = 'size'; // Default view: By Brand
let currentInventoryData = []; 
let isDetailMode = false;      
let currentPage = 1;
let isDeleteMode = false;

// --- AUTHENTICATION ---
async function authenticate(isAuto = false) {
    let headers = {};
    if(isAuto) {
        headers = { 'Authorization': 'Basic ' + sessionStorage.getItem('admin_token') };
    } else {
        const pass = document.getElementById('adminPass').value;
        headers = { 'Authorization': 'Basic ' + btoa("admin:" + pass) };
    }

    try {
        const res = await fetch('/api/stats_summary', { headers });
        if (res.status === 401) {
            if (!isAuto) {
                document.getElementById('loginError').style.display = 'block';
                document.getElementById('adminPass').value = '';
                document.getElementById('adminPass').focus();
                showToast("Wrong Password!", true);
            }
            return;
        }
     
        if(!isAuto) {
            const pass = document.getElementById('adminPass').value;
            sessionStorage.setItem('admin_token', btoa("admin:" + pass));
        }
        document.getElementById('loginError').style.display = 'none';
        AUTH_HEADER = headers;
        document.getElementById('loginOverlay').style.display = 'none';
        document.getElementById('mainDashboard').style.display = 'block';
        
        const data = await res.json();
        updateDashboardUI(data); // Initial Load
        
        const btnSize = document.getElementById('btn-view-size');
        const btnBrand = document.getElementById('btn-view-brand');
        if (btnSize && btnBrand) {
            btnBrand.classList.remove('active');
            btnSize.classList.add('active');
        }
        const requestedTab = sessionStorage.getItem('admin_active_tab');
        if (requestedTab) {
            showTab(requestedTab);
            sessionStorage.removeItem('admin_active_tab');
        } else {
            checkUrlFilters();
        }
        startLiveUpdates();
    } catch(e) { console.error(e); if(!isAuto) showToast("Connection Error", true); }
}

// --- UTILITIES ---
function printContent(html, title, subtitle='') {
    const win = window.open('', '', 'height=800,width=1000');
    win.document.write(`<html><head><title>${title}</title><style>@page { size: A4; margin: 20mm; } body { font-family: sans-serif; color: #333; } table { width: 100%; border-collapse: collapse; font-size: 12px; } th, td { border: 1px solid #ddd; padding: 8px; text-align: left; } th { background-color: #f8fafc; } h1 { text-align: center; font-size: 20px; }</style></head><body><h1>${title}</h1><p style="text-align:center;">${subtitle}</p>${html}</body></html>`);
    win.document.close();
    setTimeout(() => { win.print(); }, 500);
}

async function downloadFileWithAuth(url, filename) {
    try {
        const res = await fetch(url, { headers: AUTH_HEADER });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(`Download failed: ${err.error || res.statusText}`);
        }
        const blob = await res.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    } catch (e) {
        console.error(e);
        showToast(e.message, true);
    }
}

function downloadBackup() { downloadFileWithAuth('/api/backup', 'pvc_factory.db'); }
async function cleanData() { if(confirm("⚠️ Delete 30+ day old data?")) await fetch('/api/cleanup', { method: 'POST', headers: AUTH_HEADER }); showToast("Cleanup Done"); }