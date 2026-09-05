import sqlite3
import json
import os
import sys

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
            is_valid INTEGER NOT NULL DEFAULT 1,
            UNIQUE(date, game)
        )
    ''')

    # Migration pour une base créée avant l'ajout de is_valid (CREATE TABLE IF
    # NOT EXISTS n'ajoute pas la colonne à une table déjà existante).
    cursor.execute("PRAGMA table_info(draws)")
    if 'is_valid' not in [c[1] for c in cursor.fetchall()]:
        cursor.execute("ALTER TABLE draws ADD COLUMN is_valid INTEGER NOT NULL DEFAULT 1")

    conn.commit()
    conn.close()
    print("Database initialized successfully.")


# Doublons de publication confirmés côté source officielle LONACI (vérifié en
# direct sur l'API le 2026-09-05, cf. project_lonaci_alignement_comprehension_jeu.md) :
# le site a republié le résultat de la semaine précédente au lieu du nouveau
# tirage, pour ces 2 jeux à des semaines voisines de décembre 2024. Isolé dans
# le temps, rien de similaire ailleurs sur 3 ans de données. Idempotent — sûr
# à ré-exécuter à chaque import (INSERT OR IGNORE ne recrée pas ces lignes,
# donc pas besoin de refaire cette étape sauf réimport complet depuis zéro).
KNOWN_INVALID_DRAWS = [
    {'game': 'National', 'date': '2024-12-14', 'winning': (89, 3, 49, 39, 50)},
    {'game': 'Lucky Tuesday', 'date': '2024-12-17', 'winning': (54, 7, 77, 61, 36)},
]


def mark_known_invalid_draws():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    marked = 0
    for d in KNOWN_INVALID_DRAWS:
        cursor.execute(
            """UPDATE draws SET is_valid = 0
               WHERE game = ? AND date = ?
                 AND winning_1 = ? AND winning_2 = ? AND winning_3 = ?
                 AND winning_4 = ? AND winning_5 = ?""",
            (d['game'], d['date'], *d['winning'])
        )
        marked += cursor.rowcount
    conn.commit()
    conn.close()
    if marked:
        print(f"{marked} tirage(s) invalide(s) connu(s) marqué(s) is_valid=0.")

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
    mark_known_invalid_draws()

    sys.path.append(os.path.abspath(os.path.join(DB_DIR, '..')))
    from analysis.prospective_tracker import run_tracker
    run_tracker()
