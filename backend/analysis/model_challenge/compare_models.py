"""Challenge du modèle en production (freq_top5_v1) par des approches plus
riches, sur les jeux Digital (groupe 'signal' du suivi prospectif) :

  - freq_top5      : baseline actuellement en production (fréquence brute cumulée)
  - freq_decay     : fréquence pondérée par récence (decay exponentiel, half-life=100 tirages)
  - markov1        : chaîne de Markov d'ordre 1 sur les transitions numéro->numéro
                      entre tirages consécutifs du même jeu
  - ml_logreg      : régression logistique par numéro sur features engineered
                      (fréquence cumulée, fréquence glissante 20/50, écart courant,
                      écart moyen historique, jour de semaine), réentraînée tous les
                      50 tirages, fenêtre expansive (jamais de fuite du futur)
  - random_control : référence empirique (tirage aléatoire de 5/90), pour vérifier
                      que la méthode elle-même ne "détecte" pas un edge par artefact

Validation : walk-forward strict (à l'instant t, un modèle n'utilise que les
tirages 0..t-1 pour prédire le tirage t). Comparaison inter-modèles par test de
Wilcoxon signé (apparié, même tirages) contre la baseline freq_top5, et p-value
de permutation contre l'hypothèse H0 = tirages purement aléatoires (comme dans
prospective_tracker.py, pour rester cohérent avec le juge final prospectif).
"""
import sqlite3
import os
import sys
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression

ANALYSIS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)
from game_config import DIGITAL_GAMES, CONTROL_GAMES

WINNING_COLS = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']

MIN_HISTORY = 30
TOP_K = 5
DECAY_HALFLIFE = 100  # choisi a priori (pas optimisé sur le test -> pas de p-hacking)
DECAY = 0.5 ** (1.0 / DECAY_HALFLIFE)
ML_RETRAIN_EVERY = 50
RNG_SEED = 42


def load_game(conn, game):
    df = pd.read_sql_query(
        f"SELECT date, {', '.join(WINNING_COLS)} FROM draws WHERE game = ? ORDER BY date ASC, id ASC",
        conn, params=(game,)
    )
    df['date'] = pd.to_datetime(df['date'])
    return df


def build_presence(df):
    n = len(df)
    draws_matrix = df[WINNING_COLS].values.astype(int)
    presence = np.zeros((n, 91), dtype=np.float64)
    for t in range(n):
        presence[t, draws_matrix[t]] = 1.0
    return draws_matrix, presence


def topk_from_scores(scores, k=TOP_K):
    # scores: array indexé 1..90 (index 0 ignoré). Tie-break déterministe par numéro croissant.
    idx = np.arange(91)
    order = np.lexsort((idx, -scores))  # trie par -score puis par index croissant en cas d'égalité
    order = [i for i in order if i >= 1]
    return order[:k]


def run_freq_top5(draws_matrix, presence):
    n = len(draws_matrix)
    preds = [None] * n
    cum_counts = np.zeros(91)
    for t in range(n):
        if t >= MIN_HISTORY:
            preds[t] = topk_from_scores(cum_counts)
        cum_counts += presence[t]
    return preds


def run_freq_decay(draws_matrix, presence):
    n = len(draws_matrix)
    preds = [None] * n
    weighted = np.zeros(91)
    for t in range(n):
        if t >= MIN_HISTORY:
            preds[t] = topk_from_scores(weighted)
        weighted = weighted * DECAY + presence[t]
    return preds


def run_markov1(draws_matrix, presence):
    n = len(draws_matrix)
    preds = [None] * n
    # transition_count[a, b] = nb de fois où b est apparu au tirage suivant d'un tirage contenant a
    transition_count = np.zeros((91, 91))
    source_count = np.zeros(91)  # nb de fois où a est apparu comme numéro "source" (donc a un tirage suivant observé)

    for t in range(n):
        if t >= MIN_HISTORY and t >= 1:
            prev_numbers = draws_matrix[t - 1]
            with np.errstate(divide='ignore', invalid='ignore'):
                probs = np.where(source_count > 0, transition_count[prev_numbers].sum(axis=0) / np.maximum(source_count[prev_numbers].sum(), 1), 0.0)
            preds[t] = topk_from_scores(probs)

        # mettre à jour la matrice de transition avec le passage draw[t-1] -> draw[t]
        if t >= 1:
            prev_numbers = draws_matrix[t - 1]
            cur_numbers = draws_matrix[t]
            for a in prev_numbers:
                source_count[a] += 1
                transition_count[a, cur_numbers] += 1
    return preds


