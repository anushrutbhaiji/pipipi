import json
import os
import csv
import io
import threading
import time
from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, jsonify, send_file, Response
import services          # Our Logic Layer
import printer_backend   # Our Hardware Layer
from threading import Lock
FILE_LOCK = Lock()

def get_real_ip():
    # Cloudflare / ngrok / proxies
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def is_allowed_internal_ip(ip):
    # Normalize IPv6-mapped IPv4 (::ffff:192.168.1.40)
    if ip.startswith('::ffff:'):
        ip = ip.replace('::ffff:', '')

    # Localhost
    if ip in ('127.0.0.1', '::1'):
        return True

    # LAN
    if ip.startswith('192.168.1.'):
        return True

    return False


# --- GPIO SETUP ---
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    try:
        import RPi.GPIO as GPIO # Try again mostly for rpi-lgpio compatibility
        GPIO_AVAILABLE = True
    except:
        GPIO = None
        GPIO_AVAILABLE = False
        print("⚠️ RPi.GPIO/rpi-lgpio not found. Running in simulation mode.")

app = Flask(__name__)

# --- GLOBAL COUNTER ---
# --- REPLACE "SESSION_PIPE_COUNT = 0" WITH THIS ---
import os
if os.path.exists("counter_memory.txt"):
    with open("counter_memory.txt", "r") as f:
        try:
            SESSION_PIPE_COUNT = int(f.read().strip())
        except:
            SESSION_PIPE_COUNT = 0
else:
    SESSION_PIPE_COUNT = 0

# --- LIMIT SWITCH CONFIGURATION ---
SWITCH_PIN = 17
AUTO_PRINT_ACTIVE = False
AUTO_PRINT_SETTINGS = {}

def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
    if not value: return ""
    try: return datetime.fromisoformat(value).strftime(format)
    except: return value
app.jinja_env.filters['format_datetime'] = format_datetime_filter

ADMIN_PASS = "admin24"

def limit_switch_listener():
    # Ensure we refer to the module-level counter variable
    global SESSION_PIPE_COUNT
    if not GPIO_AVAILABLE: return

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"✅ Limit Switch Listener Started on GPIO {SWITCH_PIN}")
    except Exception as e:
        print(f"❌ GPIO Setup Failed: {e}")
        return

    last_state = GPIO.input(SWITCH_PIN) 

    while True:
        try:
            current_state = GPIO.input(SWITCH_PIN)
            
            # Check for PRESS (High -> Low)
            if last_state == GPIO.HIGH and current_state == GPIO.LOW:
                
                # Double check to make sure it's not a tiny spark (0.2s check)
                time.sleep(0.2)
                if GPIO.input(SWITCH_PIN) == GPIO.HIGH:
                    last_state = GPIO.HIGH
                    continue

                if AUTO_PRINT_ACTIVE and AUTO_PRINT_SETTINGS:
                    print("🔘 Switch Triggered! Printing Label...")
                    
                    # Ensure batch reflects the next counter value
                    data_to_save = AUTO_PRINT_SETTINGS.copy()
                    data_to_save['batch'] = f"#{SESSION_PIPE_COUNT + 1}"
                    label_data = services.create_label_in_db(data_to_save)
                    label_data['pressure'] = data_to_save.get('pressure', '')
                    
                    success, msg = printer_backend.silent_print_label(label_data)
                    
                    if success:
                        SESSION_PIPE_COUNT += 1
                        # --- ADD THIS TO SAVE THE COUNT ---
                        with FILE_LOCK:
                            with open("counter_memory.txt", "w") as f:
                                f.write(str(SESSION_PIPE_COUNT))
                        # ----------------------------------
                        
                        services.mark_printed(label_data['id'])
                        print(f"🖨️ Printed ID: {label_data['id']}")
                    else:
                        print(f"❌ Print Failed: {msg}")

                    # ===================================================
                    # 🔴 THE FIX: 60-SECOND LOCKOUT (HAMMER FIX)
                    # ===================================================
                    print("🛡️ Locking system for 60 seconds (Ignoring all bounce)...")
                    time.sleep(60.0) 
                    # ===================================================

                    # --- NOW WAIT FOR RELAY TO TURN OFF ---
                    print("⏳ Waiting for cycle to end...")
                    while GPIO.input(SWITCH_PIN) == GPIO.LOW:
                        time.sleep(1.0) 
                    
                    print("✅ Cycle Complete. Ready for next.")
                    time.sleep(1.0) 

            last_state = current_state
            time.sleep(0.05) 
            
        except Exception as e:
            print(f"Error in thread: {e}")
            time.sleep(1)
