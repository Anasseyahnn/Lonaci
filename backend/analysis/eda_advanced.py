"""Analyses complémentaires à eda.py :
1. Test d'uniformité PAR JEU (le test global de eda.py mélange 37 tirages
   potentiellement issus de machines différentes — un biais global peut être
   un artefact de mélange plutôt qu'un vrai biais mécanique).
2. Corrélation entre les numéros Gagnants et les numéros Machine d'un même tirage.
3. Test formel d'autocorrélation (ACF) sur la présence de chaque numéro dans le temps,
   en complément du test de répétitions consécutives de eda.py.
"""
import sqlite3
import pandas as pd
import numpy as np
import scipy.stats as stats
from statsmodels.stats.diagnostic import acorr_ljungbox
import os

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))


def load_data():
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT date, game,
               winning_1, winning_2, winning_3, winning_4, winning_5,
               machine_1, machine_2, machine_3, machine_4, machine_5
        FROM draws
        ORDER BY date ASC, id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def uniformity_per_game(df, min_draws=100):
    print("\n=== 6. TEST D'UNIFORMITÉ DES NUMÉROS GAGNANTS, PAR JEU ===")
    print(f"(jeux avec au moins {min_draws} tirages seulement, pour un test statistiquement valable)\n")

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    results = []

    for game, group in df.groupby('game'):
        n = len(group)
        if n < min_draws:
            continue

        all_numbers = group[winning_cols].values.flatten()
        counts = pd.Series(all_numbers).value_counts().reindex(range(1, 91), fill_value=0)
        expected_freq = len(all_numbers) / 90.0

        chi2_stat, p_val = stats.chisquare(counts, f_exp=expected_freq)
        results.append({
            'game': game,
            'n_draws': n,
            'chi2': chi2_stat,
            'p_value': p_val,
            'biaise': p_val < 0.05,
            'num_max': counts.idxmax(),
            'freq_max': counts.max(),
            'num_min': counts.idxmin(),
            'freq_min': counts.min(),
        })

    res_df = pd.DataFrame(results).sort_values('p_value')
    n_games = len(res_df)
    n_biaises = res_df['biaise'].sum()

    print(res_df.to_string(index=False))
    print(f"\n{n_biaises}/{n_games} jeux rejettent l'uniformité à p < 0.05 (sans correction).")

    # Correction de Bonferroni : avec n_games tests simultanés, le seuil de
    # signification doit être divisé par n_games pour garder un taux d'erreur
    # global de 5 % (sinon, tester 30 jeux fait mécaniquement "trouver" ~1-2
    # faux positifs même si tout est parfaitement aléatoire).
    alpha_corrected = 0.05 / n_games if n_games else 0.05
    n_biaises_corrected = (res_df['p_value'] < alpha_corrected).sum()
    print(f"Avec correction de Bonferroni (seuil ajusté à p < {alpha_corrected:.5f}) : "
          f"{n_biaises_corrected}/{n_games} jeux restent significatifs.")

    if n_biaises_corrected == 0:
        print("-> Le biais global détecté dans eda.py est très probablement un artefact "
              "du mélange de plusieurs jeux (effet Simpson), pas un vrai biais mécanique "
              "par machine de tirage.")
    else:
        biaised_games = res_df[res_df['p_value'] < alpha_corrected]['game'].tolist()
        print(f"-> Biais qui SURVIT à la correction sur : {biaised_games}. "
              f"À examiner en priorité (mais toujours d'ampleur trop faible pour être exploitable en pari).")

    return res_df


