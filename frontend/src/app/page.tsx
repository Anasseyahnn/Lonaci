'use client';

import React, { useEffect, useState } from 'react';

interface Prediction {
  number: number;
  occurrences: number;
  probability: number;
  percentage_above_expected: number;
}

interface PredictionResponse {
  game: string;
  mechanism: 'digital' | 'physique' | 'inconnu';
  n_draws_used: number;
  predictions: Prediction[];
  recommendation_logic: string;
}

interface GameInfo {
  game: string;
  mechanism: 'digital' | 'physique' | 'inconnu';
}

interface Stats {
  scope: string;
  game: string | null;
  expected_occurrences: number;
  general: {
    total_draws: number;
    first_draw_date: string;
    last_draw_date: string;
  };
  most_frequent: Array<{
    number: number;
    count: number;
    expected: number;
    ratio: number;
  }>;
  least_frequent: Array<{
    number: number;
    count: number;
    expected: number;
    ratio: number;
  }>;
}

interface Draw {
  date: string;
  game: string;
  winning_numbers: number[];
}

interface PayoutThreshold {
  count: number;
  rate: number;
  theoretical_rate: number;
  p_value_vs_random: number;
}

interface Scoreboard {
  group_label: string;
  model_version?: string;
  n: number;
  status: 'no_data' | 'insufficient_n' | 'ok';
  observed_mean_correct?: number;
  random_expectation?: number;
  improvement_pct?: number;
  distribution?: Record<string, number>;
  permutation_p_value?: number;
  payout_thresholds?: Record<string, PayoutThreshold>;
}

interface ModelsComparison {
  random_baseline_mean_correct: number;
  digital_games: string[];
  control_games: string[];
  models: Record<string, Scoreboard>;
  note: string;
}

const API_BASE_URL = 'http://localhost:8000';

