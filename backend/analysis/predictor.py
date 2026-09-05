import sqlite3
import pandas as pd
import numpy as np
import os
import sys

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

# analysis/ n'est pas un package (pas de __init__.py) : selon qu'on est lancé
# en script ou importé via `analysis.predictor` depuis l'API, son propre
# dossier n'est pas toujours sur sys.path — on le force pour que
# `from game_config import ...` fonctionne dans les deux cas.
if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)

from game_config import classify_game

TOP_K = 5
MIN_HISTORY = 30  # même seuil que model_challenge/compare_models.py et prospective_tracker.py


def get_db_connection():
    return sqlite3.connect(DB_PATH)


def list_games():
    """Liste des jeux présents en base, pour que l'API/l'app proposent un sélecteur."""
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT DISTINCT game FROM draws ORDER BY game", conn)
    conn.close()
    return [{"game": g, "mechanism": classify_game(g)} for g in df['game'].tolist()]


def get_global_frequencies():
    """
    Fréquences historiques tous jeux confondus — UNIQUEMENT à usage descriptif
    (ex. "combien de tirages en base au total"), jamais comme base d'une
    prédiction : ça mélange des jeux Digital (RNG logiciel suspecté) et des
    jeux physiques (mécanique), deux mécanismes de tirage différents dont un
    biais éventuel n'aurait ni la même cause ni la même validité.
    """
    conn = get_db_connection()
    query = "SELECT winning_1, winning_2, winning_3, winning_4, winning_5 FROM draws"
    df = pd.read_sql_query(query, conn)
    conn.close()

    all_numbers = df.values.flatten()
    total_drawn = len(all_numbers)

    counts = pd.Series(all_numbers).value_counts().reindex(range(1, 91), fill_value=0)
    probs = counts / total_drawn

    return counts, probs


def get_game_frequencies(game):
    """Fréquences historiques des numéros gagnants POUR CE JEU UNIQUEMENT."""
    conn = get_db_connection()
    query = (
        "SELECT winning_1, winning_2, winning_3, winning_4, winning_5 "
        "FROM draws WHERE game = ? ORDER BY date ASC, id ASC"
    )
    df = pd.read_sql_query(query, conn, params=(game,))
    conn.close()

    n_draws = len(df)
    all_numbers = df.values.flatten()
    total_drawn = len(all_numbers)

    counts = pd.Series(all_numbers).value_counts().reindex(range(1, 91), fill_value=0)
    probs = counts / total_drawn if total_drawn else counts.astype(float)

    return counts, probs, n_draws


def generate_prediction(game, top_k=TOP_K):
    """
    Prédiction fréquentiste PAR JEU (freq_top5_v1, tel que validé dans
    prospective_tracker.py) : jamais de pool inter-jeux. Un jeu Digital et un
    jeu physique ne partagent ni le même mécanisme de tirage ni la même
    hypothèse de biais — les traiter comme une seule population de tirages
    (comme le faisait l'ancienne version de cette fonction) dilue le signal
    Digital dans le bruit des jeux physiques et vice-versa.

    Lève ValueError si l'historique du jeu est trop court (< MIN_HISTORY) —
    pas de prédiction fantôme sur une poignée de tirages nong représentatifs.
    """
    counts, probs, n_draws = get_game_frequencies(game)
    if n_draws < MIN_HISTORY:
        raise ValueError(
            f"Historique insuffisant pour '{game}' ({n_draws} tirages, "
            f"minimum {MIN_HISTORY} requis pour une fréquence fiable)."
        )

    expected = n_draws * 5 / 90.0
    top_numbers = probs.sort_values(ascending=False).head(top_k)

    predictions = []
    for num, prob in top_numbers.items():
        predictions.append({
            "number": int(num),
            "occurrences": int(counts[num]),
            "probability": float(prob),
            "percentage_above_expected": float((counts[num] - expected) / expected * 100) if expected else 0.0,
        })

    return {
        "game": game,
        "mechanism": classify_game(game),
        "n_draws_used": n_draws,
        "predictions": predictions,
    }


def get_game_statistics():
    """
    Statistiques globales sur le jeu pour l'affichage mobile (compte de
    tirages par jeu, dates) — usage purement descriptif, pas de prédiction.
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
        "draws_by_game": games_count,
    }


if __name__ == '__main__':
    print("=== JEUX DISPONIBLES ===")
    for g in list_games():
        print(f"  {g['game']:22s} ({g['mechanism']})")

    print("\n=== PRÉDICTIONS PAR JEU (TOP 5) ===")
    for g in list_games():
        try:
            result = generate_prediction(g['game'])
        except ValueError as e:
            print(f"\n{g['game']} : {e}")
            continue
        print(f"\n{result['game']} ({result['mechanism']}, {result['n_draws_used']} tirages) :")
        for i, p in enumerate(result['predictions'], 1):
            print(f"  {i}. Numéro {p['number']:2d} — probabilité {p['probability']:.4f} "
                  f"({p['occurrences']} sorties, {p['percentage_above_expected']:+.1f}% vs attendu)")

    stats_game = get_game_statistics()
    print(f"\nNombre total de tirages en BD : {stats_game['total_draws']}")
