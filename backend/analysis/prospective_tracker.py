"""Suivi prospectif hors-échantillon de plusieurs modèles candidats, sur les
jeux Digital (groupe signal) et les jeux à boules physiques (groupe témoin).
Ce script enregistre une prédiction AVANT de connaître le résultat du
prochain tirage, puis la résout une fois le résultat scrapé — vraie
validation prospective, pas rétrospective.

Historique de la méthodologie (voir backend/analysis/model_challenge/ pour
le détail complet du challenge de modèles, 2026-08) :
  - freq_top5_v1 est le modèle historique, repéré par backtest rétrospectif
    walk-forward (+23.7% sur Digital, 5/6 fenêtres significatives). Mais le
    suivi prospectif réel (hors-échantillon, jamais vu à l'entraînement) n'a
    montré AUCUN signal après 19 tirages résolus (p=0.9124, moyenne même
    inférieure au hasard) — la "significativité" rétrospective est très
    probablement un artefact du biais historique persistant sur le numéro 88
    (cf. eda_gaps_crossgame.py), pas un edge exploitable généralisable.
  - Un second challenge de modèles (Markov d'ordre 1, fréquence pondérée par
    récence/decay, régression logistique sur features engineered) a été fait
    par walk-forward strict sur les ~4100 tirages Digital disponibles.
    Résultat : freq_top5 (+11.1%) et markov1 (+7.0%) restent significatifs
    contre l'hasard après correction de Bonferroni EN RÉTROSPECTIF, mais leur
    différence mutuelle (Wilcoxon apparié) n'est PAS significative (p=0.25) —
    impossible de départager les deux sur la seule base du rétrospectif, qui
    est structurellement contaminé par le même biais historique persistant.
    freq_decay et ml_logreg ne battent pas le hasard après correction : ml
    abandonné (overfit probable, complexité non justifiée), freq_decay
    abandonné (pas significatif, redondant avec freq_top5).
  - Décision : plutôt que de trancher sur un rétrospectif structurellement
    biaisé, freq_top5_v1 ET markov1_v1 sont désormais suivis prospectivement
    EN PARALLÈLE sur les jeux Digital, avec leurs propres prédictions et leur
    propre scoreboard. Le vrai juge reste le hors-échantillon accumulé ici,
    pas le backtest.

Groupe signal  : jeux Digital (RNG logiciel suspecté) — freq_top5_v1 et
                 markov1_v1 suivis en parallèle.
Groupe témoin  : jeux à boules physiques, freq_top5_v1 uniquement — sert à
                 vérifier que le tracker ne "détecte" pas un edge par simple
                 artefact de méthode. Si le témoin dérive lui aussi vers un
                 edge positif stable dans la durée, c'est la méthode qui est
                 en cause, pas un vrai biais Digital.

Boucle à chaque exécution (déclenchée après l'import des nouveaux tirages) :
  1. Résoudre les prédictions en attente dont un nouveau tirage est arrivé.
  2. Générer la prédiction suivante pour chaque (jeu, modèle) qui n'en a pas
     déjà une en attente, à partir de tout l'historique disponible à cet instant.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import binom

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

MODEL_VERSION = "freq_top5_v1"
MARKOV_MODEL_VERSION = "markov1_v1"
DIGITAL_MODEL_VERSIONS = [MODEL_VERSION, MARKOV_MODEL_VERSION]
TOP_K = 5
MIN_HISTORY = 30  # pas de prédiction tant qu'il y a moins de tirages que ça pour ce jeu

DIGITAL_GAMES = ['Digital Reveil 7h', 'Digital Reveil 8h', 'Digital 21h', 'Digital 22h', 'Digital 23h']
CONTROL_GAMES = ['Special Weekend 1h', 'Special Weekend 3h', 'Wari', 'Soutra', 'National']

WINNING_COLS = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']

# Numéro(s) qui ont survécu à la correction de Bonferroni dans l'audit gaps
# (backend/analysis/eda_gaps_crossgame.py, commit a2ab476) : sur-représentés
# spécifiquement dans les jeux Digital vs jeux à boules physiques.
SUSPECT_NUMBERS = [88]


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
            UNIQUE(game, model_version, training_cutoff_date)
        )
    ''')
    conn.commit()
    _migrate_unique_constraint_if_needed(conn)


def _migrate_unique_constraint_if_needed(conn):
    """L'ancien schéma avait UNIQUE(game, training_cutoff_date), ce qui empêche
    d'enregistrer plusieurs modèles pour le même (jeu, date de cutoff). Migre
    vers UNIQUE(game, model_version, training_cutoff_date) si besoin, sans
    perte de données (30 lignes historiques, toutes freq_top5_v1)."""
    schema_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='predictions'"
    ).fetchone()[0]
    if 'UNIQUE(game, model_version, training_cutoff_date)' in schema_sql:
        return

    conn.execute('ALTER TABLE predictions RENAME TO predictions_old')
    conn.execute('''
        CREATE TABLE predictions (
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
            UNIQUE(game, model_version, training_cutoff_date)
        )
    ''')
    conn.execute('''
        INSERT INTO predictions (id, game, group_label, model_version, training_cutoff_date,
                                  n_draws_used, predicted_numbers, predicted_at,
                                  actual_date, actual_numbers, n_correct, resolved_at)
        SELECT id, game, group_label, model_version, training_cutoff_date,
               n_draws_used, predicted_numbers, predicted_at,
               actual_date, actual_numbers, n_correct, resolved_at
        FROM predictions_old
    ''')
    conn.execute('DROP TABLE predictions_old')
    conn.commit()
    print("[prospective_tracker] Schéma 'predictions' migré vers UNIQUE(game, model_version, training_cutoff_date).")


def generate_markov1_top5(df, top_k=TOP_K):
    """Chaîne de Markov d'ordre 1 : score(numéro b) = P(b apparaît au tirage
    suivant | a apparaît au tirage courant), moyenné sur les 5 numéros du
    dernier tirage connu, à partir des fréquences de transition observées sur
    tout l'historique disponible."""
    numbers = df[WINNING_COLS].values.astype(int)
    n = len(numbers)
    if n < 2:
        return None

    transition_count = np.zeros((91, 91))
    source_count = np.zeros(91)
    for i in range(n - 1):
        prev_numbers, cur_numbers = numbers[i], numbers[i + 1]
        for a in prev_numbers:
            source_count[a] += 1
            transition_count[a, cur_numbers] += 1

    last_draw = numbers[-1]
    denom = max(source_count[last_draw].sum(), 1)
    scores = np.zeros(91)
    scores[1:] = transition_count[last_draw, 1:].sum(axis=0) / denom

    idx = np.arange(91)
    order = np.lexsort((idx, -scores))
    top = [int(i) for i in order if i >= 1][:top_k]
    return sorted(top)


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