if GPIO_AVAILABLE:
    t = threading.Thread(target=limit_switch_listener, daemon=True)
    t.start()

# --- VIEWS ---
@app.route('/')
def index(): return render_template('admin.html')

@app.route('/generate')
def generate():
    real_ip = get_real_ip()
    
    # Existing IP check
    if real_ip not in ('127.0.0.1', '::1'):
        return "Forbidden", 403
    return render_template('generate.html')

@app.route('/scan')
def scan(): return render_template('scan.html')

@app.route('/dispatch')
def dispatch_hub():
    real_ip = get_real_ip()
    print("DISPATCH IP:", real_ip)

    if not is_allowed_internal_ip(real_ip):
        return "Forbidden", 403

    return render_template('dispatch.html')

@app.route('/mobile')
def mobile(): return render_template('dispatch_mobile.html')

@app.route('/dispatch-esp')
def dispatch_esp():
    return render_template('dispatch_esp.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/shipment/<int:shipment_id>')
def shipment_detail(shipment_id):
    shipment_data = services.get_shipment_details(shipment_id)
    if not shipment_data: return "Shipment not found", 404
    return render_template('shipment_detail.html', shipment=shipment_data['shipment'], items=shipment_data['items'])

# --- API ---
@app.route('/api/labels', methods=['POST'])
def create_label():
    d = request.json
    label = services.create_label_in_db(d)
    label['pressure'] = d.get('pressure', '')
    qr_img = services.generate_qr_for_label(label['id'], label['created_at'])
    return jsonify({"success": True, "label": label, "qr_image": qr_img})

@app.route('/api/print', methods=['POST'])
def trigger_print():
    req = request.json
    label_id = req.get('id')
    pressure = req.get('pressure', '')
    label = services.get_label_by_id(label_id)
    if not label: return jsonify({"success": False}), 404
    label_for_print = label.copy()
    label_for_print['pressure'] = pressure
    success, msg = printer_backend.silent_print_label(label_for_print)
    if success: 
        global SESSION_PIPE_COUNT
        SESSION_PIPE_COUNT += 1
        with FILE_LOCK:
            with open("counter_memory.txt", "w") as f:
                f.write(str(SESSION_PIPE_COUNT))
        services.mark_printed(label_id)

    return jsonify({"success": success, "message": msg})

@app.route('/api/autoprint/toggle', methods=['POST'])
def toggle_autoprint():
    global AUTO_PRINT_ACTIVE, AUTO_PRINT_SETTINGS
    data = request.json
    status = data.get('enabled', False)
    payload = data.get('settings', {})
    if status:
        AUTO_PRINT_SETTINGS = payload
        AUTO_PRINT_ACTIVE = True
        msg = "Auto-Print ACTIVATED."
    else:
        AUTO_PRINT_ACTIVE = False
        AUTO_PRINT_SETTINGS = {}
        msg = "Auto-Print DEACTIVATED."
    print(msg)
    return jsonify({"success": True, "message": msg})

@app.route('/api/labels/<int:id>', methods=['GET'])
def get_label(id):
    lbl = services.get_label_by_id(id)
    return jsonify(lbl) if lbl else (jsonify({"error": "Not found"}), 404)

@app.route('/api/dispatch', methods=['POST'])
def mark_dispatch():
    services.mark_dispatched(request.json['id'])
    return jsonify({"success": True})

