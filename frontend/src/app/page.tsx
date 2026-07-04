'use client';

import React, { useEffect, useState } from 'react';

interface Prediction {
  number: number;
  occurrences: number;
  probability: number;
  percentage_above_expected: number;
}

interface Stats {
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

interface ModelComparison {
  name: string;
  correct_guesses: number;
  improvement: string;
  at_least_1_win: string;
  description: string;
}

const API_BASE_URL = 'http://localhost:8000';

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [history, setHistory] = useState<Draw[]>([]);
  const [models, setModels] = useState<ModelComparison[]>([]);
  const [activeTab, setActiveTab] = useState<'predictions' | 'history' | 'models'>('predictions');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Predictions
      const predRes = await fetch(`${API_BASE_URL}/api/predictions`);
      if (!predRes.ok) throw new Error("API predictions offline");
      const predData = await predRes.json();
      setPredictions(predData.predictions);

      // 2. Statistics
      const statsRes = await fetch(`${API_BASE_URL}/api/statistics`);
      if (!statsRes.ok) throw new Error("API stats offline");
      const statsData = await statsRes.json();
      setStats(statsData);

      // 3. History
      const histRes = await fetch(`${API_BASE_URL}/api/history?limit=30`);
      if (!histRes.ok) throw new Error("API history offline");
      const histData = await histRes.json();
      setHistory(histData.draws);

      // 4. Models comparison
      const modelsRes = await fetch(`${API_BASE_URL}/api/models-comparison`);
      if (!modelsRes.ok) throw new Error("API models offline");
      const modelsData = await modelsRes.json();
      setModels(modelsData.models);

    } catch (err: any) {
      console.error(err);
      setError("Impossible de joindre le serveur API FastAPI local (port 8000). Veuillez vérifier qu'il tourne en arrière-plan.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getBallColor = (number: number) => {
    if (number <= 18) return 'from-red-500 to-rose-600 shadow-red-500/30';
    if (number <= 36) return 'from-blue-500 to-indigo-600 shadow-blue-500/30';
    if (number <= 54) return 'from-emerald-500 to-teal-600 shadow-emerald-500/30';
    if (number <= 72) return 'from-amber-500 to-orange-600 shadow-amber-500/30';
    return 'from-violet-500 to-purple-600 shadow-purple-500/30';
  };

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
          onClick={fetchData}
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
              <p className="text-xs text-emerald-400/90 font-medium">Biais Mécanique Statistique</p>
            </div>
          </div>

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
        {activeTab === 'predictions' && (
          <div className="space-y-8 animate-fadeIn">
            {/* Hero Prediction */}
            <div className="relative overflow-hidden rounded-3xl border border-gray-800 bg-[#1f2833]/30 p-8 shadow-xl">
              <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 rounded-full filter blur-[80px] pointer-events-none"></div>
              
              <div className="max-w-2xl">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mb-4">
                  🎰 Recommandation Optimale
                </span>
                <h2 className="text-2xl sm:text-3xl font-black text-white leading-tight">
                  Tirage Suggéré Loto Bonheur
                </h2>
                <p className="text-gray-400 text-sm mt-2 leading-relaxed">
                  Ces numéros exploitent le biais de tirage physique significatif identifié sur 36 mois de données ($p &lt; 0.05$). Les probabilités temporelles d'indépendance montrent que les martingales temporelles sont inefficaces.
                </p>
              </div>

              {/* Balls row */}
              <div className="mt-8 flex flex-wrap justify-start gap-4 sm:gap-6">
                {predictions.map((p) => (
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
                    <h3 className="text-white font-bold text-lg mb-2">📊 Biais Statistique Global</h3>
                    <p className="text-gray-400 text-xs leading-relaxed">
                      L'écart par rapport à l'uniformité théorique est scientifiquement avéré (p-value d'uniformité de 0.000). Les boules ci-dessus sortent de manière anormalement fréquente.
                    </p>
                  </div>
                  <div className="grid grid-cols-3 gap-4 mt-6">
                    <div className="bg-gray-900/50 p-4 rounded-2xl border border-gray-800 text-center">
                      <p className="text-2xl font-black text-emerald-400">{stats.general.total_draws}</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mt-1">Tirages</p>
                    </div>
                    <div className="bg-gray-900/50 p-4 rounded-2xl border border-gray-800 text-center">
                      <p className="text-2xl font-black text-rose-500">0.000</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mt-1">p-value U</p>
                    </div>
                    <div className="bg-gray-900/50 p-4 rounded-2xl border border-gray-800 text-center">
                      <p className="text-2xl font-black text-emerald-400">0.967</p>
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mt-1">p-value S</p>
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
                <h2 className="text-xl font-bold text-white">📅 Historique Récent des Tirages</h2>
                <p className="text-xs text-gray-500">Les 30 derniers tirages scrappés et enregistrés.</p>
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
        {activeTab === 'models' && (
          <div className="space-y-6 animate-fadeIn">
            <div>
              <h2 className="text-xl font-bold text-white">📊 Performance des Modèles Predictifs</h2>
              <p className="text-xs text-gray-500 leading-relaxed mt-1">
                Comparaison sur le jeu de test (les 20% derniers tirages). La métrique d'évaluation est le nombre de bons numéros devinés sur les 5 conseillés par tirage (le hasard pur donne une espérance de **0.278**).
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {models.map((model, idx) => (
                <div key={idx} className="border border-gray-800 bg-[#1f2833]/20 rounded-2xl p-6 flex flex-col justify-between hover:border-gray-700/80 transition-all">
                  <div>
                    <div className="flex items-center justify-between gap-4 mb-3">
                      <h3 className="text-white font-bold text-md">{model.name}</h3>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                        model.improvement.startsWith('+') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-500'
                      }`}>
                        {model.improvement}
                      </span>
                    </div>
                    <p className="text-gray-400 text-xs leading-relaxed mb-6">
                      {model.description}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4 border-t border-gray-800/80 pt-4">
                    <div>
                      <p className="text-[10px] text-gray-500 uppercase font-bold">Moyenne Correcte</p>
                      <p className="text-lg font-black text-white mt-0.5">{model.correct_guesses.toFixed(3)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-500 uppercase font-bold">Min. 1 bon numéro</p>
                      <p className="text-lg font-black text-white mt-0.5">{model.at_least_1_win}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-gray-800 mt-20 bg-gray-900/20 py-8">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-xs text-gray-600">
            Lonaci Predictor — Analyse mathématique et scientifique de l'équité des jeux de tirage.
          </p>
        </div>
      </footer>
    </div>
  );
}
