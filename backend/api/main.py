from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import os
import sys

# Add parent directory to path to import analysis tools
API_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(API_DIR, '..')))

from analysis.predictor import generate_prediction, get_global_frequencies, get_game_statistics

app = FastAPI(title="Lonaci Predictor API", description="API de prédiction et statistiques pour le Loto Bonheur (Côte d'Ivoire)")

# Enable CORS for Mobile App requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.abspath(os.path.join(API_DIR, '..', 'database', 'lonaci.db'))

def get_db_connection():
    return sqlite3.connect(DB_PATH)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Lonaci Predictor API",
        "version": "1.0.0"
    }

@app.get("/api/predictions")
def get_predictions(limit: int = 5):
    preds = generate_prediction(top_k=limit)
    return {
        "predictions": preds,
        "recommendation_logic": "Biais statique global (tirages statistiquement non uniformes, p-value < 0.05. Absence constatée de mémoire temporelle)."
    }

@app.get("/api/statistics")
def get_stats():
    # Game stats
    game_stats = get_game_statistics()
    
    # Frequencies
    counts, probs = get_global_frequencies()
    
    # Expected draws per number
    total_draws = game_stats['total_draws']
    expected = (total_draws * 5) / 90.0
    
    # Top 5 most frequent
    top5 = counts.sort_values(ascending=False).head(5)
    top5_list = [{"number": int(n), "count": int(c), "expected": round(expected, 2), "ratio": round(c / expected, 3)} for n, c in top5.items()]
    
    # Bottom 5 least frequent
    bottom5 = counts.sort_values(ascending=True).head(5)
    bottom5_list = [{"number": int(n), "count": int(c), "expected": round(expected, 2), "ratio": round(c / expected, 3)} for n, c in bottom5.items()]
    
    return {
        "general": game_stats,
        "expected_occurrences": round(expected, 2),
        "most_frequent": top5_list,
        "least_frequent": bottom5_list
    }

@app.get("/api/history")
def get_history(limit: int = 50):
    conn = get_db_connection()
    query = f"""
        SELECT date, game, 
               winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws
        ORDER BY date DESC, id DESC
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row['date'])[:10],
            "game": row['game'],
            "winning_numbers": [int(row[f'winning_{i}']) for i in range(1, 6) if row[f'winning_{i}'] is not None]
        })
        
    return {
        "count": len(records),
        "draws": records
    }

@app.get("/api/models-comparison")
def get_models():
    # Grounded values from F:\Startup\Lonaci\backend\analysis\train.py output
    return {
        "validation_metric": "Moyenne de boules devinées par tirage dans un pari de 5 numéros (Top 5)",
        "random_baseline": 0.278,
        "models": [
            {
                "name": "Baseline Historique (Top 5 Fréquent)",
                "correct_guesses": 0.3139,
                "improvement": "+12.92%",
                "at_least_1_win": "28.82%",
                "description": "Exploite le biais mécanique global. Modèle optimal en raison de l'indépendance temporelle des tirages."
            },
            {
                "name": "Random Forest",
                "correct_guesses": 0.2974,
                "improvement": "+6.97%",
                "at_least_1_win": "27.57%",
                "description": "Modèle d'arbre de décision. Introduit du bruit dû aux paramètres temporels."
            },
            {
                "name": "Régression Logistique",
                "correct_guesses": 0.2842,
                "improvement": "+2.25%",
                "at_least_1_win": "25.97%",
                "description": "Modèle linéaire simple."
            },
            {
                "name": "XGBoost",
                "correct_guesses": 0.2757,
                "improvement": "-0.83%",
                "at_least_1_win": "25.63%",
                "description": "Sur-apprentissage sur les fluctuations à court terme."
            }
        ]
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
