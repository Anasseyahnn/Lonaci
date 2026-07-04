import sqlite3
import json
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'lonaci.db')
RESULTS_PATH = os.path.abspath(os.path.join(DB_DIR, '..', 'scraper', 'results.json'))

def init_db():
    print(f"Initializing database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            game TEXT,
            winning_1 INTEGER,
            winning_2 INTEGER,
            winning_3 INTEGER,
            winning_4 INTEGER,
            winning_5 INTEGER,
            machine_1 INTEGER,
            machine_2 INTEGER,
            machine_3 INTEGER,
            machine_4 INTEGER,
            machine_5 INTEGER,
            UNIQUE(date, game)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def import_json_data():
    if not os.path.exists(RESULTS_PATH):
        print(f"No results.json found at: {RESULTS_PATH}. Please run the scraper first.")
        return
        
    print(f"Loading data from: {RESULTS_PATH}")
    with open(RESULTS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Found {len(data)} records in results.json. Importing to database...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    imported_count = 0
    skipped_count = 0
    
    for item in data:
        date = item.get('date')
        game = item.get('game')
        w = item.get('winningNumbers', [])
        m = item.get('machineNumbers', [])
        
        # Pad arrays if they are shorter than 5 elements
        w = (w + [None] * 5)[:5]
        m = (m + [None] * 5)[:5]
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO draws (
                    date, game, 
                    winning_1, winning_2, winning_3, winning_4, winning_5,
                    machine_1, machine_2, machine_3, machine_4, machine_5
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (date, game, w[0], w[1], w[2], w[3], w[4], m[0], m[1], m[2], m[3], m[4]))
            
            if cursor.rowcount > 0:
                imported_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"Error importing row ({date}, {game}): {e}")
            
    conn.commit()
    conn.close()
    print(f"Import complete. Imported: {imported_count} draws, Skipped (duplicates): {skipped_count} draws.")

if __name__ == '__main__':
    init_db()
    import_json_data()
