"""TabICLv2 (soda-inria, ICML 2026) — modèle de fondation tabulaire par
apprentissage en contexte (in-context learning), sans entraînement classique :
`fit` charge le contexte, `predict` fait tout en un forward pass.

Deux pipelines SÉPARÉS, comme demandé après la découverte que Gagnants et
Machine n'ont aucune numéro en commun sur le même tirage (règle structurelle
du jeu, pas un signal exploitable) :
  1. Prédire les GAGNANTS à partir de l'historique des GAGNANTS uniquement.
  2. Prédire les numéros MACHINE à partir de l'historique des MACHINE uniquement.

Même feature engineering que train.py (freq_10/50/100, delay, freq globale)
et même métrique (nb moyen de numéros corrects dans le top-5 prédit, comparé
à l'espérance aléatoire théorique de 0.278) pour une comparaison directe avec
la baseline, la régression logistique, Random Forest, XGBoost et le LSTM/GRU
déjà évalués.

Limite pratique assumée : TabICLv2 tourne ici sur CPU (pas de GPU dispo) et
son coût calcul croît avec la taille du contexte d'entraînement. On limite
donc le contexte aux ~2500 tirages les plus récents (~200k lignes de
features) plutôt que les 9195 tirages complets (~800k lignes), qui feraient
tourner l'inference pendant des heures sur CPU. C'est documenté ci-dessous,
pas caché.
"""
import sqlite3
import pandas as pd
import numpy as np
from tabicl import TabICLClassifier
import os
import time

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

RANDOM_EXPECTATION = 0.278
# 2500 tirages (~225k lignes de features, une ligne par numéro candidat 1-90)
# a fait planter l'inférence CPU (OOM, tentative d'allocation de 9,2 Go en un
# bloc dans l'attention du transformer). Fenêtre réduite à 300 tirages
# (~27k lignes) après ce premier échec réel, pas une estimation a priori.
RECENT_DRAWS_WINDOW = 300
HISTORY_START = 200          # comme train.py : il faut de l'historique avant de calculer freq_100


def load_draws(cols):
    conn = sqlite3.connect(DB_PATH)
    query = f"""
        SELECT date, game, {', '.join(cols)}
        FROM draws
        WHERE {cols[0]} IS NOT NULL
        ORDER BY date ASC, id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def build_features(df, cols):
    """Reprend exactement la logique de train.py::build_features, généralisée
    à n'importe quelle paire de colonnes (winning_* ou machine_*)."""
    draws_matrix = df[cols].values.astype(int)
    num_draws = len(df)

    presence = np.zeros((num_draws, 91), dtype=int)
    for t in range(num_draws):
        presence[t, draws_matrix[t]] = 1

    cum_freq = np.cumsum(presence, axis=0)

    last_seen = np.zeros((num_draws, 91), dtype=int)
    current_last_seen = np.zeros(91, dtype=int)
    for t in range(num_draws):
        last_seen[t] = current_last_seen.copy()
        for num in draws_matrix[t]:
            current_last_seen[num] = t

    X_list, y_list, meta_list = [], [], []
    for t in range(HISTORY_START, num_draws):
        y_draw = presence[t]
        for num in range(1, 91):
            f10 = np.sum(presence[t - 10:t, num])
            f50 = np.sum(presence[t - 50:t, num])
            f100 = np.sum(presence[t - 100:t, num])
            last_t = last_seen[t, num]
            delay = t - last_t if last_t > 0 else t
            glob_f = cum_freq[t - 1, num] / t
            X_list.append([num, f10, f50, f100, delay, glob_f])
            y_list.append(y_draw[num])
            meta_list.append((t, num))

    X_df = pd.DataFrame(X_list, columns=['number', 'freq_10', 'freq_50', 'freq_100', 'delay', 'global_freq'])
    y = np.array(y_list)
    meta_df = pd.DataFrame(meta_list, columns=['draw_idx', 'number'])
    return X_df, y, meta_df


def evaluate_top5(y_true, y_prob, meta_df, label):
    eval_df = meta_df.copy()
    eval_df['y_true'] = y_true
    eval_df['y_prob'] = y_prob

    correct_guesses = []
    for _, group in eval_df.groupby('draw_idx'):
        actual = set(group[group['y_true'] == 1]['number'].values)
        predicted = set(group.sort_values('y_prob', ascending=False).head(5)['number'].values)
        correct_guesses.append(len(actual & predicted))

    avg_correct = float(np.mean(correct_guesses))
    improvement = (avg_correct - RANDOM_EXPECTATION) / RANDOM_EXPECTATION * 100
    print(f"Modèle: {label}")
    print(f"  Moyenne de numéros devinés par tirage : {avg_correct:.4f} (Aléatoire théorique : {RANDOM_EXPECTATION:.3f})")
    print(f"  Amélioration par rapport à l'aléatoire : {improvement:+.2f}%")
    cg = np.array(correct_guesses)
    for min_correct in [1, 2, 3]:
        pct = np.mean(cg >= min_correct) * 100
        print(f"  Taux de tirages avec au moins {min_correct} bon(s) numéro(s) : {pct:.2f}%")
    return avg_correct


def run_pipeline(cols, label):
    print(f"\n{'=' * 70}\nPIPELINE : {label}\n{'=' * 70}")
    df_full = load_draws(cols)
    print(f"{len(df_full)} tirages avec {label.lower()} renseignés au total.")

    # Fenêtre récente pour rester tractable sur CPU (cf. docstring).
    df = df_full.tail(RECENT_DRAWS_WINDOW + HISTORY_START).reset_index(drop=True)
    print(f"Fenêtre utilisée pour TabICLv2 : {len(df)} tirages les plus récents.")

    X, y, meta = build_features(df, cols)

    unique_draws = meta['draw_idx'].unique()
    split_idx = int(len(unique_draws) * 0.8)
    train_idx, test_idx = unique_draws[:split_idx], unique_draws[split_idx:]

    train_mask = meta['draw_idx'].isin(train_idx)
    test_mask = meta['draw_idx'].isin(test_idx)

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    meta_test = meta[test_mask]

    print(f"Contexte (train) : {len(X_train)} lignes / {len(train_idx)} tirages")
    print(f"Test : {len(X_test)} lignes / {len(test_idx)} tirages")

    print("\nChargement / téléchargement du checkpoint TabICLv2 et inférence (CPU)...")
    t0 = time.time()
    # n_estimators/batch_size réduits par rapport aux défauts (8/8) pour
    # limiter le pic mémoire de l'attention sur CPU, après l'OOM initial.
    clf = TabICLClassifier(device="cpu", n_jobs=os.cpu_count(), n_estimators=4, batch_size=2)
    clf.fit(X_train, y_train)
    probs = clf.predict_proba(X_test)[:, 1]
    duration = time.time() - t0
    print(f"Terminé en {duration:.1f}s.")

    return evaluate_top5(y_test, probs, meta_test, f"TabICLv2 — {label}")


def main():
    winning_score = run_pipeline(['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5'], "Gagnants")
    machine_score = run_pipeline(['machine_1', 'machine_2', 'machine_3', 'machine_4', 'machine_5'], "Machine")

    print(f"\n{'=' * 70}\nRÉCAPITULATIF TabICLv2\n{'=' * 70}")
    print(f"Gagnants <- historique Gagnants : {winning_score:.4f} (théorique aléatoire : {RANDOM_EXPECTATION:.3f})")
    print(f"Machine  <- historique Machine  : {machine_score:.4f} (théorique aléatoire : {RANDOM_EXPECTATION:.3f})")


if __name__ == '__main__':
    main()
