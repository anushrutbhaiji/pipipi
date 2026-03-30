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
                # --- ADD THIS BLOCK ---
        try:
            conn.execute("SELECT pressure_class FROM labels LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE labels ADD COLUMN pressure_class TEXT")
            print("Migrated DB: Added pressure_class to labels")
        # ----------------------
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
    batch = data.get('batch', '#1')
    pressure = data.get('pressure', '') # New field

    with get_db_connection() as conn:
        cur = conn.cursor()
        # <--- Added pressure_class to the INSERT statement below
        cur.execute("INSERT INTO labels (pipe_name, size, color, weight_g, length_m, batch, operator, created_at, pressure_class) VALUES (?,?,?,?,?,?,?,?,?)",
                    (data['pipe_name'], data['size'], data['color'], data['weight_g'], length_m, batch, data.get('operator','OP-1'), created_at, pressure))
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
    #  <-- MAKE SURE THERE ARE 4 SPACES HERE
    with get_db_connection() as conn:
        # 1. Get the Shipment Meta Data
        shipment = conn.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
        if not shipment: return None
        
        # 2. Get the ACTUAL pipes currently assigned to this shipment
        pipes = conn.execute("SELECT * FROM labels WHERE shipment_id = ?", (shipment_id,)).fetchall()
        
        # --- AUTO-REPAIR COUNTS ---
        real_count = len(pipes)
        real_weight = sum(p['weight_g'] for p in pipes) if pipes else 0
        
        if shipment['total_pipes'] != real_count:
            print(f"⚠️ Fixing Sync: DB {shipment['total_pipes']} -> Real {real_count}")
            conn.execute("UPDATE shipments SET total_pipes=?, total_weight=? WHERE id=?", 
                         (real_count, real_weight, shipment_id))
            conn.commit()
            
            # Update the variable so the UI sees the fixed number immediately
            shipment = dict(shipment)
            shipment['total_pipes'] = real_count
            shipment['total_weight'] = real_weight
        # --------------------------
        
        return {
            "shipment": dict(shipment),
            "items": [dict(p) for p in pipes]
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
    if args.get('pressure'): conditions.append("pressure_class=?"); params.append(args.get('pressure'))
    
    # ... (name, size, color, pressure, weight filters stay the same above this)
    target_weight = args.get('weight')
    if target_weight:
        conditions.append("weight_g = ?")
        params.append(target_weight)
    report_type = args.get('report_type', 'inventory')
    target_date = args.get('date')
    time_range = args.get('time_range')
    status = args.get('status')
    
    # --- 🕒 TIME MACHINE LOGIC ---
    if target_date and report_type == 'inventory':
        if status == 'stock':
            conditions.append("date(created_at) <= ?")
            params.append(target_date)
            conditions.append("(dispatched_at IS NULL OR date(dispatched_at) > ?)")
            params.append(target_date)
            conditions.append("(dispatched_by IS NULL OR dispatched_by != 'rejected')") # Hide rejected
            
        elif status == 'dispatched':
            conditions.append("date(dispatched_at) = ?")
            params.append(target_date)
            conditions.append("(dispatched_by IS NULL OR dispatched_by != 'rejected')") # Hide rejected
            
        elif status == 'rejected':
            conditions.append("dispatched_by = 'rejected'")
            conditions.append("date(created_at) <= ?")
            params.append(target_date)
            
        else:
            # 'All' status
            conditions.append("date(created_at) <= ?")
            params.append(target_date)
    else:
        # --- NORMAL LOGIC ---
        if status == 'stock': 
            conditions.append("dispatched_at IS NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected')")
        elif status == 'dispatched': 
            conditions.append("dispatched_at IS NOT NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected')")
        elif status == 'rejected': 
            conditions.append("dispatched_by = 'rejected'")
        
        # Date logic defaults to created_at for everything except dispatch reports
        date_field = "dispatched_at" if report_type == 'dispatch' else "created_at"
        if target_date: 
            conditions.append(f"date({date_field}) = ?"); params.append(target_date)

    # --- TIME RANGE LOGIC (Hour by hour) ---
    # ... (keep your existing time_range code here)

    # --- TIME RANGE LOGIC (Hour by hour) ---
    if time_range:
        date_field = "dispatched_at" if (report_type == 'dispatch' or status == 'dispatched') else "created_at"
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
        # SUMMARY VIEW: No pagination needed (Groups all records)
        query = f"""
            SELECT pipe_name, size, color, pressure_class, weight_g,
                   COUNT(*) as count, SUM(weight_g) as total_weight, AVG(weight_g) as avg_weight 
            FROM labels WHERE {where} 
            GROUP BY pipe_name, size, color, pressure_class, weight_g
            ORDER BY pipe_name, size
        """
        with get_db_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    else:
        # DETAIL VIEW: Time for Pagination!
        page = int(args.get('page', 1))
        per_page = int(args.get('per_page', 100))
        offset = (page - 1) * per_page
        
        # 1. Get the TOTAL count of pipes matching the filters
        count_query = f"SELECT COUNT(*) FROM labels WHERE {where}"
        
        # 2. Get ONLY the specific 100 pipes for the current page
        data_query = f"""
            SELECT labels.*, 
                   (SELECT challan_no FROM shipments WHERE id = labels.shipment_id) as challan_no 
            FROM labels 
            WHERE {where} 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """
        
        with get_db_connection() as conn:
            total_records = conn.execute(count_query, params).fetchone()[0]
            rows = conn.execute(data_query, params + [per_page, offset]).fetchall()
            
        # Return a dictionary with the pagination metadata
        return {
            "items": [dict(r) for r in rows],
            "total": total_records,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_records + per_page - 1) // per_page if per_page > 0 else 1
        }