def generate_freq_top5(df, top_k=TOP_K):
    all_numbers = df[WINNING_COLS].values.flatten()
    all_numbers = all_numbers[~pd.isna(all_numbers)].astype(int)
    return sorted(pd.Series(all_numbers).value_counts().head(top_k).index.tolist())


PREDICTORS = {
    MODEL_VERSION: generate_freq_top5,
    MARKOV_MODEL_VERSION: generate_markov1_top5,
}


def generate_new_predictions(conn, games, group_label, model_versions):
    cur = conn.cursor()
    created = 0
    for game in games:
        df = None  # chargé paresseusement, une seule fois par jeu même si plusieurs modèles
        for model_version in model_versions:
            has_pending = cur.execute(
                "SELECT 1 FROM predictions WHERE game = ? AND model_version = ? AND actual_numbers IS NULL",
                (game, model_version)
            ).fetchone()
            if has_pending:
                continue

            if df is None:
                df = pd.read_sql_query(
                    f"SELECT date, {', '.join(WINNING_COLS)} FROM draws WHERE game = ? ORDER BY date ASC, id ASC",
                    conn, params=(game,)
                )
                if len(df) < MIN_HISTORY:
                    df = pd.DataFrame()  # marqueur "pas assez d'historique", évite de recharger
            if len(df) < MIN_HISTORY:
                continue

            predicted = PREDICTORS[model_version](df)
            if not predicted:
                continue
            cutoff_date = df['date'].max()

            try:
                cur.execute(
                    """INSERT INTO predictions
                       (game, group_label, model_version, training_cutoff_date, n_draws_used,
                        predicted_numbers, predicted_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (game, group_label, model_version, cutoff_date, len(df),
                     json.dumps(predicted), datetime.now(timezone.utc).isoformat())
                )
                created += 1
            except sqlite3.IntegrityError:
                pass  # déjà une prédiction pour ce (jeu, modèle, cutoff) exact

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


def scoreboard(conn, group_label, label, model_version=None):
    query = ("SELECT game, predicted_numbers, actual_numbers, n_correct FROM predictions "
             "WHERE group_label = ? AND n_correct IS NOT NULL")
    params = [group_label]
    if model_version:
        query += " AND model_version = ?"
        params.append(model_version)
    df = pd.read_sql_query(query, conn, params=params)

    model_suffix = f", modèle {model_version}" if model_version else ""
    print(f"\n=== SCOREBOARD PROSPECTIF — {label} ({group_label}{model_suffix}) ===")
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


def suspect_number_report(conn, number):
    """Suit un numéro suspect (ex: 88) sur les jeux Digital en comparant :
    - son taux de sortie AVANT le début du tracking prospectif (référence historique,
      c'est la période sur laquelle le biais a été détecté) ;
    - son taux de sortie DEPUIS le début du tracking (période prospective, non vue
      lors de la détection du biais).
    Calcule les p-values binomiales exactes de la période prospective sous les deux
    hypothèses (hasard pur p=5/90, biais historique p=taux observé avant tracking)
    pour situer où en est la preuve, sans conclure prématurément.
    """
    games_sql = ','.join('?' * len(DIGITAL_GAMES))

    tracking_start = conn.execute(
        "SELECT MIN(training_cutoff_date) FROM predictions WHERE group_label = 'digital'"
    ).fetchone()[0]

    print(f"\n=== SUIVI NUMÉRO SUSPECT {number} — JEUX DIGITAL ===")
    if tracking_start is None:
        print("Aucun suivi prospectif démarré pour l'instant.")
        return

    hit_clause = " OR ".join(f"{c} = ?" for c in WINNING_COLS)

    hist_hits, hist_total = conn.execute(
        f"""SELECT
                SUM(CASE WHEN {hit_clause} THEN 1 ELSE 0 END),
                COUNT(*)
            FROM draws WHERE game IN ({games_sql}) AND date <= ?""",
        (*([number] * len(WINNING_COLS)), *DIGITAL_GAMES, tracking_start)
    ).fetchone()
    prosp_hits, prosp_total = conn.execute(
        f"""SELECT
                SUM(CASE WHEN {hit_clause} THEN 1 ELSE 0 END),
                COUNT(*)
            FROM draws WHERE game IN ({games_sql}) AND date > ?""",
        (*([number] * len(WINNING_COLS)), *DIGITAL_GAMES, tracking_start)
    ).fetchone()

    hist_hits, hist_total = hist_hits or 0, hist_total or 0
    prosp_hits, prosp_total = prosp_hits or 0, prosp_total or 0
    p_random = 5 / 90
    p_biais = (hist_hits / hist_total) if hist_total else p_random

    print(f"Référence historique (jusqu'au {tracking_start}) : {hist_hits}/{hist_total} tirages "
          f"({100 * p_biais:.2f}% — hasard pur théorique : {100 * p_random:.2f}%)")

    if prosp_total == 0:
        print("Aucun tirage prospectif résolu depuis le début du tracking.")
        return

    p_taux = prosp_hits / prosp_total
    print(f"Période prospective (depuis {tracking_start}, hors-échantillon) : "
          f"{prosp_hits}/{prosp_total} tirages ({100 * p_taux:.2f}%)")

    # P(observer <= prosp_hits) sous chaque hypothèse, pour voir si le prospectif
    # s'écarte significativement du hasard OU du biais historique dans un sens ou l'autre.
    p_val_vs_random = 1 - binom.cdf(prosp_hits - 1, prosp_total, p_random) if prosp_hits > 0 else 1.0
    p_val_le_random = binom.cdf(prosp_hits, prosp_total, p_random)
    p_val_le_biais = binom.cdf(prosp_hits, prosp_total, p_biais)

    print(f"P(observer <= {prosp_hits} sorties sur {prosp_total} | hasard pur {100*p_random:.2f}%) = {p_val_le_random:.3f}")
    print(f"P(observer <= {prosp_hits} sorties sur {prosp_total} | biais historique {100*p_biais:.2f}%) = {p_val_le_biais:.3f}")
    print(f"P(observer >= {prosp_hits} sorties sur {prosp_total} | hasard pur {100*p_random:.2f}%) = {p_val_vs_random:.3f}")

    # Taille d'échantillon nécessaire pour trancher avec 80% de puissance, alpha 5% unilatéral.
    z_alpha, z_beta = 1.645, 0.84
    if p_biais > p_random:
        n_needed = ((z_alpha * (p_random * (1 - p_random)) ** 0.5
                     + z_beta * (p_biais * (1 - p_biais)) ** 0.5) / (p_biais - p_random)) ** 2
        n_needed = int(round(n_needed))
        restant = max(n_needed - prosp_total, 0)
        print(f"Échantillon nécessaire pour trancher (puissance 80%, alpha 5%) : ~{n_needed} tirages "
              f"({prosp_total}/{n_needed} déjà accumulés, {restant} restants, ~{restant / 5:.0f} jours à 5 tirages Digital/jour).")

    if prosp_total < 30:
        print("-> Échantillon prospectif encore trop petit pour conclure dans un sens ou l'autre. "
              "Continuer la collecte.")
    elif p_val_le_random < 0.05:
        print("-> Le numéro sort SIGNIFICATIVEMENT MOINS souvent que le hasard pur en prospectif : "
              "le biais historique ne se confirme pas, voire s'inverse. À surveiller de près.")
    elif p_val_vs_random < 0.05:
        print("-> Le numéro sort significativement PLUS souvent que le hasard pur en prospectif : "
              "cohérent avec le biais historique, signal qui se confirme.")
    else:
        print("-> Toujours dans la zone de bruit normal, ni confirmation ni infirmation claire à ce stade.")


def run_tracker():
    conn = get_conn()
    init_predictions_table(conn)

    n_resolved = resolve_pending_predictions(conn)
    print(f"[prospective_tracker] {n_resolved} prédiction(s) résolue(s) avec de nouveaux tirages.")

    n_new_digital = generate_new_predictions(conn, DIGITAL_GAMES, 'digital', DIGITAL_MODEL_VERSIONS)
    n_new_control = generate_new_predictions(conn, CONTROL_GAMES, 'control', [MODEL_VERSION])
    print(f"[prospective_tracker] {n_new_digital} nouvelle(s) prédiction(s) Digital "
          f"(modèles : {', '.join(DIGITAL_MODEL_VERSIONS)}), "
          f"{n_new_control} nouvelle(s) prédiction(s) témoin.")

    for model_version in DIGITAL_MODEL_VERSIONS:
        scoreboard(conn, 'digital', 'JEUX DIGITAL (signal recherché)', model_version=model_version)
    scoreboard(conn, 'control', 'JEUX TÉMOINS (physiques, doit rester ~0%)', model_version=MODEL_VERSION)

    for number in SUSPECT_NUMBERS:
        suspect_number_report(conn, number)

    conn.close()


if __name__ == '__main__':
    run_tracker()
