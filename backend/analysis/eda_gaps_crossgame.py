"""Deux pistes non encore explorées, à la demande explicite d'un contre-audit :

1. ANALYSE DES ÉCARTS (Gaps) — prévue dans PLAN.md dès le départ, jamais faite.
   Pour chaque numéro 1-90, distribution du nombre de tirages entre deux
   apparitions successives. Sous H0 (tirages indépendants, p=5/90 par tirage),
   les écarts suivent une loi géométrique. Un numéro "cassé" (mécaniquement
   biaisé) aurait une distribution d'écarts significativement différente.

2. CORRÉLATION CROISÉE ENTRE JEUX "DIGITAL" DU MÊME JOUR — jamais testée.
   Digital Reveil 7h/8h, Digital 21h/22h/23h sont tirés le même jour et
   partagent probablement un même moteur RNG logiciel (vs machine à boules
   physique pour les autres jeux). S'ils partagent une graine ou un état
   interne, on verrait une corrélation anormale entre leurs numéros du même
   jour — chose qu'aucun test précédent (qui comparait Gagnants/Machine d'UN
   SEUL jeu) n'aurait pu détecter.
"""
import sqlite3
import pandas as pd
import numpy as np
import scipy.stats as stats
from itertools import combinations
import os
import sys

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

if ANALYSIS_DIR not in sys.path:
    sys.path.insert(0, ANALYSIS_DIR)
from game_config import DIGITAL_GAMES  # inclut désormais Afterwork, cf. game_config.py


