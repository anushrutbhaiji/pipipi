import os

# --- 1. DEFINE FILE CONTENTS ---

# REFACTORED APP.PY
code_app = r'''import os
import csv
import io
from flask import Flask, render_template, request, jsonify, send_file, Response
import services          # Our new Logic Layer
import printer_backend   # Our new Hardware Layer

app = Flask(__name__)
ADMIN_PASS = "admin123"

# --- VIEWS ---
@app.route('/')
def index(): return render_template('generate.html')

@app.route('/scan')
def scan(): return render_template('scan.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

# --- API ---
@app.route('/api/labels', methods=['POST'])
def create_label():
    d = request.json
    # 1. Save to DB (Service Layer)
    label = services.create_label_in_db(d)
    
    # 2. Prepare for Response
    # Pass 'pressure' back to frontend so it can be sent to print route later
    label['pressure'] = d.get('pressure', '') 
    
    # 3. Generate QR for UI
    qr_img = services.generate_qr_for_label(label['id'], label['created_at'])
    
    return jsonify({"success": True, "label": label, "qr_image": qr_img})

@app.route('/api/print', methods=['POST'])
def trigger_print():
    req = request.json
    label_id = req.get('id')
    pressure = req.get('pressure', '') # Get pressure from UI (not in DB)
    
    label = services.get_label_by_id(label_id)
    if not label: return jsonify({"success": False}), 404
    
    # Inject pressure for the printer
    label_for_print = label.copy()
    label_for_print['pressure'] = pressure
    
    success, msg = printer_backend.silent_print_label(label_for_print)
    if success: services.mark_printed(label_id)
    
    return jsonify({"success": success, "message": msg})

@app.route('/api/labels/<int:id>', methods=['GET'])
def get_label(id):
    lbl = services.get_label_by_id(id)
    return jsonify(lbl) if lbl else (jsonify({"error": "Not found"}), 404)

@app.route('/api/dispatch', methods=['POST'])
def mark_dispatch():
    services.mark_dispatched(request.json['id'])
    return jsonify({"success": True})

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    data = services.fetch_inventory_data(request.args)
    return jsonify(data)

@app.route('/api/stats_summary', methods=['GET'])
def get_stats_summary():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(services.get_stats())

@app.route('/api/export', methods=['GET'])
def export_excel():
    data = services.fetch_inventory_data(request.args)
    si = io.StringIO(); cw = csv.writer(si)
    
    # Simple dynamic CSV generation based on first row keys
    if data:
        cw.writerow(data[0].keys())
        for row in data: cw.writerow(row.values())
    else:
        cw.writerow(["No Data"])

    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=report.csv"})

@app.route('/api/backup')
def backup(): return send_file(services.DB_NAME, as_attachment=True)

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    services.run_cleanup()
    return jsonify({"success": True})

if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    print("System Running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
'''

# NEW SERVICES.PY
code_services = r'''import sqlite3
import datetime
import json
import io
import qrcode
import base64

DB_NAME = "pvc_factory.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipe_name TEXT, size TEXT, color TEXT, weight_g REAL,
                length_m TEXT, batch TEXT, operator TEXT,
                created_at TEXT, printed_at TEXT, dispatched_at TEXT, dispatched_by TEXT
            )
        """)
init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def import_base64(data):
    return base64.b64encode(data).decode('utf-8')

# --- CORE LOGIC ---
def create_label_in_db(data):
    created_at = datetime.datetime.now().isoformat()
    length_m = data.get('length_m', '6m')
    batch = data.get('batch', 'BATCH-001')
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Pressure is NOT saved here, as requested
        cur.execute("INSERT INTO labels (pipe_name, size, color, weight_g, length_m, batch, operator, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (data['pipe_name'], data['size'], data['color'], data['weight_g'], length_m, batch, data.get('operator','OP-1'), created_at))
        new_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM labels WHERE id=?", (new_id,)).fetchone()
        return dict(row)

def generate_qr_for_label(label_id, created_at):
    qr_img = qrcode.make(json.dumps({"id": label_id, "created_at": created_at}))
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    return "data:image/png;base64," + import_base64(buf.getvalue())

def get_label_by_id(label_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM labels WHERE id=?", (label_id,)).fetchone()
    return dict(row) if row else None

def mark_printed(label_id):
    with get_db_connection() as conn:
        conn.execute("UPDATE labels SET printed_at=? WHERE id=?", (datetime.datetime.now().isoformat(), label_id))

def mark_dispatched(label_id, dispatched_by="Scanner"):
    with get_db_connection() as conn:
        conn.execute("UPDATE labels SET dispatched_at=?, dispatched_by=? WHERE id=?", 
                     (datetime.datetime.now().isoformat(), dispatched_by, label_id))

def run_cleanup():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM labels WHERE created_at < date('now', '-30 days')")

# --- FILTERING & REPORTING ---
def build_where_clause(args):
    conditions = ["1=1"]
    params = []
    
    if args.get('name'): conditions.append("pipe_name=?"); params.append(args.get('name'))
    if args.get('size'): conditions.append("size=?"); params.append(args.get('size'))
    if args.get('color'): conditions.append("color=?"); params.append(args.get('color'))
    
    if args.get('status') == 'stock': conditions.append("dispatched_at IS NULL")
    if args.get('status') == 'dispatched': conditions.append("dispatched_at IS NOT NULL")
    
    report_type = args.get('report_type', 'inventory')
    target_date = args.get('date')
    time_range = args.get('time_range')
    
    date_field = "dispatched_at" if report_type == 'dispatch' else "created_at"
    
    if target_date: 
        conditions.append(f"date({date_field}) = ?"); params.append(target_date)

    if time_range:
        try:
            start_h, end_h = map(int, time_range.split('-'))
            if start_h < end_h:
                conditions.append(f"CAST(strftime('%H', {date_field}) AS INT) >= ? AND CAST(strftime('%H', {date_field}) AS INT) < ?")
                params.append(start_h); params.append(end_h)
            else:
                conditions.append(f"(CAST(strftime('%H', {date_field}) AS INT) >= ? OR CAST(strftime('%H', {date_field}) AS INT) < ?)")
                params.append(start_h); params.append(end_h)
        except: pass

    if report_type == 'dispatch': conditions.append("dispatched_at IS NOT NULL")
    return " AND ".join(conditions), params

def fetch_inventory_data(args):
    where, params = build_where_clause(args)
    
    if args.get('grouped') == 'true':
        query = f"""
            SELECT pipe_name, size, color, COUNT(*) as count, SUM(weight_g) as total_weight, AVG(weight_g) as avg_weight 
            FROM labels WHERE {where} GROUP BY pipe_name, size, color ORDER BY pipe_name, size
        """
    else:
        query = f"SELECT * FROM labels WHERE {where} ORDER BY created_at DESC LIMIT 500"
        
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def get_stats():
    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        dispatched = conn.execute("SELECT COUNT(*) FROM labels WHERE dispatched_at IS NOT NULL").fetchone()[0]
        stock_summ = conn.execute("SELECT pipe_name, size, color, COUNT(*) as total, SUM(CASE WHEN dispatched_at IS NULL THEN 1 ELSE 0 END) as stock FROM labels GROUP BY pipe_name, size, color").fetchall()
        prod = conn.execute("SELECT date(created_at) as day, COUNT(*) as count FROM labels WHERE created_at >= date('now', '-7 days') GROUP BY day").fetchall()
    return {"total": total, "dispatched": dispatched, "stock": total - dispatched, "stock_summary": [dict(r) for r in stock_summ], "production_chart": [dict(r) for r in prod]}
'''