# --- UPDATED CREATE SHIPMENT (THE FIX) ---
@app.route('/api/shipments/create', methods=['POST'])
def create_shipment():
    data = request.json
    
    # DEBUG: Print incoming data to console
    print("\n--- DEBUG: INCOMING SHIPMENT DATA ---")
    print(data) 
    print("-------------------------------------\n")
    
    meta = data.get('meta', {})
    items = data.get('items', [])
    
    # FIX: Accept 'challan_number', 'challan_no', or 'challanNo'
    challan_val = meta.get('challan_number') or meta.get('challan_no') or meta.get('challanNo')
    
    # Validation
    if not challan_val or not items:
        # Return received keys to help debugging
        return jsonify({
            "success": False, 
            "message": f"Missing Challan Number or items. (Received keys: {list(meta.keys())})"
        }), 400

    # Normalize data for service layer
    meta['challan_number'] = challan_val

    try:
        shipment_id, timestamp = services.create_shipment_record(meta, items)
        return jsonify({"success": True, "message": f"Shipment {shipment_id} created.", "shipment_id": shipment_id})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Challan number already exists."}), 409
    except Exception as e:
        print(f"❌ Server Error in Create Shipment: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# --- UPDATED ADMIN HISTORY (THE FIX) ---
@app.route('/api/admin/shipments', methods=['GET'])
def get_admin_shipments():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: 
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Try to get data
        return jsonify(services.get_shipment_history())
    except Exception as e:
        # IF IT FAILS: Print the real error to the black terminal
        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"❌ ERROR LOADING HISTORY: {e}")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        return jsonify({"error": str(e)}), 500

@app.route('/api/shipments/<int:shipment_id>', methods=['DELETE'])
def delete_shipment_api(shipment_id):
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    success = services.delete_shipment(shipment_id)
    return jsonify({"success": True, "message": "Deleted"}) if success else (jsonify({"success": False}), 404)

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(services.fetch_inventory_data(request.args))

@app.route('/api/stats_summary', methods=['GET'])
def get_stats_summary():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(services.get_stats())

@app.route('/api/export', methods=['GET'])
def export_excel():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    data = services.fetch_inventory_data(request.args)
    si = io.StringIO(); cw = csv.writer(si)
    if data:
        cw.writerow(data[0].keys())
        for row in data: cw.writerow(row.values())
    else: cw.writerow(["No Data"])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=report.csv"})

@app.route('/api/backup')
def backup(): 
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    return send_file(services.DB_NAME, as_attachment=True)

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    services.run_cleanup()
    return jsonify({"success": True})

@app.route('/api/counter', methods=['GET'])
def get_counter():
    return jsonify({"count": SESSION_PIPE_COUNT})

@app.route('/api/counter/reset', methods=['POST'])
def reset_counter_api():
    global SESSION_PIPE_COUNT
    SESSION_PIPE_COUNT = 0
    # --- ADD THIS TO ERASE THE MEMORY FILE ---
    with FILE_LOCK:
        with open("counter_memory.txt", "w") as f:
            f.write("0")
    # -----------------------------------------
    
    return jsonify({"success": True, "count": 0})
# --- ADD NEAR THE BOTTOM OF app.py (Before 'if __name__...') ---

@app.route('/api/labels/<int:label_id>', methods=['DELETE'])
def reject_pipe(label_id):
    # Optional: Check for admin password if you want security
    # auth = request.authorization
    # if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401

    success = services.delete_label(label_id)
    if success:
        return jsonify({"success": True, "message": "Pipe rejected and removed from DB."})
    else:
        return jsonify({"error": "Pipe not found"}), 404
# --- GLOBAL SETTINGS SYNC (THE CLOUD MEMORY) ---
SETTINGS_FILE = "global_settings.json"
# --- IS CODE KO 'get_global_settings' KI JAGAH PASTE KARO ---
@app.route('/api/settings/get', methods=['GET'])
def get_global_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with FILE_LOCK:
                with open(SETTINGS_FILE, 'r') as f:
                    content = f.read().strip()
                # Agar file khali hai toh empty bhejo
                if not content:
                    return jsonify({})
                return jsonify(json.loads(content))
        except Exception as e:
            # AGAR FILE KHARAB HAI, TOH USKO DELETE KAR DO (Auto-Repair)
            print(f"⚠️ Settings file corrupted. Deleting it. Error: {e}")
            try:
                os.remove(SETTINGS_FILE)
            except:
                pass
            return jsonify({})
    return jsonify({})

@app.route('/api/settings/update', methods=['POST'])
def update_global_settings():
    new_settings = request.json
    try:
        # Read existing to merge, or start fresh
        existing = {}
        if os.path.exists(SETTINGS_FILE):
            with FILE_LOCK:
                with open(SETTINGS_FILE, 'r') as f:
                    existing = json.load(f)
        
        # Update only the changed fields
        existing.update(new_settings)
        
        with FILE_LOCK:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(existing, f)

            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- UNIQUE ROUTE: Search Challan ---
