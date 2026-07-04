import sqlite3
import pandas as pd
import numpy as np
import os
import json

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_global_frequencies():
    """
    Calcule les probabilités historiques de chaque numéro (1 à 90) sur toute la base de données.
    """
    conn = get_db_connection()
    query = "SELECT winning_1, winning_2, winning_3, winning_4, winning_5 FROM draws"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    all_numbers = df.values.flatten()
    total_drawn = len(all_numbers)
    
    # Frequencies
    counts = pd.Series(all_numbers).value_counts().reindex(range(1, 91), fill_value=0)
    
    # Probabilities
    probs = counts / total_drawn
    
    return counts, probs

def generate_prediction(top_k=5):
    """
    Génère la prédiction optimale basée sur le biais statique global identifié.
    Comme le test temporel montre une totale indépendance entre tirages, la meilleure stratégie
    scientifique est de parier sur les boules ayant le plus fort taux d'apparition historique (les plus lourdes/usées).
    """
    counts, probs = get_global_frequencies()
    
    # Sort numbers by probability descending
    top_numbers = probs.sort_values(ascending=False).head(top_k)
    
    predictions = []
    for num, prob in top_numbers.items():
        predictions.append({
            "number": int(num),
            "occurrences": int(counts[num]),
            "probability": float(prob),
            "percentage_above_expected": float((counts[num] - (len(probs) * 5 / 90)) / (len(probs) * 5 / 90) * 100)
        })
        
    return predictions

def get_game_statistics():
    """
    Récupère des statistiques globales sur le jeu pour l'affichage mobile.
    """
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT date, game FROM draws", conn)
    conn.close()
    
    total_draws = len(df)
    games_count = df['game'].value_counts().to_dict()
    
    return {
        "total_draws": total_draws,
        "first_draw_date": df['date'].min(),
        "last_draw_date": df['date'].max(),
        "draws_by_game": games_count
    }

if __name__ == '__main__':
    # Test prediction
    preds = generate_prediction()
    print("=== PRÉDICTIONS OPTIMALES (TOP 5) ===")
    for i, p in enumerate(preds, 1):
        print(f"{i}. Numéro {p['number']} : Probabilité {p['probability']:.4f} ({p['occurrences']} sorties)")
        
    stats_game = get_game_statistics()
    print(f"\nNombre total de tirages en BD : {stats_game['total_draws']}")
