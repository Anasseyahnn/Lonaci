"""Suivi prospectif hors-échantillon du signal 'fréquence historique' repéré
en recherche (walk-forward rétrospectif : +23.7% sur les jeux Digital, 5/6
fenêtres significatives). Contrairement aux backtests précédents, ce script
enregistre une prédiction AVANT de connaître le résultat du prochain tirage,
puis la résout une fois le résultat scrapé — vraie validation prospective,
pas rétrospective.

Groupe signal  : jeux Digital (RNG logiciel suspecté).
Groupe témoin  : jeux à boules physiques, mêmes règles de prédiction — sert
                 à vérifier que le tracker ne "détecte" pas un edge par simple
                 artefact de méthode. Si le témoin dérive lui aussi vers un
                 edge positif stable dans la durée, c'est la méthode qui est
                 en cause, pas un vrai biais Digital.

Boucle à chaque exécution (déclenchée après l'import des nouveaux tirages) :
  1. Résoudre les prédictions en attente dont un nouveau tirage est arrivé.
  2. Générer la prédiction suivante pour chaque jeu qui n'en a pas déjà une
     en attente, à partir de tout l'historique disponible à cet instant.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

MODEL_VERSION = "freq_top5_v1"
TOP_K = 5
MIN_HISTORY = 30  # pas de prédiction tant qu'il y a moins de tirages que ça pour ce jeu

DIGITAL_GAMES = ['Digital Reveil 7h', 'Digital Reveil 8h', 'Digital 21h', 'Digital 22h', 'Digital 23h']
CONTROL_GAMES = ['Special Weekend 1h', 'Special Weekend 3h', 'Wari', 'Soutra', 'National']

WINNING_COLS = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_predictions_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL,
            group_label TEXT NOT NULL,
            model_version TEXT NOT NULL,
            training_cutoff_date TEXT NOT NULL,
            n_draws_used INTEGER NOT NULL,
            predicted_numbers TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            actual_date TEXT,
            actual_numbers TEXT,
            n_correct INTEGER,
            resolved_at TEXT,
            UNIQUE(game, training_cutoff_date)
        )
    ''')
    conn.commit()


def resolve_pending_predictions(conn):
    """Pour chaque prédiction non résolue, cherche si un nouveau tirage du
    même jeu est arrivé après le cutoff d'entraînement, et la clôture."""
    cur = conn.cursor()
    pending = cur.execute(
        "SELECT id, game, training_cutoff_date, predicted_numbers FROM predictions WHERE actual_numbers IS NULL"
    ).fetchall()

    resolved_count = 0
    for pred_id, game, cutoff, predicted_json in pending:
        row = cur.execute(
            f"""SELECT date, {', '.join(WINNING_COLS)} FROM draws
                WHERE game = ? AND date > ?
                ORDER BY date ASC, id ASC LIMIT 1""",
            (game, cutoff)
        ).fetchone()
        if row is None:
            continue

        actual_date = row[0]
        actual_numbers = [int(x) for x in row[1:] if x is not None]
        predicted_numbers = json.loads(predicted_json)
        n_correct = len(set(predicted_numbers) & set(actual_numbers))

        cur.execute(
            """UPDATE predictions
               SET actual_date = ?, actual_numbers = ?, n_correct = ?, resolved_at = ?
               WHERE id = ?""",
            (actual_date, json.dumps(actual_numbers), n_correct,
             datetime.now(timezone.utc).isoformat(), pred_id)
        )
        resolved_count += 1

    conn.commit()
    return resolved_count


