# Plan de Développement — Projet Lonaci (Analyse & Prédiction)

Ce document présente l'architecture et les étapes de développement de l'application de collecte, d'analyse statistique et de prédiction du jeu **Loto Bonheur** (LONACI).

---

## 1. Objectifs du Projet
1. **Collecte de Données (Scraping)** : Récupérer l'intégralité des tirages historiques du Loto Bonheur sur le site officiel [lotobonheur.ci](https://lotobonheur.ci/resultats).
2. **Base de Données** : Structurer et stocker ces données dans une base locale SQLite (`lonaci.db`) pour faciliter les requêtes.
3. **Analyse Statistique & Détection d'Anomalies (EDA)** : 
   * Tester l'équité du jeu (Test du Chi-deux d'ajustement pour vérifier l'uniformité de la distribution des numéros).
   * Analyser l'indépendance temporelle (Autocorrélation, séries temporelles) pour voir si les résultats sont manipulés ou biaisés.
4. **Modélisation ML / DL** :
   * Tester plusieurs approches de prédiction (Classification multi-label, LSTM/GRU pour l'analyse de séquences, XGBoost pour les corrélations).
   * Comparer les performances par rapport à un tirage purement aléatoire.
5. **Application Mobile (React Native + Expo)** :
   * Créer une interface premium pour visualiser les statistiques de tirages.
   * Afficher les prédictions générées par le meilleur modèle.

---

## 2. Architecture du Projet

```
F:\Startup\Lonaci/
├── app/                  # Application mobile React Native (Expo Router) - Racine actuelle
├── backend/              # Partie Données, APIs et Machine Learning
│   ├── database/         # Fichiers de base de données (lonaci.db, schema.sql)
│   ├── scraper/          # Scripts de scraping (Puppeteer / Node.js)
│   ├── analysis/         # Analyse de données et modèles de prédiction
│   │   ├── eda.ipynb     # Notebook d'analyse exploratoire et tests statistiques
│   │   ├── models/       # Scripts d'entraînement (ML/Deep Learning)
│   │   └── predictor.py  # Script principal d'inférence
│   └── api/              # API REST (FastAPI) pour servir les prédictions et historiques à l'application
```

---

## 3. Plan de Route (Roadmap)

### Étape 1 : Collecte et Stockage (Scraping)
* Récupérer le code du scraper Puppeteer existant et l'adapter pour exporter directement dans une base SQLite localisée dans `backend/database/lonaci.db`.
* Créer un script d'initialisation de base de données (`init_db.js` ou `db.py`) avec la table `draws` contenant :
  * `id` (Clé primaire)
  * `date` (YYYY-MM-DD)
  * `game` (Nom du tirage : Soutra, Diamant, Moaye, Afterwork, etc.)
  * `winning_1` à `winning_5` (Les 5 premiers numéros gagnants)
  * `machine_1` à `machine_5` (Les 5 numéros de la machine)

### Étape 2 : Analyse Exploratoire & Tests d'Équité (EDA)
* Mettre en place un environnement Jupyter dans `backend/analysis/`.
* Réaliser les tests statistiques suivants :
  * **Test du Chi-deux ($\chi^2$)** : Vérifier si chaque numéro de 1 à 90 a la même probabilité d'apparaître ($p = 1/90$).
  * **Analyse des Écarts (Gaps)** : Calculer la distribution du nombre de tirages entre deux apparitions successives d'un même numéro.
  * **Autocorrélation** : Vérifier si le tirage $T$ dépend des tirages précédents $T-1$, $T-2$.
  * **Distribution des sommes et parité** : Analyser si la distribution de la somme des 5 numéros et le ratio Pairs/Impairs respectent les lois de probabilités théoriques.

### Étape 3 : Modélisation et Prédiction (ML/DL)
* **Modèles de classification** (XGBoost, Random Forest) : Prédire si un numéro spécifique sera tiré au prochain tirage sur la base de caractéristiques d'historique court (fréquence récente, retard, etc.).
* **Modèles de Deep Learning séquentiels** (LSTM / GRU en PyTorch/TensorFlow) : Modéliser les tirages comme une série temporelle séquentielle pour capturer d'éventuels motifs récurrents ou des biais de machine de tirage.
* **Évaluation** : Comparer chaque modèle à un modèle naïf (tirage aléatoire uniforme) pour prouver scientifiquement s'il y a un gain d'information.

### Étape 4 : API et Application Mobile
* Développer une API FastAPI simple pour exposer l'historique et les prédictions du modèle.
* Développer les écrans de l'application Expo (React Native) avec un design premium (mode sombre, graphiques animés, historique interactif).