def build_ml_features(draws_matrix, presence, dates):
    n = len(draws_matrix)
    cum_count = np.zeros(91)
    last_seen = np.full(91, -1)
    gaps_sum = np.zeros(91)
    gaps_n = np.zeros(91)
    roll20 = np.zeros((n, 91))
    roll50 = np.zeros((n, 91))
    cumfreq = np.zeros((n, 91))
    gap_now = np.zeros((n, 91))
    gap_avg_hist = np.zeros((n, 91))
    dow = dates.dt.dayofweek.values

    for t in range(n):
        cumfreq[t] = cum_count / max(t, 1)
        gap_now[t] = np.where(last_seen >= 0, t - last_seen, t)
        gap_avg_hist[t] = np.where(gaps_n > 0, gaps_sum / np.maximum(gaps_n, 1), 18.0)
        lo20 = max(0, t - 20)
        lo50 = max(0, t - 50)
        roll20[t] = presence[lo20:t].sum(axis=0) if t > lo20 else 0
        roll50[t] = presence[lo50:t].sum(axis=0) if t > lo50 else 0

        cur = draws_matrix[t]
        for num in cur:
            if last_seen[num] >= 0:
                gaps_sum[num] += t - last_seen[num]
                gaps_n[num] += 1
            last_seen[num] = t
        cum_count += presence[t]

    return {
        'cumfreq': cumfreq, 'roll20': roll20, 'roll50': roll50,
        'gap_now': gap_now, 'gap_avg_hist': gap_avg_hist, 'dow': dow,
    }