const MODEL_LABELS: Record<string, string> = {
  freq_top5_v1_digital: 'Fréquence top-5 — jeux Digital',
  markov1_v1_digital: 'Chaîne de Markov ordre 1 — jeux Digital',
  freq_top5_v1_control: 'Fréquence top-5 — jeux physiques (témoin)',
};

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [games, setGames] = useState<GameInfo[]>([]);
  const [selectedGame, setSelectedGame] = useState<string>('');
  const [predictionData, setPredictionData] = useState<PredictionResponse | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [history, setHistory] = useState<Draw[]>([]);
  const [models, setModels] = useState<ModelsComparison | null>(null);
  const [activeTab, setActiveTab] = useState<'predictions' | 'history' | 'models'>('predictions');

  const fetchGameDependentData = async (game: string) => {
    const predRes = await fetch(`${API_BASE_URL}/api/predictions?game=${encodeURIComponent(game)}`);
    if (!predRes.ok) throw new Error("API predictions offline ou jeu invalide");
    setPredictionData(await predRes.json());

    const statsRes = await fetch(`${API_BASE_URL}/api/statistics?game=${encodeURIComponent(game)}`);
    if (!statsRes.ok) throw new Error("API stats offline");
    setStats(await statsRes.json());

    const histRes = await fetch(`${API_BASE_URL}/api/history?limit=30&game=${encodeURIComponent(game)}`);
    if (!histRes.ok) throw new Error("API history offline");
    const histData = await histRes.json();
    setHistory(histData.draws);
  };

  const fetchInitial = async () => {
    setLoading(true);
    setError(null);
    try {
      const gamesRes = await fetch(`${API_BASE_URL}/api/games`);
      if (!gamesRes.ok) throw new Error("API games offline");
      const gamesData = await gamesRes.json();
      const gameList: GameInfo[] = gamesData.games;
      setGames(gameList);

      // Défaut : un jeu Digital si disponible (c'est le groupe "signal"
      // suivi prospectivement), sinon le premier jeu de la liste.
      const defaultGame = gameList.find((g) => g.mechanism === 'digital')?.game ?? gameList[0]?.game;
      setSelectedGame(defaultGame);
      await fetchGameDependentData(defaultGame);

      const modelsRes = await fetch(`${API_BASE_URL}/api/models-comparison`);
      if (!modelsRes.ok) throw new Error("API models offline");
      setModels(await modelsRes.json());
    } catch (err: any) {
      console.error(err);
      setError("Impossible de joindre le serveur API FastAPI local (port 8000). Veuillez vérifier qu'il tourne en arrière-plan.");
    } finally {
      setLoading(false);
    }
  };

  const handleGameChange = async (game: string) => {
    setSelectedGame(game);
    setLoading(true);
    try {
      await fetchGameDependentData(game);
    } catch (err: any) {
      console.error(err);
      setError("Erreur lors du changement de jeu.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitial();
  }, []);

  const getBallColor = (number: number) => {
    if (number <= 18) return 'from-red-500 to-rose-600 shadow-red-500/30';
    if (number <= 36) return 'from-blue-500 to-indigo-600 shadow-blue-500/30';
    if (number <= 54) return 'from-emerald-500 to-teal-600 shadow-emerald-500/30';
    if (number <= 72) return 'from-amber-500 to-orange-600 shadow-amber-500/30';
    return 'from-violet-500 to-purple-600 shadow-purple-500/30';
  };

  const mechanismLabel = (m: string) =>
    m === 'digital' ? '🖥️ Digital (RNG logiciel suspecté)' : m === 'physique' ? '🎱 Physique (boules, témoin)' : '❓ Mécanisme non classifié';

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0d0f14] flex flex-col items-center justify-center text-white px-4">
        <div className="relative w-20 h-20">
          <div className="absolute top-0 left-0 w-full h-full border-4 border-emerald-500/20 rounded-full"></div>
          <div className="absolute top-0 left-0 w-full h-full border-4 border-t-emerald-500 rounded-full animate-spin"></div>
        </div>
        <p className="mt-6 text-gray-400 text-sm tracking-wider animate-pulse">
          Chargement de l'historique et initialisation des prédictions...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0d0f14] flex flex-col items-center justify-center text-white px-4 text-center">
        <div className="w-16 h-16 bg-red-500/10 text-red-500 flex items-center justify-center rounded-2xl mb-6 border border-red-500/20">
          <span className="text-3xl">⚠️</span>
        </div>
        <h1 className="text-xl font-bold mb-2">Connexion Échouée</h1>
        <p className="text-gray-400 max-w-md text-sm mb-6">{error}</p>
        <button
          onClick={fetchInitial}
          className="bg-emerald-500 hover:bg-emerald-600 active:scale-95 transition-all text-black font-semibold px-6 py-3 rounded-xl shadow-lg shadow-emerald-500/20 text-sm"
        >
          Réessayer la connexion
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0c10] text-[#c5c6c7] font-sans selection:bg-emerald-500 selection:text-black">
      {/* Background Decor */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-emerald-500/5 rounded-full filter blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-10 right-1/4 w-96 h-96 bg-violet-500/5 rounded-full filter blur-[100px] pointer-events-none"></div>

      <header className="border-b border-gray-800/80 bg-[#1f2833]/20 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <span className="text-black text-xl font-bold">L</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-wide">Lonaci Predictor</h1>
              <p className="text-xs text-emerald-400/90 font-medium">Prédiction par jeu — jamais tous jeux confondus</p>
            </div>
          </div>

          <select
            value={selectedGame}
            onChange={(e) => handleGameChange(e.target.value)}
            className="bg-[#1f2833] text-white text-xs font-semibold px-3 py-2 rounded-lg border border-gray-700"
          >
            {games.map((g) => (
              <option key={g.game} value={g.game}>
                {g.game} ({g.mechanism})
              </option>
            ))}
          </select>

          <div className="flex gap-1 bg-[#1f2833]/60 p-1 rounded-xl border border-gray-800">
            {(['predictions', 'history', 'models'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all duration-200 ${
                  activeTab === tab
                    ? 'bg-emerald-500 text-black shadow-md shadow-emerald-500/10'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/40'
                }`}
              >
                {tab === 'predictions' ? '💡 Prédictions' : tab === 'history' ? '📅 Historique' : '📊 Modèles'}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Tab 1: Predictions */}
        {activeTab === 'predictions' && predictionData && (
          <div className="space-y-8 animate-fadeIn">
            {/* Hero Prediction */}
            <div className="relative overflow-hidden rounded-3xl border border-gray-800 bg-[#1f2833]/30 p-8 shadow-xl">
              <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full filter blur-[80px] pointer-events-none"></div>

              <div className="max-w-2xl">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-4">
                  {mechanismLabel(predictionData.mechanism)}
                </span>
                <h2 className="text-2xl sm:text-3xl font-black text-white leading-tight">
                  {predictionData.game}
                </h2>
                <p className="text-gray-400 text-sm mt-2 leading-relaxed">
                  {predictionData.recommendation_logic}
                </p>
                <p className="text-amber-400/90 text-xs mt-3 leading-relaxed">
                  ⚠️ Ces numéros sont un classement fréquentiste, pas une garantie de gain : voir l'onglet
                  Modèles pour le taux réel de tirages atteignant le seuil du plus petit pari payant (2 bons
                  numéros).
                </p>
              </div>

              {/* Balls row */}
              <div className="mt-8 flex flex-wrap justify-start gap-4 sm:gap-6">
                {predictionData.predictions.map((p) => (
                  <div key={p.number} className="flex flex-col items-center gap-3">
                    <div className={`w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-gradient-to-br ${getBallColor(p.number)} flex items-center justify-center text-white font-extrabold text-2xl sm:text-3xl shadow-lg border border-white/10 hover:scale-105 transition-all cursor-pointer`}>
                      {p.number}
                    </div>
                    <span className="text-xs font-bold text-emerald-400">
                      +{p.percentage_above_expected.toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Frequencies and stats grids */}
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Stats cards */}
                <div className="border border-gray-800 bg-[#1f2833]/30 rounded-3xl p-6 flex flex-col justify-between">
                  <div>
                    <h3 className="text-white font-bold text-lg mb-2">📊 Statistiques — {predictionData.game}</h3>
                    <p className="text-gray-400 text-xs leading-relaxed">
                      Fréquences calculées uniquement sur ce jeu ({stats.general.total_draws} tirages en base,
                      tous jeux confondus — voir l'onglet Modèles pour la validation prospective par jeu).
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-6">
                    <div className="bg-gray-900/50 p-4 rounded-2xl border border-gray-800 text-center">
                      <p className="text-2xl font-black text-emerald-400">{predictionData.n_draws_used}</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mt-1">Tirages ({predictionData.game})</p>
                    </div>
                    <div className="bg-gray-900/50 p-4 rounded-2xl border border-gray-800 text-center">
                      <p className="text-2xl font-black text-white">{stats.expected_occurrences.toFixed(1)}</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mt-1">Attendu/numéro</p>
                    </div>
                  </div>
                </div>

                {/* Top/Bottom tables */}
                <div className="border border-gray-800 bg-[#1f2833]/30 rounded-3xl p-6">
                  <h3 className="text-white font-bold text-lg mb-4">🏆 Palmarès des Numéros</h3>
                  <div className="space-y-3">
                    {stats.most_frequent.map((item, idx) => (
                      <div key={item.number} className="flex items-center justify-between bg-gray-900/30 p-2 px-4 rounded-xl border border-gray-800/50">
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-gray-500 font-bold">#{idx + 1}</span>
                          <span className="w-8 h-8 rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold text-sm">
                            {item.number}
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-sm font-bold text-white">{item.count} tirages</span>
                          <span className="text-xs text-emerald-400 font-semibold ml-2">({(item.ratio * 100).toFixed(0)}% d'attendu)</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: History */}
        {activeTab === 'history' && (
          <div className="space-y-6 animate-fadeIn">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">📅 Historique Récent — {selectedGame}</h2>
                <p className="text-xs text-gray-500">Les 30 derniers tirages de ce jeu.</p>
              </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-gray-800 bg-[#1f2833]/10">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-gray-800 bg-[#1f2833]/35 text-gray-400 text-xs font-bold uppercase tracking-wider">
                      <th className="py-4 px-6">Date</th>
                      <th className="py-4 px-6">Type de jeu</th>
                      <th className="py-4 px-6 text-center">Numéros Gagnants</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {history.map((draw, idx) => (
                      <tr key={idx} className="hover:bg-gray-800/20 transition-all">
                        <td className="py-4 px-6 font-semibold text-white text-sm">{draw.date}</td>
                        <td className="py-4 px-6 text-gray-400 text-sm font-medium">{draw.game}</td>
                        <td className="py-4 px-6">
                          <div className="flex justify-center gap-2">
                            {draw.winning_numbers.map((num) => (
                              <span
                                key={num}
                                className={`w-8 h-8 rounded-full bg-gradient-to-br ${getBallColor(num)} flex items-center justify-center text-white text-xs font-bold shadow`}
                              >
                                {num}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Models */}
        {activeTab === 'models' && models && (
          <div className="space-y-6 animate-fadeIn">
            <div>
              <h2 className="text-xl font-bold text-white">📊 Suivi Prospectif Hors-Échantillon</h2>
              <p className="text-xs text-gray-500 leading-relaxed mt-1">
                Chiffres en direct depuis le suivi prospectif (jamais un backtest) : jeux Digital = groupe
                signal, jeux physiques = témoin (doit rester proche du hasard, espérance{' '}
                {models.random_baseline_mean_correct.toFixed(3)}). Le "taux au seuil 2N+" est le vrai
                indicateur — il compte les tirages où au moins 2 numéros sur 5 sont corrects, seuil minimum
                pour toucher un gain réel ; la moyenne de bons numéros peut s'améliorer sans qu'aucun pari ne
                devienne gagnant.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {Object.entries(models.models).map(([key, m]) => {
                const seuil2 = m.payout_thresholds?.['2'];
                const improving = (m.improvement_pct ?? 0) >= 0;
                return (
                  <div key={key} className="border border-gray-800 bg-[#1f2833]/20 rounded-2xl p-6 flex flex-col justify-between hover:border-gray-700/80 transition-all">
                    <div>
                      <div className="flex items-center justify-between gap-4 mb-3">
                        <h3 className="text-white font-bold text-md">{MODEL_LABELS[key] ?? key}</h3>
                        {m.status === 'ok' && (
                          <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${improving ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-500'}`}>
                            {improving ? '+' : ''}{m.improvement_pct?.toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <p className="text-gray-400 text-xs leading-relaxed mb-4">
                        {m.n} prédictions résolues.
                        {m.status === 'insufficient_n' && ' Encore trop peu de points pour un test fiable.'}
                        {m.status === 'no_data' && ' Aucune donnée pour l\'instant.'}
                      </p>
                    </div>

                    {m.status === 'ok' && (
                      <div className="grid grid-cols-2 gap-4 border-t border-gray-800/80 pt-4">
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase font-bold">Moyenne Correcte</p>
                          <p className="text-lg font-black text-white mt-0.5">{m.observed_mean_correct?.toFixed(3)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] text-gray-500 uppercase font-bold">Taux au seuil 2N+ (gain réel)</p>
                          <p className="text-lg font-black text-white mt-0.5">
                            {seuil2 ? `${(seuil2.rate * 100).toFixed(1)}%` : '—'}
                          </p>
                          {seuil2 && (
                            <p className="text-[10px] text-gray-500 mt-0.5">
                              théorique {(seuil2.theoretical_rate * 100).toFixed(2)}%, p={seuil2.p_value_vs_random.toFixed(3)}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-gray-800 mt-20 bg-gray-900/20 py-8">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-xs text-gray-600">
            Lonaci Predictor — analyse statistique par jeu, jamais tous jeux confondus. Un jeu Digital et un
            jeu physique ne partagent pas le même mécanisme de tirage.
          </p>
        </div>
      </footer>
    </div>
  );
}