# NEW PRINTER_BACKEND.PY
code_printer = r'''import json
import qrcode
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont, ImageWin

def silent_print_label(label_data, printer_name=None):
    try:
        import win32print; import win32ui
        W, H = 640, 400
        img = Image.new('RGB', (W, H), 'white')
        draw = ImageDraw.Draw(img)
        
        # Fonts
        try:
            font_lg = ImageFont.truetype("arial.ttf", 45)
            font_md = ImageFont.truetype("arial.ttf", 30)
            font_sm = ImageFont.truetype("arial.ttf", 22)
            font_xl = ImageFont.truetype("arial.ttf", 55) # For Pressure
        except:
            font_lg = font_md = font_sm = font_xl = ImageFont.load_default()

        # Text Info
        draw.text((20, 10), str(label_data['pipe_name']), font=font_lg, fill="black")
        draw.text((20, 65), f"{label_data['size']} | {label_data['color']}", font=font_md, fill="black")
        draw.text((20, 110), f"Wt: {label_data['weight_g']} Kg", font=font_lg, fill="black")
        draw.text((20, 180), f"Batch: {label_data['batch']}", font=font_sm, fill="black") 
        draw.text((20, 210), f"Op: {label_data['operator']}", font=font_sm, fill="black")
        draw.text((220, 210), f"Time: {label_data['created_at'][11:16]}", font=font_sm, fill="black")

        # --- NEW: PRESSURE CLASS PRINTING ---
        pressure_val = label_data.get('pressure', '')
        if pressure_val:
            # Draw Pressure boldly on the right side
            draw.text((280, 60), pressure_val, font=font_xl, fill="black")

        # QR Code
        qr = qrcode.make(json.dumps({"id": label_data['id']}))
        qr = qr.resize((160, 160))
        img.paste(qr, (460, 20))

        # Barcode
        try:
            barcode_class = barcode.get_barcode_class('code128')
            my_barcode = barcode_class(str(label_data['id']), writer=ImageWriter())
            buffer = io.BytesIO()
            my_barcode.write(buffer, options={"write_text": True, "font_size": 10, "module_height": 8.0})
            buffer.seek(0)
            barcode_img = Image.open(buffer).resize((400, 100))
            img.paste(barcode_img, (120, 280))
        except: pass

        # Windows Printing Logic
        if not printer_name: printer_name = win32print.GetDefaultPrinter()
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        hDC.StartDoc("PVC Label")
        hDC.StartPage()
        ImageWin.Dib(img).draw(hDC.GetHandleOutput(), (0, 0, W, H))
        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()
        return True, "Printed"
    except Exception as e: 
        return False, str(e)
'''

# ORIGINAL LAYOUT.HTML (Preserved)
code_layout = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PVC Factory Pro</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Modern Palette */
            --primary: #2563eb;       /* Bright Royal Blue */
            --primary-dark: #1d4ed8;
            --secondary: #64748b;     /* Slate Grey */
            --success: #10b981;       /* Emerald */
            --danger: #ef4444;        /* Red */
            --warning: #f59e0b;       /* Amber */
            --bg-body: #f8fafc;       /* Very Light Blue-Grey */
            --bg-card: #ffffff;
            --text-main: #0f172a;     /* Deep Navy */
            --text-light: #64748b;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.1);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
            --radius: 16px;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }

        /* --- Navbar --- */
        .navbar {
            background: var(--bg-card);
            padding: 1rem 2rem;
            box-shadow: var(--shadow-sm);
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .brand {
            font-size: 1.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary), #3b82f6);
            /* --- FIXED: Added standard property here --- */
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        .nav-links { display: flex; gap: 1rem; }
        .nav-item {
            text-decoration: none;
            color: var(--text-light);
            font-weight: 600;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            transition: all 0.2s;
        }
        .nav-item:hover { background: #eff6ff; color: var(--primary); }
        .nav-item.active { background: #eff6ff; color: var(--primary); }

        /* --- Layout --- */
        .container {
            max-width: 1100px;
            margin: 2rem auto;
            padding: 0 1.5rem;
        }
        .card {
            background: var(--bg-card);
            border-radius: var(--radius);
            padding: 2rem;
            box-shadow: var(--shadow-md);
            border: 1px solid #f1f5f9;
            transition: transform 0.2s;
            margin-bottom: 2rem;
        }
        /* .card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); } */

        h2, h3 { margin-top: 0; color: var(--text-main); letter-spacing: -0.5px; }

        /* --- Forms & Buttons --- */
        label { display: block; margin-bottom: 0.5rem; font-weight: 600; color: var(--text-light); font-size: 0.9rem; }
        
        input, select {
            width: 100%;
            padding: 0.9rem;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            font-size: 1rem;
            margin-bottom: 1.2rem;
            box-sizing: border-box;
            transition: all 0.2s;
            font-family: inherit;
        }
        input:focus { border-color: var(--primary); outline: none; box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1); }
        
        .big-input { 
            font-size: 2rem; 
            padding: 1rem; 
            font-weight: 700; 
            color: var(--primary); 
            text-align: center;
            letter-spacing: 1px;
        }

        .btn {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 12px;
            font-size: 1rem;
            cursor: pointer;
            font-weight: 600;
            width: 100%;
            transition: all 0.2s;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3);
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4); }
        .btn:active { transform: translateY(0); }
        .btn-outline { background: white; border: 2px solid #e2e8f0; color: var(--text-main); box-shadow: none; }
        .btn-outline:hover { border-color: var(--text-main); background: #f8fafc; }

        .grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 2rem; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }

        /* --- Toast --- */
        #toast {
            visibility: hidden;
            min-width: 300px;
            background-color: var(--text-main);
            color: #fff;
            text-align: center;
            border-radius: 50px;
            padding: 16px;
            position: fixed;
            z-index: 1000;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            box-shadow: var(--shadow-lg);
            font-weight: 500;
        }
        #toast.show { visibility: visible; animation: fadein 0.5s, fadeout 0.5s 2.5s; }
        @keyframes fadein { from {bottom: 0; opacity: 0;} to {bottom: 30px; opacity: 1;} }
        @keyframes fadeout { from {bottom: 30px; opacity: 1;} to {bottom: 0; opacity: 0;} }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="brand">🏭 PVC PRO</div>
        <div class="nav-links">
            <a href="/" class="nav-item {% if request.path == '/' %}active{% endif %}">Generate</a>
            <a href="/scan" class="nav-item {% if request.path == '/scan' %}active{% endif %}">Scan</a>
            <a href="/admin" class="nav-item {% if request.path == '/admin' %}active{% endif %}">Admin</a>
        </div>
    </nav>

    <div class="container">
        {% block content %}{% endblock %}
    </div>

    <div id="toast">Ready</div>

    <script>
        function showToast(msg, isError = false) {
            const x = document.getElementById("toast");
            x.textContent = msg;
            x.style.backgroundColor = isError ? "#ef4444" : "#10b981";
            x.className = "show";
            setTimeout(() => { x.className = x.className.replace("show", ""); }, 3000);
        }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
