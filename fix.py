import sqlite3

# Connect to the database
conn = sqlite3.connect("pvc_factory.db")
cursor = conn.cursor()

# 1. Run the update
cursor.execute("UPDATE labels SET dispatched_by = NULL WHERE id IN (1357,2234)")

# 2. Check if it worked
cursor.execute("SELECT id, pipe_name, weight_g FROM labels WHERE id = 65")
row = cursor.fetchone()

if row:
    print(f"✅ Success! Pipe #{row[0]} ({row[1]}) weight is now: {row[2]}")
else:
    print("❌ Error: Pipe ID 534 not found.")

# 3. SAVE the changes (Crucial Step)
conn.commit()
conn.close()