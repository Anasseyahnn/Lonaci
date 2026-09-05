"""Modèle séquentiel Deep Learning (LSTM/GRU) — dernière méthode manquante du PLAN.md.

Traite l'historique des tirages comme une séquence de vecteurs binaires
(présence/absence de chacun des 90 numéros) et entraîne un réseau récurrent à
prédire le vecteur du tirage suivant à partir d'une fenêtre glissante des N
tirages précédents. Évalué exactement comme train.py (top-5 prédits vs
numéros réellement gagnants, comparé à l'espérance aléatoire théorique de
0.278) pour une comparaison honnête et directe avec les modèles classiques.

SUPERSEDÉ (2026-09-05) : le plus grave des scripts pré-refonte — il ne
sélectionne même pas la colonne `game`, donc traite TOUS les jeux (Digital
21h, National, Wari, Reveil, ...) comme UNE SEULE séquence temporelle
entrelacée. Le réseau apprend des dépendances tirage(t-1)->tirage(t) entre
des jeux différents tirés à des heures et par des mécanismes différents —
des dépendances qui n'existent pas dans la réalité. Ne pas réutiliser sans
reconstruire la séquence par jeu (cf. game_config.py).
"""
import sqlite3
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import os

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(ANALYSIS_DIR, '..', 'database', 'lonaci.db'))
MODEL_PATH = os.path.join(ANALYSIS_DIR, 'lstm_model.pt')

WINDOW = 50          # nombre de tirages passés utilisés comme contexte
HIDDEN_SIZE = 64
EPOCHS = 15
BATCH_SIZE = 64
LR = 1e-3
RANDOM_EXPECTATION = 0.278  # 5 numéros prédits, 5/90 de chance chacun


def load_presence_matrix():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT date, winning_1, winning_2, winning_3, winning_4, winning_5
        FROM draws WHERE is_valid = 1 ORDER BY date ASC, id ASC
    """, conn)
    conn.close()

    winning_cols = ['winning_1', 'winning_2', 'winning_3', 'winning_4', 'winning_5']
    draws = df[winning_cols].values
    n = len(df)
    presence = np.zeros((n, 90), dtype=np.float32)
    for t in range(n):
        presence[t, draws[t] - 1] = 1.0  # numéros 1-90 -> index 0-89
    return presence


class DrawSequenceDataset(Dataset):
    def __init__(self, presence, indices, window):
        self.presence = presence
        self.indices = indices  # indices t pour lesquels on prédit presence[t] à partir de [t-window:t]
        self.window = window

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        t = self.indices[i]
        x = self.presence[t - self.window:t]          # (window, 90)
        y = self.presence[t]                            # (90,)
        return torch.from_numpy(x), torch.from_numpy(y)


class DrawGRU(nn.Module):
    def __init__(self, input_size=90, hidden_size=HIDDEN_SIZE):
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, batch_first=True, num_layers=2, dropout=0.2)
        self.head = nn.Linear(hidden_size, input_size)

    def forward(self, x):
        out, _ = self.gru(x)
        last = out[:, -1, :]           # dernier état caché de la séquence
        return self.head(last)          # logits pour les 90 numéros


def evaluate_top5(model, dataset, device):
    """Même métrique que evaluate_predictions() dans train.py : nb moyen de
    numéros corrects parmi le top-5 prédit, comparé à l'aléatoire théorique."""
    model.eval()
    correct_counts = []
    loader = DataLoader(dataset, batch_size=128, shuffle=False)
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            probs = torch.sigmoid(logits)
            top5 = torch.topk(probs, k=5, dim=1).indices     # (batch, 5)
            for b in range(x.size(0)):
                predicted = set(top5[b].tolist())
                actual = set(torch.nonzero(y[b]).squeeze(1).tolist())
                correct_counts.append(len(predicted & actual))
    avg_correct = float(np.mean(correct_counts))
    improvement = (avg_correct - RANDOM_EXPECTATION) / RANDOM_EXPECTATION * 100
    print(f"Modèle: LSTM/GRU séquentiel (fenêtre={WINDOW})")
    print(f"  Moyenne de numéros devinés par tirage : {avg_correct:.4f} (Aléatoire théorique : {RANDOM_EXPECTATION:.3f})")
    print(f"  Amélioration par rapport à l'aléatoire : {improvement:+.2f}%")
    cg = np.array(correct_counts)
    for min_correct in [1, 2, 3]:
        pct = np.mean(cg >= min_correct) * 100
        print(f"  Taux de tirages avec au moins {min_correct} bon(s) numéro(s) : {pct:.2f}%")
    return avg_correct


def main():
    torch.manual_seed(42)
    device = torch.device('cpu')

    presence = load_presence_matrix()
    n = len(presence)
    print(f"{n} tirages chargés.")

    all_indices = np.arange(WINDOW, n)
    split_idx = int(len(all_indices) * 0.8)
    train_indices = all_indices[:split_idx]
    test_indices = all_indices[split_idx:]
    print(f"Fenêtres d'entraînement : {len(train_indices)}, de test : {len(test_indices)}")

    train_ds = DrawSequenceDataset(presence, train_indices, WINDOW)
    test_ds = DrawSequenceDataset(presence, test_indices, WINDOW)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)

    model = DrawGRU().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    # BCEWithLogitsLoss + pos_weight : sans ça, le modèle apprend juste à
    # prédire "0 partout" car 85/90 numéros sont absents à chaque tirage.
    pos_weight = torch.tensor([(90 - 5) / 5.0])
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    print("\n--- ENTRAÎNEMENT LSTM/GRU ---")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
        avg_loss = total_loss / len(train_ds)
        if epoch % 3 == 0 or epoch == 1:
            print(f"  Epoch {epoch}/{EPOCHS} - loss: {avg_loss:.4f}")

    print("\n--- ÉVALUATION SUR LE JEU DE TEST (chronologique, pas de lookahead) ---")
    evaluate_top5(model, test_ds, device)

    torch.save(model.state_dict(), MODEL_PATH)
    print(f"\nModèle sauvegardé dans : {MODEL_PATH}")


if __name__ == '__main__':
    main()