'''

# ORIGINAL SCAN.HTML (Preserved)
code_scan = r'''{% extends "layout.html" %}

{% block content %}
<div class="card" style="max-width: 600px; margin: 0 auto; text-align: center;">
    <h2>🤳 Universal Scanner</h2>
    
    <div style="margin: 20px 0;">
        <input type="text" id="scannerInput" class="big-input" placeholder="Click & Scan Barcode" autocomplete="off" autofocus>
        <p style="color: #64748b; margin-top: 10px; font-size: 0.9rem;">
            🖥️ <strong>USB Gun:</strong> Seedha scan karo (Click box first)<br>
            📱 <strong>Phone:</strong> Camera neeche use karo
        </p>
    </div>

    <div style="border: 2px dashed #cbd5e1; border-radius: 12px; padding: 10px; background: #f8fafc;">
        <div id="reader"></div>
        <p style="margin-top:5px; color:#64748b; font-size:0.8rem;">Supports: QR & Barcode (Code128)</p>
    </div>
    
    <div id="scanResult" style="display: none; margin-top: 20px; background: #f0fdf4; border: 2px solid #bbf7d0; padding: 2rem; border-radius: 16px; text-align: left;">
        <h3 style="color: #166534; margin-bottom: 1rem;">✅ Match Found</h3>
        <div style="font-size: 1.2rem;">ID: #<span id="r_id"></span></div>
        <div style="font-size: 1.5rem; font-weight: 800; color: #1e293b;"><span id="r_name"></span></div>
        <div style="color: #64748b; margin-bottom: 1rem;"><span id="r_size"></span> • <span id="r_weight"></span>g</div>
        
        <div style="padding: 10px; background: white; border-radius: 8px; text-align: center; font-weight: bold; border: 2px solid green; color: green;" id="r_status_box">
            CHECKING...
        </div>

        <button class="btn" onclick="dispatchItem()" style="background: #166534; margin-top: 1rem;" id="dispatchBtn">MARK DISPATCHED</button>
    </div>
</div>

<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>

<script>
    const inputField = document.getElementById('scannerInput');
    let currentId = null;

    // --- A. USB SCANNER LOGIC ---
    inputField.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            handleScanData(inputField.value.trim());
            inputField.value = '';
        }
    });

    // Auto-focus on input for USB Gun
    document.addEventListener('click', (e) => {
        // Agar hum camera buttons par click nahi kar rahe, tabhi focus karein
        if(e.target.tagName !== 'BUTTON' && e.target.id !== 'html5-qrcode-button-camera-stop') {
             if(document.activeElement !== inputField) inputField.focus();
        }
    });

    // --- B. PHONE CAMERA LOGIC ---
    function onCameraScanSuccess(decodedText, decodedResult) {
        // Camera ko thoda break do taaki baar baar scan na kare
        // html5QrcodeScanner.pause(); 
        handleScanData(decodedText);
    }

    // --- C. COMMON DATA HANDLER ---
    function handleScanData(text) {
        if(!text) return;
        
        let idToFetch = text;

        // Try to detect if it is JSON (QR Code) or Plain Text (Barcode)
        try {
            const json = JSON.parse(text);
            if(json.id) idToFetch = json.id;
        } catch(e) {
            // Agar JSON fail hua, matlab ye seedha Barcode ID hai (e.g. "15")
            // Do nothing, use text as is.
        }

        fetchDetails(idToFetch);
    }

    // --- D. API FETCH DETAILS ---
    async function fetchDetails(id) {
        const res = await fetch(`/api/labels/${id}`);
        if(res.ok) {
            const data = await res.json();
            currentId = data.id;
            
            // Show Result UI
            document.getElementById('scanResult').style.display = 'block';
            document.getElementById('r_id').textContent = String(data.id).padStart(4,'0');
            document.getElementById('r_name').textContent = data.pipe_name;
            document.getElementById('r_size').textContent = `${data.size} | ${data.color}`;
            document.getElementById('r_weight').textContent = data.weight_g;
            
            // Status Check
            const box = document.getElementById('r_status_box');
            const btn = document.getElementById('dispatchBtn');
            
            if(data.dispatched_at) {
                box.innerText = "ALREADY DISPATCHED";
                box.style.color = "red";
                box.style.borderColor = "red";
                btn.disabled = true;
                btn.innerText = "Already Sent";
                showToast("⚠️ Already Dispatched!", true);
            } else {
                box.innerText = "IN STOCK";
                box.style.color = "green";
                box.style.borderColor = "green";
                btn.disabled = false;
                btn.innerText = "MARK DISPATCHED";
                
                // Camera wale user ke liye scroll down karo
                document.getElementById('scanResult').scrollIntoView({behavior: "smooth"});
            }
        } else {
            showToast("❌ ID Not Found", true);
        }
    }

    // --- E. DISPATCH ACTION ---
    async function dispatchItem() {
        if(!currentId) return;
        const res = await fetch('/api/dispatch', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: currentId}) });
        if(res.ok) {
            showToast("✅ Item Dispatched!");
            document.getElementById('r_status_box').innerText = "DISPATCHED JUST NOW";
            document.getElementById('dispatchBtn').disabled = true;
            
            // Clear input and Refocus
            inputField.value = '';
            inputField.focus();
            
            // Agar camera paused tha to resume karo (Optional)
            // html5QrcodeScanner.resume();
        }
    }

    // --- F. CAMERA CONFIGURATION (QR + BARCODE) ---
    const html5QrcodeScanner = new Html5QrcodeScanner(
        "reader", 
        { 
            fps: 10, 
            qrbox: { width: 250, height: 150 }, // Barcode ke liye wide box
            formatsToSupport: [ 
                Html5QrcodeSupportedFormats.QR_CODE,
                Html5QrcodeSupportedFormats.CODE_128, // Ye hai Barcode support
                Html5QrcodeSupportedFormats.CODE_39 
            ]
        },
        /* verbose= */ false
    );
    html5QrcodeScanner.render(onCameraScanSuccess);