def delete_label(label_id):
    """Permanently removes a pipe from the database."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM labels WHERE id = ?", (label_id,))
        conn.commit()
        return cur.rowcount > 0
# --- ADD AT THE BOTTOM OF services.py ---

# In services.py

def get_stats():
    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        
        # Updated: Only count actual successful dispatches
        dispatched = conn.execute("SELECT COUNT(*) FROM labels WHERE dispatched_at IS NOT NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected')").fetchone()[0]
        
        # Updated: Calculate accurate current stock (ignoring rejected)
        current_stock = conn.execute("SELECT COUNT(*) FROM labels WHERE dispatched_at IS NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected')").fetchone()[0]
        
        # --- 1. NORMAL STOCK SUMMARY ---
        stock_summ = conn.execute("""
            SELECT pipe_name, size, color, pressure_class, weight_g,
                COUNT(*) as total, 
                SUM(CASE 
                        WHEN dispatched_at IS NULL 
                        AND (dispatched_by IS NULL OR dispatched_by != 'rejected') 
                        THEN 1 ELSE 0 END) as stock,

                AVG(
                        CASE 
                            WHEN dispatched_at IS NULL 
                            AND (dispatched_by IS NULL OR dispatched_by != 'rejected') 
                            THEN weight_g 
                        END
                ) as avg_weight

            FROM labels 
            GROUP BY pipe_name, size, color, pressure_class, weight_g
        """).fetchall()
        
        prod = conn.execute("SELECT date(created_at) as day, COUNT(*) as count FROM labels WHERE created_at >= date('now', '-7 days') GROUP BY day").fetchall()
        
        # --- 2. NEW: DEAD STOCK QUERY (> 180 Days) ---
        dead_stock = conn.execute("""
            SELECT pipe_name, size, color, pressure_class,
                   CAST(julianday('now') - julianday(created_at) AS INTEGER) as days_old,
                   COUNT(*) as qty
            FROM labels
            WHERE dispatched_at IS NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected') AND created_at <= date('now', '-18 days')
            GROUP BY pipe_name, size, color, pressure_class, date(created_at)
            ORDER BY days_old DESC
        """).fetchall()
        
    return {
        "total": total, 
        "dispatched": dispatched, 
        "stock": current_stock, 
        "stock_summary": [dict(r) for r in stock_summ], 
        "production_chart": [dict(r) for r in prod],
        "dead_stock": [dict(r) for r in dead_stock] 
    }
# --- 1. Find a Challan ---
def find_challan_details(challan_no):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM shipments WHERE challan_no = ?", (challan_no,)).fetchone()
        return dict(row) if row else None

# --- 2. Add Pipes to It ---
def add_extra_items_to_shipment(shipment_id, pipe_ids):
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Check for valid In-Stock pipes
        placeholders = ','.join(['?'] * len(pipe_ids))
        query = f"SELECT id FROM labels WHERE id IN ({placeholders}) AND dispatched_at IS NULL AND (dispatched_by IS NULL OR dispatched_by != 'rejected')"
        valid_pipes = cur.execute(query, pipe_ids).fetchall()
        
        if not valid_pipes: return False, "No valid in-stock pipes found."
        
        valid_ids = [row['id'] for row in valid_pipes]
        
        # Mark them as Dispatched
        timestamp = datetime.datetime.now().isoformat()
        update_placeholders = ','.join(['?'] * len(valid_ids))
        cur.execute(f"UPDATE labels SET dispatched_at=?, dispatched_by='EditAdd', shipment_id=? WHERE id IN ({update_placeholders})", (timestamp, shipment_id, *valid_ids))
        
        # Update Shipment Totals
        stats = cur.execute("SELECT COUNT(*), SUM(weight_g) FROM labels WHERE shipment_id=?", (shipment_id,)).fetchone()
        cur.execute("UPDATE shipments SET total_pipes=?, total_weight=? WHERE id=?", (stats[0], stats[1] if stats[1] else 0, shipment_id))
        
        conn.commit()
        return True, f"Successfully added {len(valid_ids)} pipes."

# --- 1. Get Full Shipment Details (Meta + Items) ---
def get_shipment_full_details(challan_no):
    with get_db_connection() as conn:
        # Get Shipment Meta
        shipment = conn.execute("SELECT * FROM shipments WHERE challan_no = ?", (challan_no,)).fetchone()
        if not shipment: return None
        
        # Get the Pipes currently inside it
        pipes = conn.execute("SELECT * FROM labels WHERE shipment_id = ?", (shipment['id'],)).fetchall()
        
        return {
            "meta": dict(shipment),
            "items": [dict(p) for p in pipes]
        }

# --- 2. Remove Single Pipe from Shipment ---
def remove_pipe_from_shipment(pipe_id):
    with get_db_connection() as conn:
        # 1. Get the pipe to find its shipment_id
        pipe = conn.execute("SELECT shipment_id FROM labels WHERE id = ?", (pipe_id,)).fetchone()
        if not pipe or not pipe['shipment_id']: return False, "Pipe not in a shipment"
        
        s_id = pipe['shipment_id']
        
        # 2. "Undispatch" the pipe (Set to NULL)
        conn.execute("UPDATE labels SET dispatched_at = NULL, dispatched_by = NULL, shipment_id = NULL WHERE id = ?", (pipe_id,))
        
        # 3. Recalculate Shipment Totals
        stats = conn.execute("SELECT COUNT(*), SUM(weight_g) FROM labels WHERE shipment_id=?", (s_id,)).fetchone()
        new_count = stats[0]
        new_weight = stats[1] if stats[1] else 0
        
        conn.execute("UPDATE shipments SET total_pipes=?, total_weight=? WHERE id=?", (new_count, new_weight, s_id))
        conn.commit()
        
        return True, "Pipe removed and stock restored."

# --- PROCESS RETURN (CREDIT NOTE) ---
import json # Add this at the top of file if missing

# --- PROCESS RETURN (Updated with History) ---
def process_return_voucher(pipe_ids):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # --- STEP 1: Identify Source Challans (BEFORE resetting) ---
        placeholders = ','.join(['?'] * len(pipe_ids))
        
        # Find which shipments these pipes currently belong to
        # We group by shipment_id to get unique shipments
        shipment_rows = cursor.execute(f"""
            SELECT DISTINCT s.challan_no
            FROM labels l
            JOIN shipments s ON l.shipment_id = s.id
            WHERE l.id IN ({placeholders})
        """, pipe_ids).fetchall()
        
        # Create a string like "CH-101, CH-105" (in case returns are mixed)
        challan_list = [row['challan_no'] for row in shipment_rows if row['challan_no']]
        challan_source_str = ", ".join(challan_list) if challan_list else "Unknown"

        # --- STEP 2: Update Shipment Totals (The "278 vs 256" Fix) ---
        # Get counts per shipment to deduct correctly
        deduction_rows = cursor.execute(f"""
            SELECT shipment_id, COUNT(*) as qty, SUM(weight_g) as wt 
            FROM labels 
            WHERE id IN ({placeholders}) AND shipment_id IS NOT NULL
            GROUP BY shipment_id
        """, pipe_ids).fetchall()

        for row in deduction_rows:
            s_id = row['shipment_id']
            qty = row['qty']
            wt = row['wt'] if row['wt'] else 0
            cursor.execute("UPDATE shipments SET total_pipes = MAX(0, total_pipes - ?), total_weight = MAX(0, total_weight - ?) WHERE id = ?", (qty, wt, s_id))
        
        # --- STEP 3: Create Voucher Record (WITH Challan info) ---
        timestamp = datetime.datetime.now().isoformat()
        ids_string = json.dumps(pipe_ids)
        
        cursor.execute("""
            INSERT INTO return_vouchers (created_at, total_pipes, pipe_ids_json, challan_source) 
            VALUES (?, ?, ?, ?)
        """, (timestamp, len(pipe_ids), ids_string, challan_source_str))
        
        new_voucher_id = cursor.lastrowid
        
        # --- STEP 4: Reset Pipes (Back to Stock) ---
        cursor.execute(f"""
            UPDATE labels 
            SET dispatched_at = NULL, shipment_id = NULL, dispatched_by = NULL 
            WHERE id IN ({placeholders})
        """, pipe_ids)
        
        conn.commit()
        
        return True, new_voucher_id