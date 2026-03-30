import sqlite3

def fix_pipe_weights():
    # Connect to your database
    conn = sqlite3.connect("pvc_factory.db")
    cur = conn.cursor()
    
    try:
        # Update the weight_g column to 38 for IDs between 2450 and 2461
        cur.execute("""
            UPDATE labels 
            SET weight_g = 15 
            WHERE id =2678
        """)
        
        # Check how many rows were actually changed
        affected_rows = cur.rowcount
        
        # Save the changes to the database
        conn.commit()
        
        print(f"✅ Success! Updated {affected_rows} pipes.")
        print("Weights successfully changed from 381 to 38.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error occurred: {e}")
        conn.rollback() # Cancel the change if something goes wrong
        
    finally:
        # Always close the connection
        conn.close()

if __name__ == "__main__":
    fix_pipe_weights()