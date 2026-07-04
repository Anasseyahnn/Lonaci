import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from sklearn.metrics import precision_score, recall_score
import os
import pickle

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))
MODEL_PATH = os.path.join(ANALYSIS_DIR, 'best_model.pkl')

def load_draws():
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT date, game, 
               winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws
        ORDER BY date ASC, id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def build_features(df):
    print("Construction des features (historiques des numéros)...")
    
    # winning numbers matrix
    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    draws_matrix = df[winning_cols].values
    
    num_draws = len(df)
    
    # We will build features starting from draw index 200 to have enough history
    start_idx = 200
    
    X_list = []
    y_list = []
    meta_list = [] # to keep track of date/game for evaluation
    
    # Pre-calculate presence matrix for speed: shape (num_draws, 91)
    presence = np.zeros((num_draws, 91), dtype=int)
    for t in range(num_draws):
        presence[t, draws_matrix[t]] = 1
        
    # Pre-calculate cumulative frequencies
    cum_freq = np.cumsum(presence, axis=0)
    
    # Pre-calculate last appearance index to compute delay
    # last_seen[t, num] = index of last draw before t where num appeared
    last_seen = np.zeros((num_draws, 91), dtype=int)
    current_last_seen = np.zeros(91, dtype=int)
    for t in range(num_draws):
        last_seen[t] = current_last_seen.copy()
        for num in draws_matrix[t]:
            current_last_seen[num] = t

    for t in range(start_idx, num_draws):
        if t % 1000 == 0:
            print(f"  Traitement du tirage {t}/{num_draws}...")
            
        date = df.loc[t, 'date']
        game = df.loc[t, 'game']
        
        # Target: 1 if number is in winning, else 0
        y_draw = presence[t] # size 91
        
        for num in range(1, 91):
            # 1. Frequency in last 10, 50, 100 draws
            f10 = np.sum(presence[t-10:t, num])
            f50 = np.sum(presence[t-50:t, num])
            f100 = np.sum(presence[t-100:t, num])
            
            # 2. Delay since last appearance
            last_t = last_seen[t, num]
            delay = t - last_t if last_t > 0 else t # fallback to current index if never seen
            
            # 3. Global historical frequency
            glob_f = cum_freq[t-1, num] / t
            
            X_list.append([num, f10, f50, f100, delay, glob_f])
            y_list.append(y_draw[num])
            meta_list.append((t, date, game, num))
            
    X = np.array(X_list)
    y = np.array(y_list)
    
    feature_names = ['number', 'freq_10', 'freq_50', 'freq_100', 'delay', 'global_freq']
    X_df = pd.DataFrame(X, columns=feature_names)
    
    meta_df = pd.DataFrame(meta_list, columns=['draw_idx', 'date', 'game', 'number'])
    
    return X_df, y, meta_df

def evaluate_predictions(y_true, y_prob, meta_df, model_name):
    # Combine true targets, predicted probabilities and metadata
    eval_df = meta_df.copy()
    eval_df['y_true'] = y_true
    eval_df['y_prob'] = y_prob
    
    # For each draw, select the top 5 predicted numbers
    correct_guesses = []
    grouped = eval_df.groupby('draw_idx')
    
    for name, group in grouped:
        # Get actual winning numbers
        actual_winners = set(group[group['y_true'] == 1]['number'].values)
        
        # Get top 5 predicted numbers
        predicted_top5 = set(group.sort_values(by='y_prob', ascending=False).head(5)['number'].values)
        
        # Count common elements
        matches = len(actual_winners.intersection(predicted_top5))
        correct_guesses.append(matches)
        
    avg_correct = np.mean(correct_guesses)
    # Expected number of correct guesses by random choice is 5 * 5/90 = 0.278
    random_expectation = 0.278
    improvement = ((avg_correct - random_expectation) / random_expectation) * 100
    
    print(f"Modèle: {model_name}")
    print(f"  Moyenne de numéros devinés par tirage : {avg_correct:.4f} (Aléatoire théorique : {random_expectation:.3f})")
    print(f"  Amélioration par rapport à l'aléatoire : {improvement:+.2f}%")
    
    # Calculate percentage of draws with at least 1, 2, 3 correct guesses
    cg_array = np.array(correct_guesses)
    for min_correct in [1, 2, 3]:
        pct = np.mean(cg_array >= min_correct) * 100
        print(f"  Taux de tirages avec au moins {min_correct} bon(s) numéro(s) : {pct:.2f}%")
        
    return avg_correct