@app.route('/api/dispatch/search_challan/<string:c_no>')
def api_search_challan_unique(c_no):
    res = services.find_challan_details(c_no)
    if res: return jsonify({"success": True, "data": res})
    return jsonify({"success": False, "message": "Not Found"}), 404

# --- UNIQUE ROUTE: Add Items to Shipment ---
@app.route('/api/dispatch/edit_add', methods=['POST'])
def api_edit_add_items_unique():
    data = request.json
    s_id = data.get('shipment_id')
    items = data.get('items', []) # Expects list of full pipe objects
    
    if not s_id or not items:
        return jsonify({"success": False, "message": "Missing data"}), 400
        
    # Extract IDs from the pipe objects
    ids = [p['id'] for p in items]
    
    success, msg = services.add_extra_items_to_shipment(s_id, ids)
    return jsonify({"success": success, "message": msg})

# --- SEARCH: Get Full Details (Meta + Items) ---
@app.route('/api/dispatch/search_full/<string:c_no>')
def api_search_full(c_no):
    data = services.get_shipment_full_details(c_no)
    if data: return jsonify({"success": True, "data": data})
    return jsonify({"success": False, "message": "Challan not found"}), 404

# --- ACTION: Remove Item ---
@app.route('/api/dispatch/remove_item', methods=['POST'])
def api_remove_item():
    data = request.json
    pipe_id = data.get('pipe_id')
    success, msg = services.remove_pipe_from_shipment(pipe_id)
    return jsonify({"success": success, "message": msg})

# --- API: Process Return ---
@app.route('/api/returns/create', methods=['POST'])
def api_create_return():
    data = request.json
    items = data.get('items', [])
    if not items: return jsonify({"success": False, "message": "No items scanned"}), 400
    
    pipe_ids = [p['id'] for p in items]
    
    # Capture the ID returned by services
    success, voucher_id = services.process_return_voucher(pipe_ids)
    
    if success:
        return jsonify({
            "success": True, 
            "message": f"Return Voucher #{voucher_id} Saved Successfully!"
        })
    return jsonify({"success": False, "message": "Database Error"}), 500

@app.route('/admin/returns')
def admin_returns_history():
    with services.get_db_connection() as conn:
        # Fetch all returns, newest first
        vouchers = conn.execute("SELECT * FROM return_vouchers ORDER BY id DESC").fetchall()
    return render_template('return_history.html', vouchers=vouchers)

@app.route('/api/inventory/reject', methods=['POST'])
def reject_inventory():
    data = request.json
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'success': False, 'message': 'No IDs provided'}), 400
        
    try:
        with services.get_db_connection() as conn:
            placeholders = ','.join('?' * len(ids))
            
            # THE TRICK: Set dispatched_by to 'rejected'
            conn.execute(f"UPDATE labels SET dispatched_by = 'rejected' WHERE id IN ({placeholders})", ids)
            
        return jsonify({'success': True, 'message': f'Marked {len(ids)} records as rejected'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# --- ADD GLOBAL QUEUE ---
from collections import deque
ESP_QUEUE = deque()

# --- ESP PUSH API ---
@app.route('/api/esp/push', methods=['POST'])
def esp_push():
    try:
        data = request.get_json()
        print("📥 RAW DATA:", data)

        pipe_id = None

        # Case 1: {"id": 3491}
        if isinstance(data.get("id"), int):
            pipe_id = data["id"]

        # Case 2: {"id": {"id": 3491}}
        elif isinstance(data.get("id"), dict):
            pipe_id = data["id"].get("id")

        if not pipe_id:
            return jsonify({"error": "Invalid ID format"}), 400

        ESP_QUEUE.append(pipe_id)

        print(f"✅ Parsed ID: {pipe_id}")
        return jsonify({"success": True})

    except Exception as e:
        print("❌ ESP PUSH ERROR:", str(e))
        return jsonify({"error": str(e)}), 500

# --- UI FETCH API ---
@app.route('/api/esp/fetch', methods=['GET'])
def esp_fetch():
    items = []

    while ESP_QUEUE:
        items.append(ESP_QUEUE.popleft())

    return jsonify(items)

if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    print("System Running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
