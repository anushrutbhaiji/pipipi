import sqlite3
import datetime
import json
import io
import qrcode
import base64

DB_NAME = "pvc_factory.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        # 1. Base Labels Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipe_name TEXT, size TEXT, color TEXT, weight_g REAL,
                length_m TEXT, batch TEXT, operator TEXT,
                created_at TEXT, printed_at TEXT, 
                dispatched_at TEXT, dispatched_by TEXT,
                shipment_id INTEGER
            )
        """)
        # 2. New Shipments Table (For History)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                vehicle_no TEXT,
                customer_mobile TEXT,
                driver_mobile TEXT,
                customer_address TEXT,
                challan_no TEXT,
                total_pipes INTEGER,
                total_weight REAL,
                created_at TEXT
            )
        """)
    ensure_schema_updates()

def ensure_schema_updates():
    """Migrates existing DB to have new columns if they are missing."""
    with get_db_connection() as conn:
        try:
            # Check if shipment_id exists in labels
            conn.execute("SELECT shipment_id FROM labels LIMIT 1")
        except sqlite3.OperationalError:
            # If not, add it
            conn.execute("ALTER TABLE labels ADD COLUMN shipment_id INTEGER")
            print("Migrated DB: Added shipment_id to labels")
        try:
            conn.execute("SELECT customer_address FROM shipments LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE shipments ADD COLUMN customer_address TEXT")
            print("Migrated DB: Added customer_address to shipments")
        try:
            conn.execute("SELECT customer_mobile FROM shipments LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE shipments ADD COLUMN customer_mobile TEXT")
            print("Migrated DB: Added customer_mobile to shipments")
        try:
            conn.execute("SELECT driver_mobile FROM shipments LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE shipments ADD COLUMN driver_mobile TEXT")
            print("Migrated DB: Added driver_mobile to shipments")
        try:
            conn.execute("SELECT challan_no FROM shipments LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE shipments ADD COLUMN challan_no TEXT")
            print("Migrated DB: Added challan_no to shipments")

        # Add unique index for challan_no. This is idempotent.
        # It allows multiple NULL or empty string values, but enforces uniqueness for actual values.
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_shipments_challan_no ON shipments (challan_no) WHERE challan_no IS NOT NULL AND challan_no != ''")
        except sqlite3.IntegrityError:
            print("\n" + "="*80)
            print("!! DATABASE WARNING: Could not enforce unique challan numbers.")
            print("   This is because your existing 'shipments' table contains duplicate challan numbers.")
            print("   The application will run, but new duplicate challans can still be created until the data is fixed.")
            print("   TO FIX: Manually edit the 'pvc_factory.db' file (using a tool like DB Browser for SQLite)")
            print("   and ensure all non-empty 'challan_no' values in the 'shipments' table are unique.")
            print("   After fixing the data, restart the application to apply the unique constraint.")
            print("="*80 + "\n")

init_db()

def import_base64(data):
    return base64.b64encode(data).decode('utf-8')

# --- CORE LOGIC ---
def create_label_in_db(data):
    created_at = datetime.datetime.now().isoformat()
    length_m = data.get('length_m', '6m')
    batch = data.get('batch', 'BATCH-001')
    
    with get_db_connection() as conn:
        cur = conn.cursor()
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

# --- NEW DISPATCH LOGIC (BATCH) ---
def create_shipment_record(meta, items):
    """
    1. Creates a shipment record.
    2. Marks all items as dispatched and links them to the shipment.
    """
    timestamp = datetime.datetime.now().isoformat()
    total_qty = len(items)
    total_wt = sum(float(i['weight_g']) for i in items)
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # 1. Create Header
        cur.execute("""
            INSERT INTO shipments (customer_name, vehicle_no, customer_address, customer_mobile, driver_mobile, challan_no, total_pipes, total_weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (meta.get('customer'), meta.get('vehicle'), meta.get('address'), meta.get('customer_mobile'), meta.get('driver_mobile'), meta.get('challan_no'), total_qty, total_wt, timestamp))
        shipment_id = cur.lastrowid
        
        # 2. Update all Labels
        # Prepare data for a bulk update: (dispatched_at, dispatched_by, shipment_id, id)
        update_data = [(timestamp, 'DispatchHub', shipment_id, i['id']) for i in items]
        
        # Use executemany for a single, efficient bulk update operation
        cur.executemany("""
            UPDATE labels 
            SET dispatched_at=?, dispatched_by=?, shipment_id=? 
            WHERE id=?
        """, update_data)
            
        conn.commit()
        return shipment_id, timestamp

def mark_dispatched(label_id, dispatched_by="Scanner"):
    # Legacy function for single scan (Scan Page)
    with get_db_connection() as conn:
        conn.execute("UPDATE labels SET dispatched_at=?, dispatched_by=? WHERE id=?", 
                     (datetime.datetime.now().isoformat(), dispatched_by, label_id))

def get_shipment_history():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM shipments ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def get_shipment_details(shipment_id):
    """Fetches a single shipment and all its associated items."""
    with get_db_connection() as conn:
        shipment = conn.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
        if not shipment:
            return None
        
        items = conn.execute("SELECT * FROM labels WHERE shipment_id = ? ORDER BY pipe_name, size, color, id", (shipment_id,)).fetchall()
        
        return {
            "shipment": dict(shipment),
            "items": [dict(i) for i in items]
        }

def delete_shipment(shipment_id):
    """
    Deletes a shipment and returns its items to stock.
    1. Sets shipment_id, dispatched_at, dispatched_by to NULL for associated labels.
    2. Deletes the shipment record from the shipments table.
    """
    with get_db_connection() as conn:
        # The 'with' block ensures a transaction.
        cur = conn.cursor()
        
        # 1. Find all labels for the shipment and return them to stock.
        cur.execute("UPDATE labels SET dispatched_at = NULL, dispatched_by = NULL, shipment_id = NULL WHERE shipment_id = ?", (shipment_id,))
        
        # 2. Delete the shipment record itself.
        cur.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
        deleted_count = cur.rowcount
        conn.commit()
        return deleted_count > 0

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