def main():
    df = load_draws()
    print(f"Chargement de {len(df)} tirages pour l'entraînement...")
    
    X, y, meta = build_features(df)
    
    # Chronological Split: 80% train, 20% test (to avoid lookahead bias!)
    unique_draws = meta['draw_idx'].unique()
    split_idx = int(len(unique_draws) * 0.8)
    train_draw_indices = unique_draws[:split_idx]
    test_draw_indices = unique_draws[split_idx:]
    
    train_mask = meta['draw_idx'].isin(train_draw_indices)
    test_mask = meta['draw_idx'].isin(test_draw_indices)
    
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    meta_test = meta[test_mask]
    
    print(f"Tirages d'entraînement : {len(train_draw_indices)}")
    print(f"Tirages de test : {len(test_draw_indices)}")
    
    # Train Naive Baseline (predict the global historical top 5)
    print("\n--- 1. ÉVALUATION DE LA BASELINE NAÏVE (Les 5 numéros historiquement les plus fréquents) ---")
    # Pre-calculate frequencies on train set
    conn = sqlite3.connect(DB_PATH)
    # Get only train set date boundary
    train_max_date = df.loc[train_draw_indices[-1], 'date']
    query = f"SELECT winning_1, winning_2, winning_3, winning_4, winning_5 FROM draws WHERE date <= '{train_max_date}'"
    train_draws = pd.read_sql_query(query, conn).values.flatten()
    conn.close()
    
    top5_historic = pd.Series(train_draws).value_counts().head(5).index.tolist()
    print(f"Top 5 numéros les plus fréquents en entraînement : {top5_historic}")
    
    # For naive evaluation, the probability is 1 for these top 5, 0 for others
    naive_probs = np.zeros(len(X_test))
    naive_probs[X_test['number'].isin(top5_historic)] = 1.0
    evaluate_predictions(y_test, naive_probs, meta_test, "Baseline Naïve (Top 5 Fréquent)")
    
    # Train Logistic Regression
    print("\n--- 2. ENTRAÎNEMENT RÉGRESSION LOGISTIQUE ---")
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X_train, y_train)
    lr_probs = lr.predict_proba(X_test)[:, 1]
    lr_score = evaluate_predictions(y_test, lr_probs, meta_test, "Régression Logistique")
    
    # Train Random Forest
    print("\n--- 3. ENTRAÎNEMENT RANDOM FOREST ---")
    rf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    rf_probs = rf.predict_proba(X_test)[:, 1]
    rf_score = evaluate_predictions(y_test, rf_probs, meta_test, "Random Forest")
    
    # Train XGBoost
    print("\n--- 4. ENTRAÎNEMENT XGBOOST ---")
    # scale_pos_weight adjusts for class imbalance (5 winning numbers out of 90 = ~5.5% positives)
    scale_pos_weight = (90 - 5) / 5.0
    xgb = XGBClassifier(n_estimators=150, max_depth=6, scale_pos_weight=scale_pos_weight, random_state=42, n_jobs=-1)
    xgb.fit(X_train, y_train)
    xgb_probs = xgb.predict_proba(X_test)[:, 1]
    xgb_score = evaluate_predictions(y_test, xgb_probs, meta_test, "XGBoost")
    
    # Select best model
    scores = {
        'Logistic Regression': (lr_score, lr),
        'Random Forest': (rf_score, rf),
        'XGBoost': (xgb_score, xgb)
    }
    
    best_name, (best_score, best_model) = max(scores.items(), key=lambda k: k[1][0])
    print(f"\n=== MEILLEUR MODÈLE SÉLECTIONNÉ : {best_name} (Score : {best_score:.4f}) ===")
    
    # Save best model to disk
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(best_model, f)
    print(f"Modèle sauvegardé dans : {MODEL_PATH}")

if __name__ == '__main__':
    main()