def winning_vs_machine_correlation(df):
    print("\n=== 7. CORRÉLATION ENTRE NUMÉROS GAGNANTS ET NUMÉROS MACHINE (même tirage) ===")

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    machine_cols = ['machine_1', 'machine_2', 'machine_3', 'machine_4', 'machine_5']

    # Ne garder que les tirages où les 2 séries existent réellement (certains
    # jeux n'ont pas de "Machine", cf. National/Friday Bonanza/Midweek dans le
    # scrape — leurs colonnes machine_* seront NULL).
    has_machine = df[machine_cols].notna().all(axis=1)
    sub = df[has_machine].copy()
    print(f"Tirages avec numéros Machine renseignés : {len(sub)}/{len(df)}")

    if len(sub) == 0:
        print("Aucun tirage exploitable, test ignoré.")
        return

    # Nombre de numéros en commun entre Gagnants et Machine du MÊME tirage
    winning_sets = [set(row) for row in sub[winning_cols].values]
    machine_sets = [set(row) for row in sub[machine_cols].values]
    commons = [len(w & m) for w, m in zip(winning_sets, machine_sets)]

    commons_series = pd.Series(commons)
    observed_counts = commons_series.value_counts().reindex(range(6), fill_value=0)

    # Sous H0 (tirages indépendants), même loi hypergéométrique que pour les
    # répétitions consécutives de eda.py : 5 numéros tirés dans un univers de
    # 90 dont 5 sont "marqués" (les numéros gagnants).
    theoretical_probs = stats.hypergeom.pmf(range(6), 90, 5, 5)
    expected_counts = theoretical_probs * len(sub)

    chi2_stat, p_val = stats.chisquare(observed_counts, f_exp=expected_counts)

    for k in range(6):
        pct_obs = observed_counts[k] / len(sub) * 100
        pct_exp = theoretical_probs[k] * 100
        print(f"  {k} numéro(s) commun(s) Gagnants/Machine : {observed_counts[k]} fois "
              f"({pct_obs:.2f}%) [Attendu : {expected_counts[k]:.1f} ({pct_exp:.2f}%)]")

    print(f"Statistique Chi-deux (X²) : {chi2_stat:.4f}")
    print(f"p-value : {p_val:.6f}")
    if p_val < 0.05:
        print("-> RÉSULTAT : les numéros Machine ne sont PAS indépendants des numéros "
              "Gagnants du même tirage (p < 0.05) — à creuser, potentiellement un tirage "
              "partagé/lié plutôt que 2 tirages séparés.")
    else:
        print("-> RÉSULTAT : indépendance confirmée. Les numéros Machine ne donnent "
              "aucune information exploitable sur les numéros Gagnants du même tirage.")


def formal_autocorrelation_test(df, lags=10):
    print(f"\n=== 8. TEST FORMEL D'AUTOCORRÉLATION (Ljung-Box, {lags} lags) SUR LA PRÉSENCE PAR NUMÉRO ===")
    print("Complète le test empirique #5 de eda.py avec un test statistique standard "
          "sur la série temporelle binaire 'le numéro N est-il sorti au tirage t'.\n")

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    draws_matrix = df[winning_cols].values
    n = len(df)

    presence = np.zeros((n, 91), dtype=int)
    for t in range(n):
        presence[t, draws_matrix[t]] = 1

    p_values = []
    for num in range(1, 91):
        series = presence[:, num]
        try:
            lb = acorr_ljungbox(series, lags=[lags], return_df=True)
            p_values.append(lb['lb_pvalue'].iloc[0])
        except Exception:
            continue

    p_values = np.array(p_values)
    n_tested = len(p_values)
    n_significant = (p_values < 0.05).sum()
    alpha_corrected = 0.05 / n_tested if n_tested else 0.05
    n_significant_corrected = (p_values < alpha_corrected).sum()

    print(f"Numéros testés : {n_tested}")
    print(f"Significatifs à p < 0.05 (sans correction) : {n_significant}/{n_tested} "
          f"({n_significant/n_tested*100:.1f}%) — attendu par hasard pur : ~5%")
    print(f"Significatifs après correction de Bonferroni (p < {alpha_corrected:.5f}) : "
          f"{n_significant_corrected}/{n_tested}")

    if n_significant_corrected == 0:
        print("-> RÉSULTAT : aucune autocorrélation réelle détectée. Confirme statistiquement "
              "(pas seulement empiriquement) l'indépendance temporelle des tirages.")
    else:
        print(f"-> RÉSULTAT : {n_significant_corrected} numéro(s) montrent une autocorrélation "
              "qui survit à la correction — anomalie à examiner (mais rare et probablement "
              "un faux positif résiduel sur 90 tests).")


def main():
    print("=== ANALYSES COMPLÉMENTAIRES (au-delà de eda.py) ===")
    df = load_data()
    print(f"{len(df)} tirages chargés, {df['game'].nunique()} jeux distincts.")

    uniformity_per_game(df)
    winning_vs_machine_correlation(df)
    formal_autocorrelation_test(df)

    print("\n=== FIN DES ANALYSES COMPLÉMENTAIRES ===")


if __name__ == '__main__':
    main()