def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT date, game, winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws ORDER BY date ASC, id ASC
    """, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def gap_analysis(df):
    print("\n=== 12. ANALYSE DES ÉCARTS (GAPS) PAR NUMÉRO ===")
    print("Sous H0, l'écart entre 2 apparitions d'un numéro suit une loi géométrique "
          "de paramètre p = 5/90 = 0.0556 (probabilité de sortie par tirage).\n")

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    draws_matrix = df[winning_cols].values
    n = len(df)
    p_theoretical = 5.0 / 90.0
    expected_mean_gap = 1.0 / p_theoretical  # espérance d'une loi géométrique

    presence = np.zeros((n, 91), dtype=int)
    for t in range(n):
        presence[t, draws_matrix[t]] = 1

    results = []
    all_gaps_by_number = {}
    for num in range(1, 91):
        appearances = np.where(presence[:, num] == 1)[0]
        if len(appearances) < 20:
            continue
        gaps = np.diff(appearances)
        all_gaps_by_number[num] = gaps

        observed_mean = gaps.mean()
        # Test de Kolmogorov-Smirnov contre la loi géométrique théorique
        ks_stat, ks_p = stats.kstest(gaps, 'geom', args=(p_theoretical,))

        results.append({
            'number': num, 'n_appearances': len(appearances),
            'mean_gap': observed_mean, 'expected_mean_gap': expected_mean_gap,
            'max_gap': gaps.max(), 'ks_stat': ks_stat, 'ks_pvalue': ks_p,
        })

    res_df = pd.DataFrame(results).sort_values('ks_pvalue')
    n_tests = len(res_df)
    alpha = 0.05 / n_tests
    n_sig_raw = (res_df['ks_pvalue'] < 0.05).sum()
    n_sig_corrected = (res_df['ks_pvalue'] < alpha).sum()

    print(f"Écart moyen théorique attendu : {expected_mean_gap:.2f} tirages")
    print(f"Écart moyen observé (moyenne sur les 90 numéros) : {res_df['mean_gap'].mean():.2f} tirages")
    print(f"\n{n_tests} numéros testés (KS contre loi géométrique). Seuil corrigé : p < {alpha:.6f}")
    print(f"Significatifs sans correction : {n_sig_raw}/{n_tests} ({n_sig_raw/n_tests*100:.1f}%, attendu ~5%)")
    print(f"Significatifs APRÈS correction de Bonferroni : {n_sig_corrected}/{n_tests}")
    print("\nTop 10 numéros les plus suspects (plus petite p-value) :")
    print(res_df.head(10).to_string(index=False))

    if n_sig_corrected > 0:
        print("\n-> Numéro(s) dont la distribution d'écarts diffère significativement de l'aléatoire :")
        print(res_df[res_df['ks_pvalue'] < alpha].to_string(index=False))
    else:
        print("\n-> Aucun numéro ne montre une distribution d'écarts anormale après correction. "
              "Pas de 'boule cassée' détectable par cette méthode.")

    # Numéro avec le plus long retard actuel (jamais sorti depuis le plus longtemps)
    current_delay = []
    for num in range(1, 91):
        appearances = np.where(presence[:, num] == 1)[0]
        if len(appearances) == 0:
            continue
        current_delay.append((num, n - 1 - appearances[-1]))
    current_delay.sort(key=lambda x: -x[1])
    print(f"\nNuméros en plus grand retard actuellement (n'ont pas été tirés depuis le plus longtemps) :")
    for num, delay in current_delay[:5]:
        print(f"  Numéro {num} : {delay} tirages sans sortir")

    return res_df


def cross_game_correlation(df):
    print("\n=== 13. CORRÉLATION CROISÉE ENTRE JEUX 'DIGITAL' DU MÊME JOUR ===")
    print(f"Jeux testés : {DIGITAL_GAMES}\n")

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    sub = df[df['game'].isin(DIGITAL_GAMES)]

    # Un set de numéros par (date, jeu)
    pivot = {}
    for _, row in sub.iterrows():
        key = (row['date'], row['game'])
        pivot[key] = set(row[winning_cols].values)

    theoretical_probs = stats.hypergeom.pmf(range(6), 90, 5, 5)

    all_results = []
    for g1, g2 in combinations(DIGITAL_GAMES, 2):
        commons = []
        dates_g1 = {d for (d, g) in pivot if g == g1}
        dates_g2 = {d for (d, g) in pivot if g == g2}
        shared_dates = dates_g1 & dates_g2

        for d in shared_dates:
            s1 = pivot[(d, g1)]
            s2 = pivot[(d, g2)]
            commons.append(len(s1 & s2))

        if len(commons) < 30:
            continue

        commons_series = pd.Series(commons)
        observed_counts = commons_series.value_counts().reindex(range(6), fill_value=0)
        expected_counts = theoretical_probs * len(commons)
        chi2_stat, p_val = stats.chisquare(observed_counts, f_exp=expected_counts)

        all_results.append({
            'jeu_1': g1, 'jeu_2': g2, 'n_jours_communs': len(commons),
            'moy_communs_observee': np.mean(commons), 'moy_communs_attendue': 5 * 5 / 90,
            'chi2': chi2_stat, 'p_value': p_val,
        })

    res_df = pd.DataFrame(all_results).sort_values('p_value')
    n_tests = len(res_df)
    alpha = 0.05 / n_tests if n_tests else 0.05

    print(res_df.to_string(index=False))
    n_sig_raw = (res_df['p_value'] < 0.05).sum()
    n_sig_corrected = (res_df['p_value'] < alpha).sum()
    print(f"\n{n_tests} paires de jeux Digital testées. Seuil corrigé : p < {alpha:.5f}")
    print(f"Significatif sans correction : {n_sig_raw}/{n_tests}")
    print(f"Significatif APRÈS correction : {n_sig_corrected}/{n_tests}")

    if n_sig_corrected > 0:
        print("\n-> CORRÉLATION ANORMALE détectée entre des jeux Digital du même jour :")
        print(res_df[res_df['p_value'] < alpha].to_string(index=False))
        print("Ça suggérerait un moteur RNG partagé ou une graine liée entre ces tirages.")
    else:
        print("\n-> Aucune corrélation anormale entre les jeux Digital du même jour. "
              "Chacun semble tiré indépendamment, même s'ils partagent probablement le même moteur logiciel.")

    return res_df


def main():
    print("=== PISTES SUPPLÉMENTAIRES : ÉCARTS + CORRÉLATION INTER-JEUX DIGITAL ===")
    df = load_data()
    print(f"{len(df)} tirages chargés.")

    gap_analysis(df)
    cross_game_correlation(df)

    print("\n=== FIN ===")


if __name__ == '__main__':
    main()