def generate_new_predictions(conn, games, group_label):
    cur = conn.cursor()
    created = 0
    for game in games:
        has_pending = cur.execute(
            "SELECT 1 FROM predictions WHERE game = ? AND actual_numbers IS NULL", (game,)
        ).fetchone()
        if has_pending:
            continue

        df = pd.read_sql_query(
            f"SELECT date, {', '.join(WINNING_COLS)} FROM draws WHERE game = ? ORDER BY date ASC, id ASC",
            conn, params=(game,)
        )
        if len(df) < MIN_HISTORY:
            continue

        all_numbers = df[WINNING_COLS].values.flatten()
        all_numbers = all_numbers[~pd.isna(all_numbers)].astype(int)
        top5 = pd.Series(all_numbers).value_counts().head(TOP_K).index.tolist()
        cutoff_date = df['date'].max()

        try:
            cur.execute(
                """INSERT INTO predictions
                   (game, group_label, model_version, training_cutoff_date, n_draws_used,
                    predicted_numbers, predicted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (game, group_label, MODEL_VERSION, cutoff_date, len(df),
                 json.dumps(sorted(top5)), datetime.now(timezone.utc).isoformat())
            )
            created += 1
        except sqlite3.IntegrityError:
            pass  # déjà une prédiction pour ce cutoff exact (pas de nouveau tirage depuis)

    conn.commit()
    return created


def permutation_pvalue(predicted_lists, observed_correct, n_perm=5000, seed=42):
    """H0 : les tirages résolus sont purement aléatoires (5 parmi 90).
    Simule n_perm fois la somme de bonnes réponses sous H0 pour les MÊMES
    ensembles prédits, retourne le p-value unilatéral (observé >= simulé)."""
    rng = np.random.default_rng(seed)
    null_sums = np.zeros(n_perm)
    for i in range(n_perm):
        total = 0
        for predicted in predicted_lists:
            random_draw = set((rng.choice(90, size=5, replace=False) + 1).tolist())
            total += len(random_draw & set(predicted))
        null_sums[i] = total
    return (null_sums >= observed_correct).mean()


def scoreboard(conn, group_label, label):
    df = pd.read_sql_query(
        "SELECT game, predicted_numbers, actual_numbers, n_correct FROM predictions "
        "WHERE group_label = ? AND n_correct IS NOT NULL",
        conn, params=(group_label,)
    )
    print(f"\n=== SCOREBOARD PROSPECTIF — {label} ({group_label}) ===")
    if len(df) == 0:
        print("Aucune prédiction résolue pour l'instant.")
        return

    n = len(df)
    observed_mean = df['n_correct'].mean()
    random_expectation = 5 * 5 / 90.0
    improvement = (observed_mean - random_expectation) / random_expectation * 100

    print(f"Prédictions résolues : {n}")
    print(f"Moyenne de bons numéros : {observed_mean:.4f} (aléatoire théorique : {random_expectation:.4f})")
    print(f"Amélioration vs aléatoire : {improvement:+.2f}%")

    if n < 10:
        print(f"-> Encore trop peu de points ({n}) pour un test statistique fiable. "
              f"Continuer la collecte avant d'interpréter.")
        return

    predicted_lists = [json.loads(x) for x in df['predicted_numbers']]
    observed_correct = int(df['n_correct'].sum())
    p_val = permutation_pvalue(predicted_lists, observed_correct)
    print(f"Test de permutation (H0 = tirages purement aléatoires, {n} tirages résolus) : p-value = {p_val:.4f}")
    if p_val < 0.05:
        print("-> Significatif à ce stade. Continuer à accumuler pour confirmer la stabilité dans le temps.")
    else:
        print("-> Pas (encore) significatif. Pas de conclusion à tirer prématurément.")


def run_tracker():
    conn = get_conn()
    init_predictions_table(conn)

    n_resolved = resolve_pending_predictions(conn)
    print(f"[prospective_tracker] {n_resolved} prédiction(s) résolue(s) avec de nouveaux tirages.")

    n_new_digital = generate_new_predictions(conn, DIGITAL_GAMES, 'digital')
    n_new_control = generate_new_predictions(conn, CONTROL_GAMES, 'control')
    print(f"[prospective_tracker] {n_new_digital} nouvelle(s) prédiction(s) Digital, "
          f"{n_new_control} nouvelle(s) prédiction(s) témoin.")

    scoreboard(conn, 'digital', 'JEUX DIGITAL (signal recherché)')
    scoreboard(conn, 'control', 'JEUX TÉMOINS (physiques, doit rester ~0%)')

    conn.close()


if __name__ == '__main__':
    run_tracker()