</script>
{% endblock %}
'''

# FIXED GENERATE.HTML (Original Styles + Pressure)
code_generate = r'''{% extends "layout.html" %}
{% block content %}
<style>
    .chip-container { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 2rem; }
    .chip { padding: 12px 20px; border: 2px solid #e2e8f0; border-radius: 12px; cursor: pointer; font-weight: 600; background: white; color: #64748b; flex: 1; text-align: center; min-width: 80px; }
    .chip.active { background: #eff6ff; color: var(--primary); border-color: var(--primary); }
    .section-label { font-size: 0.85rem; text-transform: uppercase; color: #94a3b8; font-weight: 700; margin-bottom: 10px; }
    
    /* --- FIXED LABEL PREVIEW STYLE --- */
    .preview-box { 
        background: #f1f5f9; border-radius: 16px; padding: 2rem; 
        display: flex; justify-content: center; align-items: center; 
        min-height: 300px; border: 2px dashed #cbd5e1; 
    }
    
    .label-visual {
        width: 400px; 
        height: 250px;
        background: white; 
        border: 3px solid #000;
        padding: 15px; 
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        font-family: Arial, sans-serif;
        display: grid;
        grid-template-columns: 2fr 1fr; /* Text takes 2 parts, QR takes 1 part */
        grid-template-rows: auto auto 1fr auto;
        gap: 5px;
        position: relative;
    }

    /* Left Side: Text Info */
    .lbl-header { grid-column: 1 / 2; grid-row: 1 / 2; align-self: start; }
    .lbl-brand { font-size: 26px; font-weight: 800; text-transform: uppercase; line-height: 1.1; word-wrap: break-word; }
    .lbl-detail { font-size: 18px; color: #333; margin-top: 5px; font-weight: 600; }
    
    /* Right Side: QR Code (Fixed Zone) */
    .lbl-qr-zone { 
        grid-column: 2 / 3; 
        grid-row: 1 / 3; 
        justify-self: end;
        width: 110px; 
        height: 110px; 
        border: 1px solid #eee; 
        background: #fafafa;
        display: flex; align-items: center; justify-content: center;
    }
    .lbl-qr-zone img { width: 100%; height: 100%; object-fit: contain; }

    /* Center: Weight */
    .lbl-weight-zone { 
        grid-column: 1 / 3; 
        grid-row: 3 / 4; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        font-size: 42px; 
        font-weight: 900; 
        color: #000;
        border-top: 2px solid #eee;
        border-bottom: 2px solid #eee;
        margin: 10px 0;
    }

    /* Bottom: Meta Data */
    .lbl-meta { 
        grid-column: 1 / 3; 
        grid-row: 4 / 5; 
        font-size: 13px; 
        color: #555; 
        display: flex; 
        justify-content: space-between;
        align-items: flex-end;
    }
</style>

<div class="grid">
    <div class="card">
        <h2 style="margin-bottom: 1.5rem;">New Label</h2>
        <form id="labelForm">
            <div class="section-label">Operator / Shift</div>
            <div class="chip-container" id="group-operator">
                <div class="chip active" onclick="select('operator', this, 'Shift-A')">Shift-A</div>
                <div class="chip" onclick="select('operator', this, 'Shift-B')">Shift-B</div>
                <div class="chip" onclick="select('operator', this, 'Night')">Night</div>
            </div>
            <input type="hidden" id="operator" value="Shift-A">

            <div class="section-label">Brand / Name</div>
            <div class="chip-container" id="group-name">
                <div class="chip active" onclick="select('name', this, 'Gangotry')">Gangotry</div>
                <div class="chip" onclick="select('name', this, 'UltraPlast')">UltraPlast</div>
                <div class="chip" onclick="select('name', this, 'KissanGreen')">KissanGreen</div>
                <div class="chip" onclick="select('name', this, 'Casing')">Casing</div>
            </div>
            <input type="hidden" id="pipe_name" value="Gangotry">

            <div class="section-label">Pressure Class</div>
            <div class="chip-container" id="group-pressure">
                <div class="chip active" onclick="select('pressure', this, '4kgf')">4 Kgf</div>
                <div class="chip" onclick="select('pressure', this, '6kgf')">6 Kgf</div>
                <div class="chip" onclick="select('pressure', this, '10kgf')">10 Kgf</div>
            </div>
            <input type="hidden" id="pressure" value="4kgf">

            <div class="section-label">Size (mm)</div>
            <div class="chip-container" id="group-size">
                <div class="chip active" onclick="select('size', this, '63mm')">63</div>
                <div class="chip" onclick="select('size', this, '75mm')">75</div>
                <div class="chip" onclick="select('size', this, '90mm')">90</div>
                <div class="chip" onclick="select('size', this, '110mm')">110</div>
                <div class="chip" onclick="select('size', this, '140mm')">140</div>
                <div class="chip" onclick="select('size', this, '160mm')">160</div>
                <div class="chip" onclick="select('size', this, '180mm')">180</div>
                <div class="chip" onclick="select('size', this, '200mm')">200</div>
            </div>
            <input type="hidden" id="size" value="63mm">

            <div class="section-label">Color</div>
            <div class="chip-container" id="group-color">
                <div class="chip active" onclick="select('color', this, 'Blue')">Blue</div>
                <div class="chip" onclick="select('color', this, 'Grey')">Grey</div>
            </div>
            <input type="hidden" id="color" value="Blue">

            <div class="section-label">Net Weight (Kg)</div>
            <input type="number" id="weight_g" class="big-input" placeholder="0.000" step="0.001" required autofocus oninput="updatePreview()">
            
            <button type="submit" class="btn" style="margin-top: 1rem;">PRINT LABEL (ENTER)</button>
        </form>
    </div>

    <div class="card" style="text-align: center;">
        <h3>Live Preview</h3>
        <div class="preview-box" id="previewArea">
            </div>
    </div>
</div>

{% block scripts %}
<script>
    // Initial Render
    window.onload = function() { updatePreview(); }

    function select(type, el, val) {
        // Handle name specifically or generic ID
        let inputId = (type === 'name') ? 'pipe_name' : type;
        document.getElementById(inputId).value = val;
        
        let container = document.getElementById('group-'+type);
        for(let c of container.getElementsByClassName('chip')) c.classList.remove('active');
        el.classList.add('active');
        
        updatePreview();
        if(type !== 'weight') document.getElementById('weight_g').focus();
    }

    // --- LIVE PREVIEW LOGIC ---
    function updatePreview(qrBase64 = null) {
        const brand = document.getElementById('pipe_name').value;
        const size = document.getElementById('size').value;
        const color = document.getElementById('color').value;
        const op = document.getElementById('operator').value;
        const pressure = document.getElementById('pressure').value; // Get Pressure
        const weight = document.getElementById('weight_g').value || '0.000';
        
        let qrHtml = qrBase64 
            ? `<img src="${qrBase64}">` 
            : `<span style="color:#ccc; font-size:12px;">QR Code</span>`;

        const html = `
        <div class="label-visual">
            <div class="lbl-header">
                <div class="lbl-brand">${brand}</div>
                <div class="lbl-detail">${size} | ${color}</div>
            </div>
            <div class="lbl-qr-zone" id="previewQr">${qrHtml}</div>
            <div class="lbl-weight-zone">${weight} Kg</div>
            <div class="lbl-meta">
                <span>Op: ${op} | <b>${pressure}</b></span>
                <span>Date: ${new Date().toLocaleDateString()}</span>
            </div>
        </div>`;
        
        document.getElementById('previewArea').innerHTML = html;
    }

    // --- SUBMISSION ---
    const form = document.getElementById('labelForm');
    const btn = form.querySelector('button');
    let isProcessing = false;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if(isProcessing) return; 

        let wt = parseFloat(document.getElementById('weight_g').value);
        if (isNaN(wt) || wt <= 0) { showToast("Enter Weight!", true); return; }

        // LOCK
        isProcessing = true;
        btn.disabled = true;
        btn.innerText = "Printing...";
        btn.style.opacity = "0.7";

        let payload = {
            operator: document.getElementById('operator').value,
            pipe_name: document.getElementById('pipe_name').value,
            size: document.getElementById('size').value,
            color: document.getElementById('color').value,
            pressure: document.getElementById('pressure').value, // Add Pressure here
            weight_g: wt.toFixed(3)
        };

        try {
            const res = await fetch('/api/labels', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
            const data = await res.json();
            if (data.success) {
                updatePreview(data.qr_image);
                showToast("Printing...");
                
                // --- CRITICAL CHANGE: Pass pressure AGAIN to print route ---
                // Because we aren't saving it to DB, the print route needs to know it from here.
                let printPayload = { id: data.label.id, pressure: payload.pressure };

                const pRes = await fetch('/api/print', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(printPayload) });
                if ((await pRes.json()).success) showToast("Printed!");
            }
        } catch (e) { showToast("Error", true); }
        finally {
            isProcessing = false;
            btn.disabled = false;
            btn.innerText = "PRINT LABEL (ENTER)";
            btn.style.opacity = "1";
            document.getElementById('weight_g').value = '';
            document.getElementById('weight_g').focus();
        }
    });
</script>
{% endblock %}
{% endblock %}
'''

# FIXED ADMIN.HTML (Original Styles + Auto Refresh)
code_admin = r'''{% extends "layout.html" %}
{% block content %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
    /* --- DASHBOARD STYLES --- */
    .dashboard-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
    .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .kpi-card { background: white; padding: 1.5rem; border-radius: 12px; box-shadow: var(--shadow-sm); border-left: 5px solid #ccc; }
    .kpi-card h4 { margin: 0; color: #64748b; font-size: 0.85rem; text-transform: uppercase; }
    .kpi-card .val { font-size: 2rem; font-weight: 800; color: #1e293b; margin-top: 5px; }
    .nav-tabs { display: flex; gap: 10px; margin-bottom: 1.5rem; border-bottom: 2px solid #e2e8f0; }
    .tab-btn { padding: 10px 20px; background: none; border: none; font-weight: 600; color: #64748b; cursor: pointer; border-bottom: 3px solid transparent; font-size: 1rem; }
    .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
    .filter-bar { background: white; padding: 1.5rem; border-radius: 12px; box-shadow: var(--shadow-md); margin-bottom: 1.5rem; display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; }
    .filter-group { display: flex; flex-direction: column; flex: 1; min-width: 130px; }
    .filter-group label { font-size: 0.8rem; margin-bottom: 5px; }
    .filter-group select, .filter-group input { margin-bottom: 0; padding: 8px; font-size: 0.9rem; }
    .data-table-container { background: white; border-radius: 12px; box-shadow: var(--shadow-md); overflow: hidden; }
    .table-responsive { overflow-x: auto; max-height: 600px; }
    table { width: 100%; border-collapse: collapse; }
    th { position: sticky; top: 0; background: #f8fafc; z-index: 10; text-align: left; padding: 12px; font-size: 0.85rem; color: #64748b; border-bottom: 2px solid #e2e8f0; }
    td { padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 0.9rem; color: #334155; }
    tr:hover { background-color: #f8fafc; }
    .status-stock { background: #dbeafe; color: #1e40af; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; }
    .status-dispatch { background: #dcfce7; color: #166534; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; }
    .status-low { background: #fee2e2; color: #991b1b; padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; }
    .section { display: none; }
    .section.active { display: block; animation: fadeIn 0.3s; }
    @keyframes fadeIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
    
    .preview-actions { display: flex; justify-content: space-between; align-items: center; background: #f1f5f9; padding: 10px 20px; border-bottom: 1px solid #e2e8f0; }
</style>

<div id="loginOverlay" style="position: fixed; inset: 0; background: #f8fafc; z-index: 9999; display: flex; align-items: center; justify-content: center;">
    <div class="card" style="width: 350px; text-align: center;">
        <h2>🔐 Manager Login</h2>
        <input type="password" id="adminPass" placeholder="Enter Password">
        <button class="btn" onclick="authenticate()">Access Dashboard</button>
    </div>
</div>

<div id="mainDashboard" style="display: none;">
    <div class="dashboard-header">
        <div><h2 style="margin: 0;">🏭 Factory Manager</h2><small style="color: #64748b;">Inventory & Dispatch System</small></div>
        <div style="display: flex; gap: 10px;">
            <button class="btn" style="width: auto; background: #475569;" onclick="downloadBackup()">💾 Backup DB</button>
            <button class="btn" style="width: auto; background: #ef4444;" onclick="cleanData()">🗑️ Cleanup Old</button>
        </div>
    </div>

    <div class="kpi-row">
        <div class="kpi-card" style="border-color: #2563eb;"><h4>Total Production</h4><div class="val" id="kpi-total">0</div></div>
        <div class="kpi-card" style="border-color: #10b981;"><h4>In Stock</h4><div class="val" id="kpi-stock">0</div></div>
        <div class="kpi-card" style="border-color: #f59e0b;"><h4>Dispatched</h4><div class="val" id="kpi-dispatch">0</div></div>
    </div>

    <div class="nav-tabs">
        <button class="tab-btn active" onclick="showTab('inventory')">📋 Master Inventory</button>
        <button class="tab-btn" onclick="showTab('shipments')">🚚 Shipment History</button>
        <button class="tab-btn" onclick="showTab('reports')">📑 Reports & Sheets</button>
        <button class="tab-btn" onclick="showTab('summary')">📦 Stock Summary</button>
        <button class="tab-btn" onclick="showTab('analytics')">📈 Analytics</button>
    </div>

    <div id="tab-inventory" class="section active">
        <div class="filter-bar">
            <div class="filter-group"><label>Brand</label><select id="f_name"><option value="">All</option><option value="Gangotry">Gangotry</option><option value="UltraPlast">UltraPlast</option><option value="KissanGreen">KissanGreen</option><option value="Casing">Casing</option></select></div>
            <div class="filter-group"><label>Size</label><select id="f_size"><option value="">All</option><option value="63mm">63mm</option><option value="75mm">75mm</option><option value="90mm">90mm</option><option value="110mm">110mm</option><option value="140mm">140mm</option><option value="160mm">160mm</option><option value="180mm">180mm</option><option value="200mm">200mm</option></select></div>
            <div class="filter-group"><label>Color</label><select id="f_color"><option value="">All</option><option value="Blue">Blue</option><option value="Grey">Grey</option></select></div>
            <div class="filter-group"><label>Status</label><select id="f_status"><option value="">All</option><option value="stock">In Stock</option><option value="dispatched">Dispatched</option></select></div>
            <div class="filter-group"><label>Date</label><input type="date" id="f_start"></div>
            <div class="filter-group"><button class="btn" style="margin-bottom: 0;" onclick="fetchInventory()">🔍 Apply</button></div>
        </div>
        <div class="data-table-container">
            <div class="table-responsive"><table id="masterTable"><thead><tr><th>ID</th><th>Pipe Name</th><th>Size</th><th>Color</th><th>Weight</th><th>Op</th><th>Created</th><th>Status</th></tr></thead><tbody id="masterBody"></tbody></table></div>
        </div>
    </div>

    <div id="tab-shipments" class="section">
        <div class="data-table-container">
            <div class="preview-actions">
                <h3 style="margin:0;">Shipment History</h3>
                <button class="btn" style="width:auto; padding:8px 15px; font-size:0.9rem;" onclick="fetchShipmentHistory()">🔄 Refresh</button>
            </div>
            <div class="table-responsive">
                <table id="shipmentHistoryTable">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Customer</th>
                            <th>Vehicle No.</th>
                            <th>Challan No.</th>
                            <th>Pipes</th>
                            <th>Weight (Kg)</th>
                            <th>Created At</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="shipmentHistoryBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <div id="tab-reports" class="section">
        <div class="filter-bar">
            <div class="filter-group"><label>Report Date</label><input type="date" id="rep_date"></div>
            <div class="filter-group">
                <label>Select Shift / Time</label>
                <select id="rep_range">
                    <option value="">Whole Day (24 Hrs)</option>
                    <option value="09-17">General (09:00 - 17:00)</option>
                    <option value="08-20">Morning Shift (08:00 - 20:00)</option>
                    <option value="20-08">Night Shift (20:00 - 08:00)</option>
                    <option value="06-14">Shift A (06:00 - 14:00)</option>
                    <option value="14-22">Shift B (14:00 - 22:00)</option>
                    <option value="22-06">Shift C (22:00 - 06:00)</option>
                </select>
            </div>
            <div class="filter-group"><button class="btn" style="background: #0ea5e9;" onclick="previewReport('production')">📊 Production Summary</button></div>
            <div class="filter-group"><button class="btn" style="background: #166534;" onclick="previewReport('dispatch')">🚚 Dispatch Log</button></div>
        </div>

        <div id="reportPreviewContainer" style="display: none; margin-top: 20px;">
            <div class="data-table-container">
                <div class="preview-actions">
                    <h3 style="margin:0;" id="reportTitle">Report</h3>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn" style="width:auto; padding:8px 15px; font-size:0.9rem; background:#334155;" onclick="printReportPDF()">🖨️ Print A4</button>
                        <button class="btn" style="width:auto; padding:8px 15px; font-size:0.9rem; background:#166534;" onclick="downloadCSV()">📥 Export CSV</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table id="reportTable"><thead id="reportHead"></thead><tbody id="reportBody"></tbody></table>
                </div>
            </div>
        </div>
    </div>

    <div id="tab-summary" class="section">
        <div class="data-table-container">
            <div style="padding: 1.5rem; border-bottom: 1px solid #eee;"><h3>Live Stock Position</h3></div>
            <div class="table-responsive">
                <table><thead><tr><th>Pipe Brand</th><th>Size</th><th>Color</th><th>Total Made</th><th>Current Stock</th><th>Status</th></tr></thead><tbody id="summaryBody"></tbody></table>
            </div>
        </div>
    </div>
    <div id="tab-analytics" class="section">
        <div class="card" style="height: 400px; margin-bottom: 2rem;"><h3>Production Trend (7 Days)</h3><canvas id="prodChart"></canvas></div>
    </div>
</div>

<script>
    let AUTH_HEADER = {};
    let currentReportType = '';
    let pollingInterval = null;
    
    document.addEventListener("DOMContentLoaded", () => {
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('f_start').value = today;
        document.getElementById('rep_date').value = today;
    });

    async function authenticate() {
        const pass = document.getElementById('adminPass').value;
        const creds = btoa("admin:" + pass);
        const headers = { 'Authorization': 'Basic ' + creds };
        try {
            const res = await fetch('/api/stats_summary', { headers });
            if (res.status === 401) { showToast("Wrong Password!", true); return; }
            AUTH_HEADER = headers;
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('mainDashboard').style.display = 'block';
            loadStats(await res.json());
            fetchInventory(); 
            
            // --- NEW: START AUTO REFRESH ---
            startLiveUpdates();

        } catch(e) { showToast("Connection Error", true); }
    }

    // --- NEW: LIVE UPDATES LOGIC ---
    function startLiveUpdates() {
        if(pollingInterval) clearInterval(pollingInterval);
        pollingInterval = setInterval(async () => {
            // Only fetch if tab is active
            if(document.hidden) return; 
            try {
                const res = await fetch('/api/stats_summary', { headers: AUTH_HEADER });
                if(res.ok) {
                    const data = await res.json();
                    loadStats(data); // Re-use existing update function
                }
            } catch(e) { console.log("Silent refresh failed"); }
        }, 10000); // 10 Seconds
    }

    function showTab(tabId) {
        document.querySelectorAll('.section').forEach(el => el.classList.remove('active'));
        document.getElementById('tab-' + tabId).classList.add('active');
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        event.target.classList.add('active');

        if (tabId === 'shipments') {
            // Only fetch if the table is empty, to avoid re-fetching on every click
            if (document.getElementById('shipmentHistoryBody').innerHTML.trim() === '') {
                fetchShipmentHistory();
            }
        }
    }

    // --- EXISTING REPORT LOGIC (PRESERVED) ---
    async function previewReport(type) {
        currentReportType = type;
        const date = document.getElementById('rep_date').value;
        const range = document.getElementById('rep_range').value;
        
        let grouped = (type === 'production') ? 'true' : 'false';
        
        const params = new URLSearchParams({
            report_type: type,
            date: date,
            time_range: range,
            grouped: grouped
        });

        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        const data = await res.json();

        const container = document.getElementById('reportPreviewContainer');
        const thead = document.getElementById('reportHead');
        const tbody = document.getElementById('reportBody');
        document.getElementById('reportTitle').innerText = (type === 'production' ? 'Production Summary' : 'Dispatch Log');

        container.style.display = 'block';
        tbody.innerHTML = '';

        if(type === 'production') {
            thead.innerHTML = `<tr><th>Brand</th><th>Size</th><th>Color</th><th style="text-align:center;">Quantity</th><th style="text-align:right;">Total Wt (Kg)</th><th style="text-align:right;">Avg Wt (Kg)</th></tr>`;
            let grandTotalQty = 0;
            let grandTotalWt = 0;
            if(data.length === 0) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No production found.</td></tr>`; return; }
            data.forEach(r => {
                grandTotalQty += r.count;
                grandTotalWt += r.total_weight;
                tbody.innerHTML += `
                    <tr>
                        <td style="font-weight:bold;">${r.pipe_name}</td>
                        <td>${r.size}</td>
                        <td>${r.color}</td>
                        <td style="text-align:center; font-weight:bold;">${r.count}</td>
                        <td style="text-align:right;">${r.total_weight.toFixed(3)}</td>
                        <td style="text-align:right; color:#64748b;">${r.avg_weight.toFixed(3)}</td>
                    </tr>`;
            });
            tbody.innerHTML += `
                <tr style="background:#f1f5f9; font-weight:bold; border-top:2px solid #cbd5e1;">
                    <td colspan="3" style="text-align:right;">GRAND TOTAL:</td>
                    <td style="text-align:center;">${grandTotalQty}</td>
                    <td style="text-align:right;">${grandTotalWt.toFixed(3)}</td>
                    <td></td>
                </tr>`;
        } else {
            thead.innerHTML = `<tr><th>ID</th><th>Brand</th><th>Size</th><th>Color</th><th>Wt (kg)</th><th>Dispatched At</th><th>By</th></tr>`;
            if(data.length === 0) { tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;">No dispatch records.</td></tr>`; return; }
            data.forEach(r => {
                tbody.innerHTML += `<tr><td>${r.id}</td><td>${r.pipe_name}</td><td>${r.size}</td><td>${r.color}</td><td>${r.weight_g}</td><td>${r.dispatched_at.slice(11,16)}</td><td>${r.dispatched_by}</td></tr>`;
            });
        }
    }

    function downloadCSV() {
        const date = document.getElementById('rep_date').value;
        const range = document.getElementById('rep_range').value;
        let grouped = (currentReportType === 'production') ? 'true' : 'false';
        const params = new URLSearchParams({ report_type: currentReportType, date: date, time_range: range, grouped: grouped });
        const pass = document.getElementById('adminPass').value;
        window.location.href = `/api/export?${params}&Authorization=Basic ${btoa("admin:" + pass)}`;
    }

    function printReportPDF() {
        const tableContent = document.getElementById('reportTable').outerHTML;
        const title = document.getElementById('reportTitle').innerText;
        const date = document.getElementById('rep_date').value;
        const range = document.getElementById('rep_range').options[document.getElementById('rep_range').selectedIndex].text;
        
        const win = window.open('', '', 'height=800,width=1000');
        win.document.write(`
            <html><head><title>${title}</title>
            <style>
                @page { size: A4; margin: 20mm; }
                body { font-family: 'Helvetica', sans-serif; color: #333; }
                .header { text-align: center; margin-bottom: 2rem; border-bottom: 2px solid #333; padding-bottom: 10px; }
                .header h1 { margin: 0; font-size: 24px; text-transform: uppercase; }
                .meta { display: flex; justify-content: space-between; margin-bottom: 1rem; font-size: 14px; font-weight: bold; }
                table { width: 100%; border-collapse: collapse; font-size: 12px; }
                th { background-color: #f8fafc; border: 1px solid #333; padding: 8px; text-align: left; text-transform: uppercase; }
                td { border: 1px solid #ddd; padding: 8px; }
                tr:nth-child(even) { background-color: #fcfcfc; }
                .footer { margin-top: 30px; font-size: 10px; text-align: center; color: #666; }
            </style>
            </head><body>
            <div class="header">
                <h1>🏭 Factory ${title}</h1>
            </div>
            <div class="meta">
                <span>Date: ${date}</span>
                <span>Shift/Time: ${range}</span>
            </div>
            ${tableContent}
            <div class="footer">Generated by Factory Manager System • ${new Date().toLocaleString()}</div>
            </body></html>
        `);
        win.document.close();
        setTimeout(() => { win.print(); }, 500);
    }

    // --- OTHER LOGIC (Stats, Inventory) ---
    function loadStats(data) { 
        document.getElementById('kpi-total').innerText = data.total;
        document.getElementById('kpi-stock').innerText = data.stock;
        document.getElementById('kpi-dispatch').innerText = data.dispatched;
        const sBody = document.getElementById('summaryBody'); sBody.innerHTML = '';
        data.stock_summary.forEach(row => {
            let badge = row.stock < 50 && row.stock > 0 ? 'status-low' : (row.stock > 0 ? 'status-stock' : 'status-dispatch');
            sBody.innerHTML += `<tr><td><b>${row.pipe_name}</b></td><td>${row.size}</td><td>${row.color}</td><td>${row.total}</td><td>${row.stock}</td><td><span class="${badge}">${row.stock > 0 ? 'In Stock' : 'Empty'}</span></td></tr>`;
        });
        if(window.myChart) window.myChart.destroy();
        const ctx = document.getElementById('prodChart').getContext('2d');
        window.myChart = new Chart(ctx, {
            type: 'line', data: { labels: data.production_chart.map(d => d.day), datasets: [{ label: 'Production', data: data.production_chart.map(d => d.count), borderColor: '#2563eb', tension: 0.3, fill: true, backgroundColor: 'rgba(37,99,235,0.1)' }] }, options: { responsive: true, maintainAspectRatio: false }
        });
    }

    async function fetchInventory() {
        const params = new URLSearchParams({
            name: document.getElementById('f_name').value,
            size: document.getElementById('f_size').value,
            color: document.getElementById('f_color').value,
            status: document.getElementById('f_status').value,
            start: document.getElementById('f_start').value
        });
        const res = await fetch(`/api/inventory?${params}`, { headers: AUTH_HEADER });
        const data = await res.json();
        const tbody = document.getElementById('masterBody'); tbody.innerHTML = '';
        if(data.length === 0) { tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">No records.</td></tr>'; return; }
        data.forEach(row => {
            let status = row.dispatched_at ? `<span class="status-dispatch">Sent: ${row.dispatched_at.slice(11,16)}</span>` : `<span class="status-stock">Stock</span>`;
            tbody.innerHTML += `<tr><td>#${String(row.id).padStart(4,'0')}</td><td>${row.pipe_name}</td><td>${row.size}</td><td>${row.color}</td><td>${row.weight_g}</td><td>${row.operator}</td><td>${row.created_at.slice(0,16)}</td><td>${status}</td></tr>`;
        });
    }

    function downloadBackup() { window.location.href = '/api/backup'; }
    async function cleanData() {
        if(!confirm("⚠️ Delete 30+ day old data?")) return;
        await fetch('/api/cleanup', { method: 'POST', headers: AUTH_HEADER });
        showToast("Cleanup Done");
    }

    async function fetchShipmentHistory() {
        try {
            const res = await fetch('/api/admin/shipments', { headers: AUTH_HEADER });
            if (!res.ok) {
                showToast("Failed to load shipments.", true);
                return;
            }
            const shipments = await res.json();
            const tbody = document.getElementById('shipmentHistoryBody');
            tbody.innerHTML = '';
            if (shipments.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No shipments found.</td></tr>';
                return;
            }
            shipments.forEach(s => {
                const challan = s.challan_no || 'N/A';
                const created = new Date(s.created_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' });
                tbody.innerHTML += `
                    <tr id="shipment-row-${s.id}">
                        <td>#${s.id}</td>
                        <td>${s.customer_name}</td>
                        <td>${s.vehicle_no}</td>
                        <td>${challan}</td>
                        <td>${s.total_pipes}</td>
                        <td>${s.total_weight.toFixed(2)}</td>
                        <td>${created}</td>
                        <td>
                            <a href="/shipment/${s.id}" target="_blank" class="btn" style="width:auto; padding: 5px 10px; font-size:0.8rem; background: #64748b;">View</a>
                            <button onclick="handleDeleteShipment(${s.id})" class="btn" style="width:auto; padding: 5px 10px; font-size:0.8rem; background: #ef4444; margin-left: 5px;">Delete</button>
                        </td>
                    </tr>
                `;
            });
        } catch (e) {
            showToast("Error fetching shipment history.", true);
        }
    }

    async function handleDeleteShipment(shipmentId) {
        if (!confirm(`Are you sure you want to delete Shipment #${shipmentId}? This will return all its items to stock. This action cannot be undone.`)) return;
        const res = await fetch(`/api/shipments/${shipmentId}`, { method: 'DELETE', headers: AUTH_HEADER });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            document.getElementById(`shipment-row-${shipmentId}`).remove();
        } else {
            showToast(data.message || "Failed to delete shipment.", true);
        }
    }
</script>
{% endblock %}
'''

# ORIGINAL LAUNCHER.PY (Preserved)
code_launcher = r'''import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import sys
import os
import signal
import webbrowser
import time

# --- CONFIGURATION ---
PYTHON_CMD = "python"
APP_SCRIPT = "app.py"
# Tumhara permanent domain
PERMANENT_URL = "https://app.bhaijiproducts.online" 

class FactoryLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("PVC Factory Control Panel (Live Domain)")
        self.root.geometry("550x300")
        self.root.configure(bg="#f0f2f5")
        
        # Variables
        self.server_process = None
        self.is_running = False

        # --- UI Elements ---
        self.header = tk.Label(root, text="少 PVC PRO System (Live Domain)", font=("Arial", 16, "bold"), bg="#f0f2f5", fg="#333")
        self.header.pack(pady=10)

        self.status_label = tk.Label(root, text="Status: STOPPED 閥", font=("Arial", 14), bg="#f0f2f5", fg="red")
        self.status_label.pack(pady=5)

        self.url_label = tk.Label(root, text=f"倹 Admin Link: {PERMANENT_URL}/admin", font=("Consolas", 12), bg="#e1e4e8", padx=10, pady=5, fg="#2563eb", cursor="hand2")
        self.url_label.pack(pady=10, fill="x", padx=30)
        self.url_label.bind("<Button-1>", lambda e: self.open_link(f"{PERMANENT_URL}/admin"))

        self.btn_start = tk.Button(root, text="START PYTHON SERVER", command=self.start_system, font=("Arial", 12, "bold"), bg="#10b981", fg="white", width=30, height=2)
        self.btn_start.pack(pady=10)

        self.btn_stop = tk.Button(root, text="STOP SERVER", command=self.stop_system, font=("Arial", 12, "bold"), bg="#ef4444", fg="white", width=30, height=2, state="disabled")
        self.btn_stop.pack(pady=5)

        tk.Label(root, text="Tunnel (Cloudflare) is running automatically as a Windows Service.", font=("Arial", 9), bg="#f0f2f5", fg="#64748b").pack(pady=10)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_link(self, url):
        """Opens the permanent URL in the default web browser."""
        if self.is_running:
            webbrowser.open_new(url)
        else:
            messagebox.showwarning("System Offline", "Please start the Python Server first.")

    def start_system(self):
        if self.is_running: return
        
        self.status_label.config(text="Status: STARTING PYTHON... 泯", fg="orange")
        self.btn_start.config(state="disabled")
        
        # Start Flask Server (app.py)
        try:
            # We use subprocess.DETACHED_PROCESS to run it in the background
            self.server_process = subprocess.Popen(
                [PYTHON_CMD, APP_SCRIPT],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            )
            # Give server a moment to boot
            time.sleep(2) 
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start app.py: {e}\nCheck if Python is in your system PATH.")
            self.stop_system()
            return

        self.is_running = True
        self.btn_stop.config(state="normal")
        self.status_label.config(text="Status: RUNNING 泙 (Open Link Above)", fg="green")
        self.btn_start.config(text="SERVER IS ACTIVE", bg="#059669")
        
        # Open browser automatically after starting server
        self.open_link(f"{PERMANENT_URL}/admin")


    def stop_system(self):
        if not self.is_running: return
        
        # Killing the Python process safely (using its PID)
        try:
            # Note: Since we used DETACHED_PROCESS, we need taskkill
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.server_process.pid)], creationflags=subprocess.CREATE_NO_WINDOW)
            
        except Exception as e:
            # Handle if process already died
            print(f"Error stopping process: {e}")
            pass
        
        self.server_process = None

        self.is_running = False
        self.btn_start.config(state="normal", text="START PYTHON SERVER", bg="#10b981")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="Status: STOPPED 閥", fg="red")

    def on_close(self):
        if self.is_running:
            if messagebox.askokcancel("Quit", "Server is running. Do you want to stop it and exit?"):
                self.stop_system()
                self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FactoryLauncher(root)
    root.mainloop()
'''

# --- 2. CREATE FILES ---
BASE_DIR = "PVC_Factory_Final"
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(TEMPLATES_DIR):
    os.makedirs(TEMPLATES_DIR)

# Dictionary: Filename -> Content
files_to_write = {
    os.path.join(BASE_DIR, "app.py"): code_app,
    os.path.join(BASE_DIR, "services.py"): code_services,
    os.path.join(BASE_DIR, "printer_backend.py"): code_printer,
    os.path.join(BASE_DIR, "launcher.py"): code_launcher,
    os.path.join(TEMPLATES_DIR, "layout.html"): code_layout,
    os.path.join(TEMPLATES_DIR, "scan.html"): code_scan,
    os.path.join(TEMPLATES_DIR, "generate.html"): code_generate,
    os.path.join(TEMPLATES_DIR, "admin.html"): code_admin
}

# Write Loop
print(f"Creating project in {BASE_DIR}...")
for path, content in files_to_write.items():
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f" -> Created {path}")

print("\n✅ SUCCESS! Project folder 'PVC_Factory_Final' is ready.")
print("👉 Open the folder and run 'python launcher.py' or 'python app.py'")