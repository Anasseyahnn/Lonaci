from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import os
import sys

# Add parent directory to path to import analysis tools
API_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(API_DIR, '..')))

from analysis.predictor import generate_prediction, get_global_frequencies, get_game_frequencies, get_game_statistics, list_games
from analysis.prospective_tracker import compute_scoreboard, get_conn as get_tracker_conn
from analysis.game_config import DIGITAL_GAMES, CONTROL_GAMES

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
        "version": "2.0.0"
    }

@app.get("/api/games")
def get_games():
    """Liste des jeux disponibles avec leur mécanisme de tirage — un client
    doit choisir un jeu avant de demander une prédiction, jamais une
    prédiction 'tous jeux confondus' (voir /api/predictions)."""
    return {"games": list_games()}

@app.get("/api/predictions")
def get_predictions(game: str, limit: int = 5):
    """
    Prédiction fréquentiste PAR JEU (freq_top5_v1). Le paramètre `game` est
    obligatoire : un jeu Digital (RNG logiciel suspecté) et un jeu physique
    (mécanique) ne partagent pas le même mécanisme de tirage, et pooler leurs
    tirages pour une seule prédiction globale — comme le faisait cette route
    jusqu'ici — dilue ou fabrique un signal qui n'existe dans aucun des deux.
    """
    try:
        result = generate_prediction(game, top_k=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result['mechanism'] == 'digital':
        mechanism_note = "Jeu Digital : biais éventuel = faiblesse du générateur logiciel, jamais une usure mécanique."
    elif result['mechanism'] == 'physique':
        mechanism_note = "Jeu physique : sert normalement de témoin (biais mécanique attendu proche de zéro)."
    else:
        mechanism_note = (
            "Mécanisme de tirage non classifié pour ce jeu — impossible de dire si un biais serait "
            "plausible (logiciel) ou non (mécanique). Ne pas interpréter les probabilités ci-dessous "
            "comme un signal avant classification."
        )
    return {
        **result,
        "recommendation_logic": (
            f"Fréquence historique calculée sur ce jeu uniquement ({result['n_draws_used']} tirages). "
            f"{mechanism_note} Voir /api/models-comparison pour la validation prospective hors-échantillon."
        ),
    }

@app.get("/api/statistics")
def get_stats(game: str | None = None):
    """
    Statistiques de fréquence. Sans `game`, renvoie les stats tous jeux
    confondus — à titre descriptif uniquement (ne pas en déduire un biais :
    ça mélange des jeux Digital et physiques). Avec `game`, renvoie les
    stats propres à ce jeu, seules exploitables pour juger d'un biais.
    """
    game_stats = get_game_statistics()

    if game is not None:
        counts, probs, n_draws = get_game_frequencies(game)
        if n_draws == 0:
            raise HTTPException(status_code=400, detail=f"Aucun tirage trouvé pour '{game}'.")
        expected = n_draws * 5 / 90.0
        scope = "per_game"
    else:
        counts, probs = get_global_frequencies()
        expected = (game_stats['total_draws'] * 5) / 90.0
        scope = "all_games_pooled_descriptive_only"

    top5 = counts.sort_values(ascending=False).head(5)
    top5_list = [{"number": int(n), "count": int(c), "expected": round(expected, 2), "ratio": round(c / expected, 3)} for n, c in top5.items()]

    bottom5 = counts.sort_values(ascending=True).head(5)
    bottom5_list = [{"number": int(n), "count": int(c), "expected": round(expected, 2), "ratio": round(c / expected, 3)} for n, c in bottom5.items()]

    return {
        "scope": scope,
        "game": game,
        "general": game_stats,
        "expected_occurrences": round(expected, 2),
        "most_frequent": top5_list,
        "least_frequent": bottom5_list
    }

@app.get("/api/history")
def get_history(limit: int = 50, game: str | None = None):
    conn = get_db_connection()
    query = """
        SELECT date, game,
               winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws
        WHERE is_valid = 1
    """
    params = []
    if game is not None:
        query += " AND game = ?"
        params.append(game)
    query += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)

    df = pd.read_sql_query(query, conn, params=params)
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
    """
    Scoreboard prospectif réel — lu en direct depuis la table `predictions`
    de prospective_tracker.py (walk-forward hors-échantillon, par jeu), au
    lieu des valeurs figées d'une exécution ponctuelle de l'ancien train.py
    (globalement poolées, jamais mises à jour). Inclut le taux de tirages
    atteignant le seuil de gain réel (2N minimum), pas seulement la moyenne
    de bons numéros — voir [[project-lonaci-model-challenge]] pour le
    contexte : la moyenne seule peut s'améliorer sans qu'aucun pari ne
    devienne gagnant.
    """
    conn = get_tracker_conn()
    try:
        signal_freq = compute_scoreboard(conn, 'digital', 'freq_top5_v1')
        signal_markov = compute_scoreboard(conn, 'digital', 'markov1_v1')
        control = compute_scoreboard(conn, 'control', 'freq_top5_v1')
    finally:
        conn.close()

    return {
        "random_baseline_mean_correct": 5 * 5 / 90.0,
        "digital_games": DIGITAL_GAMES,
        "control_games": CONTROL_GAMES,
        "models": {
            "freq_top5_v1_digital": signal_freq,
            "markov1_v1_digital": signal_markov,
            "freq_top5_v1_control": control,
        },
        "note": "control = jeux physiques (témoin, doit rester proche du hasard théorique)."
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
