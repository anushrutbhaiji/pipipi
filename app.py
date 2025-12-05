import os
import csv
import io
from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, jsonify, send_file, Response
import services          # Our new Logic Layer
import printer_backend   # Our new Hardware Layer

app = Flask(__name__)

def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
    """Jinja filter to format an ISO date string."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime(format)
    except:
        return value
app.jinja_env.filters['format_datetime'] = format_datetime_filter

ADMIN_PASS = "admin123"

# --- VIEWS ---
@app.route('/')
def index(): return render_template('generate.html')

@app.route('/scan')
def scan(): return render_template('scan.html')

@app.route('/dispatch')
def dispatch_hub():
    return render_template('dispatch.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/shipment/<int:shipment_id>')
def shipment_detail(shipment_id):
    # This page is intended to be accessed from the admin dashboard.
    # For a production app, proper session-based auth would be needed here.
    shipment_data = services.get_shipment_details(shipment_id)
    if not shipment_data:
        return "Shipment not found", 404
    
    return render_template('shipment_detail.html', 
                           shipment=shipment_data['shipment'], 
                           items=shipment_data['items'])

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

@app.route('/api/shipments/create', methods=['POST'])
def create_shipment():
    data = request.json
    meta = data.get('meta', {})
    items = data.get('items', [])
    
    if not all([meta.get('customer'), meta.get('vehicle')]) or not items:
        return jsonify({"success": False, "message": "Missing customer, vehicle, or items."}), 400

    try:
        shipment_id, timestamp = services.create_shipment_record(meta, items)
        return jsonify({
            "success": True,
            "message": f"Shipment {shipment_id} created successfully.",
            "shipment_id": shipment_id,
            "timestamp": timestamp
        })
    except sqlite3.IntegrityError:
        challan = meta.get('challan_no')
        if challan:
            return jsonify({"success": False, "message": f"Challan number '{challan}' already exists. Please use a unique challan number."}), 409 # HTTP 409 Conflict
        else:
            # This would be an unexpected integrity error
            return jsonify({"success": False, "message": "A database integrity error occurred."}), 500

@app.route('/api/admin/shipments', methods=['GET'])
def get_admin_shipments():
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    history_data = services.get_shipment_history()
    return jsonify(history_data)

@app.route('/api/shipments/<int:shipment_id>', methods=['DELETE'])
def delete_shipment_api(shipment_id):
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: 
        return jsonify({"error": "Unauthorized"}), 401
    
    success = services.delete_shipment(shipment_id)
    
    if success:
        return jsonify({"success": True, "message": f"Shipment #{shipment_id} deleted and items returned to stock."})
    else:
        # This could happen if the ID doesn't exist.
        return jsonify({"success": False, "message": f"Shipment #{shipment_id} not found or could not be deleted."}), 404

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
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    
    data = services.fetch_inventory_data(request.args)
    si = io.StringIO(); cw = csv.writer(si)
    
    # Simple dynamic CSV generation based on first row keys
    if data:
        cw.writerow(data[0].keys())
        for row in data: 
            cw.writerow(row.values())
    else:
        cw.writerow(["No Data"])

    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=report.csv"})

@app.route('/api/backup')
def backup(): 
    auth = request.authorization
    if not auth or auth.password != ADMIN_PASS: return jsonify({"error": "Unauthorized"}), 401
    return send_file(services.DB_NAME, as_attachment=True)

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    services.run_cleanup()
    return jsonify({"success": True})

if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    print("System Running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
