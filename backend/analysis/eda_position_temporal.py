"""Contre-audit méthodologique après un point aveugle identifié : winning_1..5
n'est PAS un ensemble trié mais l'ORDRE RÉEL de sortie des boules (seulement
0.92% des tirages sont naturellement croissants). Le site propose d'ailleurs
des paris par position (PN = Premier Numéro, 1N..5N). Traiter les 5 numéros
comme un sac non-ordonné (ce qu'a fait toute l'analyse précédente, sauf le
test PN initial de eda.py) peut masquer un biais spécifique à une position.

Deux angles ajoutés, tous deux avec correction de Bonferroni :
1. Uniformité PAR POSITION (1 à 5) ET PAR JEU — pas seulement globalement.
2. Dérive TEMPORELLE : le biais est-il stable sur 2023-2026, ou concentré
   récemment (usure mécanique progressive, changement d'équipement...) ?
   Zoom spécifique sur "Digital 21h", seul jeu resté biaisé après correction
   dans eda_advanced.py — et fait notable, un jeu "Digital" (probablement
   RNG logiciel), pas une machine à boules physique.
"""
import sqlite3
import pandas as pd
import numpy as np
import scipy.stats as stats
import os

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))


def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT date, game, winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws WHERE is_valid = 1 ORDER BY date ASC, id ASC
    """, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values('date').reset_index(drop=True)


def chi2_uniformity(series):
    counts = series.value_counts().reindex(range(1, 91), fill_value=0)
    expected = len(series) / 90.0
    chi2_stat, p_val = stats.chisquare(counts, f_exp=expected)
    return chi2_stat, p_val, counts, expected


def uniformity_by_position_global(df):
    print("\n=== 9. UNIFORMITÉ PAR POSITION DE TIRAGE (toutes machines confondues) ===")
    results = []
    for pos in range(1, 6):
        col = f'winning_{pos}'
        chi2_stat, p_val, counts, expected = chi2_uniformity(df[col])
        results.append({'position': pos, 'chi2': chi2_stat, 'p_value': p_val,
                         'num_max': counts.idxmax(), 'freq_max': counts.max(),
                         'num_min': counts.idxmin(), 'freq_min': counts.min()})
    res_df = pd.DataFrame(results)
    print(res_df.to_string(index=False))
    alpha = 0.05 / 5
    sig = res_df[res_df['p_value'] < alpha]
    print(f"\nSignificatif après Bonferroni (p < {alpha:.4f}) sur les 5 positions : {len(sig)}/5")
    if len(sig):
        print(sig.to_string(index=False))
    return res_df


def uniformity_by_position_and_game(df, min_draws=100):
    print(f"\n=== 10. UNIFORMITÉ PAR POSITION *ET* PAR JEU (>= {min_draws} tirages) ===")
    results = []
    for game, group in df.groupby('game'):
        if len(group) < min_draws:
            continue
        for pos in range(1, 6):
            col = f'winning_{pos}'
            chi2_stat, p_val, counts, expected = chi2_uniformity(group[col])
            results.append({'game': game, 'position': pos, 'n_draws': len(group),
                             'chi2': chi2_stat, 'p_value': p_val,
                             'num_max': counts.idxmax(), 'freq_max': counts.max()})
    res_df = pd.DataFrame(results).sort_values('p_value')
    n_tests = len(res_df)
    alpha = 0.05 / n_tests
    n_sig_raw = (res_df['p_value'] < 0.05).sum()
    n_sig_corrected = (res_df['p_value'] < alpha).sum()

    print(f"{n_tests} tests (jeu x position). Seuil corrigé : p < {alpha:.6f}")
    print(f"Significatifs sans correction : {n_sig_raw}/{n_tests} ({n_sig_raw/n_tests*100:.1f}%, attendu ~5% par hasard)")
    print(f"Significatifs APRÈS correction de Bonferroni : {n_sig_corrected}/{n_tests}")
    print("\nTop 10 combinaisons jeu x position les plus significatives :")
    print(res_df.head(10).to_string(index=False))

    if n_sig_corrected > 0:
        print("\n-> Combinaisons qui SURVIVENT à la correction :")
        print(res_df[res_df['p_value'] < alpha].to_string(index=False))
    else:
        print("\n-> Aucune combinaison jeu x position ne survit à la correction : "
              "pas de biais positionnel caché derrière l'agrégation.")
    return res_df


def temporal_drift(df, game_filter=None, freq='QE'):
    label = game_filter if game_filter else "TOUS JEUX CONFONDUS"
    print(f"\n=== 11. DÉRIVE TEMPORELLE DU BIAIS — {label} (fenêtres trimestrielles) ===")

    sub = df[df['game'] == game_filter] if game_filter else df
    sub = sub.set_index('date')

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    results = []
    for period, group in sub.groupby(pd.Grouper(freq=freq)):
        if len(group) < 30:
            continue
        all_numbers = group[winning_cols].values.flatten()
        counts = pd.Series(all_numbers).value_counts().reindex(range(1, 91), fill_value=0)
        expected = len(all_numbers) / 90.0
        chi2_stat, p_val = stats.chisquare(counts, f_exp=expected)
        results.append({
            'periode': f"{period.year}-Q{period.quarter}",
            'n_tirages': len(group), 'chi2': chi2_stat, 'p_value': p_val,
            'num_max': counts.idxmax(), 'freq_max': counts.max(),
        })

    if not results:
        print("Pas assez de données pour une analyse temporelle sur ce périmètre.")
        return None

    res_df = pd.DataFrame(results)
    print(res_df.to_string(index=False))

    n_periods = len(res_df)
    alpha = 0.05 / n_periods if n_periods else 0.05
    trend_recent = res_df.tail(3)
    print(f"\nSignificatif après correction (p < {alpha:.4f}) : {(res_df['p_value'] < alpha).sum()}/{n_periods} période(s)")
    print(f"3 dernières périodes : {trend_recent[['periode', 'p_value']].to_string(index=False)}")

    # Corrélation simple : le chi2 augmente-t-il avec le temps (dérive) ?
    if n_periods >= 4:
        x = np.arange(n_periods)
        slope, intercept, r, p, se = stats.linregress(x, res_df['chi2'])
        print(f"Tendance du chi² dans le temps : pente={slope:+.2f}/période, r={r:.3f}, p={p:.4f}")
        if p < 0.05 and slope > 0:
            print("-> Le biais AUGMENTE significativement avec le temps (dérive détectée).")
        elif p < 0.05 and slope < 0:
            print("-> Le biais DIMINUE significativement avec le temps.")
        else:
            print("-> Pas de tendance temporelle significative — le niveau de biais est stable.")

    return res_df


def main():
    print("=== CONTRE-AUDIT : POSITION DE TIRAGE + DÉRIVE TEMPORELLE ===")
    df = load_data()
    print(f"{len(df)} tirages, {df['date'].min().date()} au {df['date'].max().date()}, {df['game'].nunique()} jeux.")

    uniformity_by_position_global(df)
    uniformity_by_position_and_game(df)
    temporal_drift(df, game_filter=None)
    temporal_drift(df, game_filter='Digital 21h')

    print("\n=== FIN DU CONTRE-AUDIT ===")


if __name__ == '__main__':
    main()
