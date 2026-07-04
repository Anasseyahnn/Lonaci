import sqlite3
import pandas as pd
import numpy as np
import scipy.stats as stats
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Paths setup
ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
PLOTS_DIR = os.path.join(ANALYSIS_DIR, 'plots')
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))

os.makedirs(PLOTS_DIR, exist_ok=True)
sns.set_theme(style="darkgrid")

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
    
    # Sort chronologically
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def analyze_uniformity_all_numbers(df):
    print("\n=== 1. TEST D'UNIFORMITÉ DES NUMÉROS GAGNANTS (1 à 90) ===")
    
    # Flatten all winning numbers (5 per draw)
    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    all_winning = df[winning_cols].values.flatten()
    
    # Calculate frequencies
    counts = pd.Series(all_winning).value_counts().reindex(range(1, 91), fill_value=0)
    
    # Chi-square Goodness-of-Fit Test
    total_draws = len(df)
    total_numbers_drawn = len(all_winning)
    expected_freq = total_numbers_drawn / 90.0 # Expected: total * (5/90) which is total_draws * 5 / 90
    
    chi2_stat, p_val = stats.chisquare(counts, f_exp=expected_freq)
    
    print(f"Nombre total de tirages analysés : {total_draws}")
    print(f"Nombre total de boules tirées : {total_numbers_drawn}")
    print(f"Fréquence théorique attendue par numéro : {expected_freq:.2f}")
    print(f"Numéro le plus fréquent : {counts.idxmax()} (tiré {counts.max()} fois)")
    print(f"Numéro le moins fréquent : {counts.idxmin()} (tiré {counts.min()} fois)")
    print(f"Statistique Chi-deux (X²) : {chi2_stat:.4f}")
    print(f"p-value : {p_val:.6f}")
    
    if p_val < 0.05:
        print("-> RÉSULTAT : REJET de l'hypothèse d'uniformité (p < 0.05). Il y a un biais statistique significatif !")
    else:
        print("-> RÉSULTAT : ACCEPTATION de l'hypothèse d'uniformité (p >= 0.05). La distribution des numéros est conforme à l'aléa théorique.")
        
    # Plot distribution
    plt.figure(figsize=(15, 6))
    colors = ['#10b981' if (val >= expected_freq) else '#ef4444' for val in counts]
    plt.bar(counts.index, counts.values, color=colors, alpha=0.85)
    plt.axhline(expected_freq, color='blue', linestyle='--', linewidth=2, label=f'Attendu théorique ({expected_freq:.1f})')
    plt.title("Distribution de fréquence des 90 numéros (Tirages Gagnants)", fontsize=14, fontweight='bold')
    plt.xlabel("Numéro", fontsize=12)
    plt.ylabel("Nombre d'apparitions", fontsize=12)
    plt.xlim(0.5, 90.5)
    plt.xticks(range(5, 91, 5))
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'winning_distribution.png'))
    plt.close()

def analyze_uniformity_first_number(df):
    print("\n=== 2. TEST D'UNIFORMITÉ DU PREMIER NUMÉRO TIRÉ (PN) ===")
    
    pn_numbers = df['winning_1']
    counts = pn_numbers.value_counts().reindex(range(1, 91), fill_value=0)
    
    total_draws = len(df)
    expected_freq = total_draws / 90.0
    
    chi2_stat, p_val = stats.chisquare(counts, f_exp=expected_freq)
    
    print(f"Fréquence théorique attendue par numéro en 1ère position : {expected_freq:.2f}")
    print(f"PN le plus fréquent : {counts.idxmax()} (tiré {counts.max()} fois)")
    print(f"PN le moins fréquent : {counts.idxmin()} (tiré {counts.min()} fois)")
    print(f"Statistique Chi-deux (X²) : {chi2_stat:.4f}")
    print(f"p-value : {p_val:.6f}")
    
    if p_val < 0.05:
        print("-> RÉSULTAT : REJET de l'hypothèse d'uniformité pour le PN (p < 0.05).")
    else:
        print("-> RÉSULTAT : ACCEPTATION de l'hypothèse d'uniformité pour le PN (p >= 0.05).")
        
    # Plot distribution
    plt.figure(figsize=(15, 6))
    plt.bar(counts.index, counts.values, color='#3b82f6', alpha=0.85)
    plt.axhline(expected_freq, color='red', linestyle='--', linewidth=2, label=f'Attendu théorique ({expected_freq:.1f})')
    plt.title("Distribution de fréquence du Premier Numéro Tiré (PN)", fontsize=14, fontweight='bold')
    plt.xlabel("Numéro", fontsize=12)
    plt.ylabel("Nombre d'apparitions en 1ère position", fontsize=12)
    plt.xlim(0.5, 90.5)
    plt.xticks(range(5, 91, 5))
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'pn_distribution.png'))
    plt.close()