def run_ml_logreg(draws_matrix, presence, dates):
    n = len(draws_matrix)
    preds = [None] * n
    if n <= MIN_HISTORY:
        return preds

    feats = build_ml_features(draws_matrix, presence, dates)
    nums = np.arange(1, 91)

    def make_X(t):
        X = np.column_stack([
            feats['cumfreq'][t, 1:], feats['roll20'][t, 1:], feats['roll50'][t, 1:],
            feats['gap_now'][t, 1:], feats['gap_avg_hist'][t, 1:],
            np.full(90, np.sin(2 * np.pi * feats['dow'][t] / 7)),
            np.full(90, np.cos(2 * np.pi * feats['dow'][t] / 7)),
        ])
        return X

    model = None
    for t in range(n):
        if t < MIN_HISTORY:
            continue
        if model is None or (t - MIN_HISTORY) % ML_RETRAIN_EVERY == 0:
            # entraîner sur tout l'historique 0..t-1 (fenêtre expansive, walk-forward strict)
            X_train = np.vstack([make_X(i) for i in range(MIN_HISTORY // 2, t)])
            y_train = np.concatenate([presence[i, 1:] for i in range(MIN_HISTORY // 2, t)])
            if len(np.unique(y_train)) < 2:
                model = None
            else:
                model = LogisticRegression(max_iter=200, class_weight='balanced', C=0.5)
                model.fit(X_train, y_train)

        if model is not None:
            X_t = make_X(t)
            proba = model.predict_proba(X_t)[:, 1] if len(model.classes_) > 1 else np.zeros(90)
            scores = np.zeros(91)
            scores[1:] = proba
            preds[t] = topk_from_scores(scores)
        else:
            preds[t] = topk_from_scores(feats['cumfreq'][t])
    return preds


def run_random_control(draws_matrix, presence, seed_offset=0):
    n = len(draws_matrix)
    rng = np.random.default_rng(RNG_SEED + seed_offset)
    preds = [None] * n
    for t in range(n):
        if t >= MIN_HISTORY:
            preds[t] = sorted((rng.choice(90, size=TOP_K, replace=False) + 1).tolist())
    return preds


def score_predictions(draws_matrix, preds):
    n_correct = []
    for t, p in enumerate(preds):
        if p is None:
            continue
        actual = set(draws_matrix[t].tolist())
        n_correct.append(len(actual & set(p)))
    return np.array(n_correct)


def permutation_pvalue(n_trials, observed_correct, n_perm=5000, seed=42):
    rng = np.random.default_rng(seed)
    # Sous H0, l'intersection entre un ensemble prédit fixe de 5 numéros et un
    # tirage de 5 parmi 90 sans remise suit une loi Hypergéométrique(N=90, K=5, n=5)
    # — PAS une Binomiale(5, 5/90), qui surestimerait légèrement la variance
    # (tirage sans remise). On simule la somme sur n_trials tirages indépendants.
    null_sums = stats.hypergeom.rvs(M=90, n=5, N=5, size=(n_perm, n_trials), random_state=rng).sum(axis=1)
    return (null_sums >= observed_correct).mean()


def main():
    conn = sqlite3.connect(DB_PATH)
    all_results = []
    per_model_correct = {m: [] for m in ['freq_top5', 'freq_decay', 'markov1', 'ml_logreg', 'random_control']}

    for game in DIGITAL_GAMES:
        df = load_game(conn, game)
        n = len(df)
        print(f"\n### Jeu {game} : {n} tirages ###")
        if n < MIN_HISTORY + 10:
            print("  -> Pas assez de tirages pour un walk-forward significatif, jeu ignoré.")
            continue

        draws_matrix, presence = build_presence(df)
        dates = df['date']

        preds_freq = run_freq_top5(draws_matrix, presence)
        preds_decay = run_freq_decay(draws_matrix, presence)
        preds_markov = run_markov1(draws_matrix, presence)
        preds_ml = run_ml_logreg(draws_matrix, presence, dates)
        preds_rand = run_random_control(draws_matrix, presence, seed_offset=hash(game) % 1000)

        for name, preds in [('freq_top5', preds_freq), ('freq_decay', preds_decay),
                             ('markov1', preds_markov), ('ml_logreg', preds_ml),
                             ('random_control', preds_rand)]:
            correct = score_predictions(draws_matrix, preds)
            per_model_correct[name].append(correct)
            mean_c = correct.mean()
            improvement = (mean_c - 5 * 5 / 90) / (5 * 5 / 90) * 100
            print(f"  {name:16s} n={len(correct):4d}  moyenne_correct={mean_c:.4f}  amélioration_vs_hasard={improvement:+6.2f}%")
            all_results.append({'game': game, 'model': name, 'n': len(correct), 'mean_correct': mean_c,
                                 'improvement_pct': improvement, 'sum_correct': int(correct.sum())})

    conn.close()

    res_df = pd.DataFrame(all_results)
    res_df.to_csv(os.path.join(OUT_DIR, 'model_comparison_per_game.csv'), index=False)

    print("\n" + "=" * 90)
    print("=== COMPARAISON AGRÉGÉE — TOUS JEUX DIGITAL POOLÉS (walk-forward, prédictions non vues) ===")
    print("=" * 90)

    theoretical = 5 * 5 / 90.0
    summary = []
    baseline_pooled = np.concatenate(per_model_correct['freq_top5'])

    for name, arrs in per_model_correct.items():
        pooled = np.concatenate(arrs)
        n_trials = len(pooled)
        observed_sum = int(pooled.sum())
        mean_c = pooled.mean()
        improvement = (mean_c - theoretical) / theoretical * 100
        p_val_random = permutation_pvalue(n_trials, observed_sum)

        if name != 'freq_top5' and len(pooled) == len(baseline_pooled):
            try:
                w_stat, w_p = stats.wilcoxon(pooled, baseline_pooled)
            except ValueError:
                w_stat, w_p = np.nan, np.nan
        else:
            w_stat, w_p = np.nan, np.nan

        summary.append({
            'model': name, 'n_predictions': n_trials, 'mean_correct': mean_c,
            'theoretical_random': theoretical, 'improvement_pct': improvement,
            'p_value_vs_random_H0': p_val_random,
            'wilcoxon_p_vs_freq_top5': w_p,
        })
        print(f"\n--- {name} ---")
        print(f"  Prédictions évaluées : {n_trials}")
        print(f"  Moyenne bons numéros : {mean_c:.4f} (théorique aléatoire : {theoretical:.4f})")
        print(f"  Amélioration vs hasard : {improvement:+.2f}%")
        print(f"  p-value H0=hasard pur (permutation, unilatéral, {n_trials} tirages) : {p_val_random:.4f}")
        if name != 'freq_top5':
            print(f"  Wilcoxon signé apparié vs freq_top5 (H0 = pas de différence) : p = {w_p:.4f}" if not np.isnan(w_p) else "  Wilcoxon: n/a")

    summary_df = pd.DataFrame(summary)
    n_models_tested = len(summary_df) - 1  # -1 car random_control n'est pas un "candidat" à comparer à la correction
    alpha_corrected = 0.05 / max(n_models_tested, 1)
    print(f"\nCorrection multi-modèles (Bonferroni, {n_models_tested} modèles candidats testés contre H0 hasard) : "
          f"seuil ajusté p < {alpha_corrected:.4f}")
    summary_df['significatif_apres_correction'] = summary_df['p_value_vs_random_H0'] < alpha_corrected
    print(summary_df.to_string(index=False))
    summary_df.to_csv(os.path.join(OUT_DIR, 'model_comparison_summary.csv'), index=False)

    print("\n=== CONCLUSION ===")
    winners = summary_df[(summary_df['model'] != 'random_control') & (summary_df['p_value_vs_random_H0'] < alpha_corrected) & (summary_df['improvement_pct'] > 0)]
    if len(winners) == 0:
        print("Aucun modèle candidat ne bat significativement le hasard après correction multi-tests.")
        best_row = summary_df[summary_df['model'] != 'random_control'].sort_values('mean_correct', ascending=False).iloc[0]
        print(f"Meilleur candidat en pratique (non significatif) : {best_row['model']} "
              f"(moyenne {best_row['mean_correct']:.4f} vs {theoretical:.4f} théorique, p={best_row['p_value_vs_random_H0']:.4f}).")
    else:
        print("Modèle(s) qui battent significativement le hasard après correction :")
        print(winners.to_string(index=False))


if __name__ == '__main__':
    main()