def analyze_sums(df):
    print("\n=== 3. ANALYSE DE LA SOMME DES NUMÉROS GAGNANTS ===")
    
    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    sums = df[winning_cols].sum(axis=1)
    
    # Theoretical sum for 5 numbers from 1-90
    # Expected mean = 5 * 45.5 = 227.5
    # Variance of a single draw from 1 to 90 is (90^2 - 1)/12 = 674.9167
    # For a sample of 5 without replacement: Var(Sum) = 5 * Var_X * (1 - 5/90) = 5 * 674.9167 * (85/90) = 3187.05
    # Std Dev = sqrt(3187.05) approx 56.45
    
    observed_mean = sums.mean()
    observed_std = sums.std()
    
    print(f"Somme moyenne observée : {observed_mean:.2f} (Attendu théorique : 227.50)")
    print(f"Écart-type observé : {observed_std:.2f} (Attendu théorique : 56.45)")
    
    # Plot sum distribution
    plt.figure(figsize=(10, 6))
    sns.histplot(sums, kde=True, color='#8b5cf6', stat='density', bins=30)
    
    # Plot theoretical normal curve
    xmin, xmax = plt.xlim()
    x = np.linspace(xmin, xmax, 100)
    p = stats.norm.pdf(x, 227.5, 56.45)
    plt.plot(x, p, 'r--', linewidth=2, label='Distribution normale théorique')
    
    plt.title("Distribution de la Somme des 5 Numéros Gagnants", fontsize=14, fontweight='bold')
    plt.xlabel("Somme des numéros", fontsize=12)
    plt.ylabel("Densité de probabilité", fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'sums_distribution.png'))
    plt.close()

def analyze_even_odd(df):
    print("\n=== 4. ANALYSE DU RATIO PAIR / IMPAIR ===")
    
    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    # Modulo 2 to check if even (0 if even, 1 if odd)
    odds_count = (df[winning_cols] % 2).sum(axis=1)
    evens_count = 5 - odds_count
    
    # Theoretical probability (hypergeometric distribution: 45 even, 45 odd in 90 numbers)
    # P(k evens out of 5) = C(45, k) * C(45, 5-k) / C(90, 5)
    total_ways = stats.hypergeom.pmf(range(6), 90, 45, 5)
    expected_counts = total_ways * len(df)
    
    observed_counts = evens_count.value_counts().reindex(range(6), fill_value=0)
    
    chi2_stat, p_val = stats.chisquare(observed_counts, f_exp=expected_counts)
    
    print("Distribution observée du nombre de numéros PAIRS par tirage :")
    for k in range(6):
        print(f"  {k} pair(s), {5-k} impair(s) : {observed_counts[k]} fois ({observed_counts[k]/len(df)*100:.2f}%) [Attendu : {expected_counts[k]:.1f} ({total_ways[k]*100:.2f}%)]")
        
    print(f"Statistique Chi-deux (X²) : {chi2_stat:.4f}")
    print(f"p-value : {p_val:.6f}")
    
    if p_val < 0.05:
        print("-> RÉSULTAT : Anomalie significative dans le ratio Pair/Impair (p < 0.05).")
    else:
        print("-> RÉSULTAT : Ratio Pair/Impair conforme à la distribution théorique (p >= 0.05).")
        
    # Plot even/odd distribution
    plt.figure(figsize=(10, 6))
    x = np.arange(6)
    width = 0.35
    plt.bar(x - width/2, observed_counts.values, width, label='Observé', color='#ec4899')
    plt.bar(x + width/2, expected_counts, width, label='Théorique attendu', color='#9ca3af', alpha=0.7)
    plt.title("Distribution du nombre de numéros PAIRS par tirage", fontsize=14, fontweight='bold')
    plt.xlabel("Nombre de numéros pairs dans le tirage", fontsize=12)
    plt.ylabel("Nombre de tirages", fontsize=12)
    plt.xticks(x)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'even_odd_distribution.png'))
    plt.close()

def analyze_temporal_repeats(df):
    print("\n=== 5. ANALYSE DES RÉPÉTITIONS CONSÉCUTIVES (DÉPENDANCE TEMPORELLE) ===")
    
    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    draws_sets = [set(row) for row in df[winning_cols].values]
    
    repeats = []
    for i in range(1, len(draws_sets)):
        common = len(draws_sets[i].intersection(draws_sets[i-1]))
        repeats.append(common)
        
    repeats_series = pd.Series(repeats)
    observed_counts = repeats_series.value_counts().reindex(range(6), fill_value=0)
    
    # Theoretical probability of k common numbers between two independent draws of 5 from 90:
    # Hypergeometric PMF: choosing 5 winning numbers from a universe of 90, 
    # where the "successes in universe" are the 5 winning numbers of the previous draw.
    # hypergeom.pmf(k, 90, 5, 5)
    theoretical_probs = stats.hypergeom.pmf(range(6), 90, 5, 5)
    expected_counts = theoretical_probs * len(repeats)
    
    chi2_stat, p_val = stats.chisquare(observed_counts, f_exp=expected_counts)
    
    print("Distribution observée du nombre de numéros répétés d'un tirage à l'autre :")
    for k in range(6):
        print(f"  {k} numéro(s) commun(s) : {observed_counts[k]} fois ({observed_counts[k]/len(repeats)*100:.2f}%) [Attendu : {expected_counts[k]:.1f} ({theoretical_probs[k]*100:.2f}%)]")
        
    print(f"Statistique Chi-deux (X²) : {chi2_stat:.4f}")
    print(f"p-value : {p_val:.6f}")
    
    if p_val < 0.05:
        print("-> RÉSULTAT : Dépendance temporelle suspecte ! Le nombre de répétitions ne suit pas l'aléa (p < 0.05).")
    else:
        print("-> RÉSULTAT : Indépendance temporelle confirmée. Le taux de répétition est normal (p >= 0.05).")
        
    # Plot temporal repeats
    plt.figure(figsize=(10, 6))
    x = np.arange(6)
    width = 0.35
    plt.bar(x - width/2, observed_counts.values, width, label='Observé', color='#f59e0b')
    plt.bar(x + width/2, expected_counts, width, label='Théorique attendu', color='#9ca3af', alpha=0.7)
    plt.title("Numéros communs entre deux tirages consécutifs", fontsize=14, fontweight='bold')
    plt.xlabel("Nombre de numéros communs", fontsize=12)
    plt.ylabel("Nombre d'occurrences", fontsize=12)
    plt.xticks(x)
    plt.legend()
    plt.yscale('log') # Log scale because 3, 4, 5 are extremely rare
    plt.ylabel("Nombre d'occurrences (Échelle Log)", fontsize=12)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'consecutive_repeats.png'))
    plt.close()

def main():
    print("=== DÉBUT DE L'ANALYSE EXPLORATOIRE DES DONNÉES (EDA) ===")
    df = load_data()
    print(f"Base de données chargée. {len(df)} tirages trouvés du {df['date'].min().strftime('%d/%m/%Y')} au {df['date'].max().strftime('%d/%m/%Y')}.")
    
    analyze_uniformity_all_numbers(df)
    analyze_uniformity_first_number(df)
    analyze_sums(df)
    analyze_even_odd(df)
    analyze_temporal_repeats(df)
    
    print("\n=== FIN DE L'ANALYSE EXPLORATOIRE ===")
    print(f"Toutes les figures ont été sauvegardées dans : {PLOTS_DIR}")

if __name__ == '__main__':
    main()
