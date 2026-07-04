import React, { useEffect, useState } from 'react';
import { StyleSheet, ActivityIndicator, Pressable, ScrollView, View, FlatList } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { API_BASE_URL } from '@/constants/api';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

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

export default function ExploreScreen() {
  const safeAreaInsets = useSafeAreaInsets();
  const theme = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Draw[]>([]);
  const [models, setModels] = useState<ModelComparison[]>([]);
  const [activeTab, setActiveTab] = useState<'history' | 'models'>('history');

  const insets = {
    ...safeAreaInsets,
    bottom: safeAreaInsets.bottom + BottomTabInset + Spacing.three,
  };

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch history
      const histRes = await fetch(`${API_BASE_URL}/api/history?limit=30`);
      if (!histRes.ok) throw new Error("Erreur de communication API");
      const histData = await histRes.json();
      setHistory(histData.draws);

      // Fetch models
      const modelsRes = await fetch(`${API_BASE_URL}/api/models-comparison`);
      if (modelsRes.ok) {
        const modelsData = await modelsRes.json();
        setModels(modelsData.models);
      }
    } catch (err) {
      setError("Erreur lors de la récupération des données.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getBallColor = (number: number) => {
    if (number <= 18) return '#ef4444';
    if (number <= 36) return '#3b82f6';
    if (number <= 54) return '#10b981';
    if (number <= 72) return '#f59e0b';
    return '#8b5cf6';
  };

  if (loading) {
    return (
      <ThemedView style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#10b981" />
        <ThemedText style={{ marginTop: Spacing.four }}>Chargement...</ThemedText>
      </ThemedView>
    );
  }

  return (
    <ScrollView
      style={[styles.scrollView, { backgroundColor: theme.background }]}
      contentInset={insets}
      contentContainerStyle={styles.scrollContent}
    >
      <ThemedView style={styles.container}>
        {/* Navigation Tabs */}
        <View style={styles.tabContainer}>
          <Pressable 
            style={[styles.tab, activeTab === 'history' && { borderBottomColor: '#10b981' }]}
            onPress={() => setActiveTab('history')}
          >
            <ThemedText style={[styles.tabText, activeTab === 'history' && styles.activeTabText]}>
              Historique
            </ThemedText>
          </Pressable>
          <Pressable 
            style={[styles.tab, activeTab === 'models' && { borderBottomColor: '#10b981' }]}
            onPress={() => setActiveTab('models')}
          >
            <ThemedText style={[styles.tabText, activeTab === 'models' && styles.activeTabText]}>
              Comparatif Modèles
            </ThemedText>
          </Pressable>
        </View>

        {activeTab === 'history' ? (
          <View style={styles.section}>
            <ThemedText type="subtitle" style={styles.sectionTitle}>
              Derniers Tirages Loto Bonheur
            </ThemedText>
            
            {history.map((item, idx) => (
              <ThemedView key={idx} type="backgroundElement" style={styles.drawCard}>
                <View style={styles.drawMeta}>
                  <ThemedText style={styles.drawDate}>{item.date}</ThemedText>
                  <ThemedText themeColor="textSecondary" style={styles.drawGame}>{item.game}</ThemedText>
                </View>
                
                <View style={styles.winningRow}>
                  {item.winning_numbers.map((num) => (
                    <View key={num} style={[styles.miniBall, { backgroundColor: getBallColor(num) }]}>
                      <ThemedText style={styles.miniBallText}>{num}</ThemedText>
                    </View>
                  ))}
                </View>
              </ThemedView>
            ))}
          </View>
        ) : (
          <View style={styles.section}>
            <ThemedText type="subtitle" style={styles.sectionTitle}>
              Performances Prédictives (Machine Learning)
            </ThemedText>
            
            <ThemedText type="small" themeColor="textSecondary" style={styles.introText}>
              Chaque modèle est évalué sur un jeu de test chronologique (les 20% derniers tirages). La métrique principale est le nombre moyen de boules correctes devinées dans une sélection recommandée de 5 numéros (Top 5). Le hasard pur donne **0.278** boules correctes en moyenne.
            </ThemedText>

            {models.map((model, idx) => (
              <ThemedView key={idx} type="backgroundElement" style={styles.modelCard}>
                <View style={styles.modelHeader}>
                  <ThemedText style={styles.modelName}>{model.name}</ThemedText>
                  <ThemedText style={[
                    styles.modelScore, 
                    model.improvement.startsWith('+') ? { color: '#10b981' } : { color: '#ef4444' }
                  ]}>
                    {model.improvement}
                  </ThemedText>
                </View>

                <View style={styles.modelGrid}>
                  <View style={styles.gridItem}>
                    <ThemedText type="small" themeColor="textSecondary">Moyenne devinée</ThemedText>
                    <ThemedText style={styles.gridVal}>{model.correct_guesses.toFixed(3)}</ThemedText>
                  </View>
                  <View style={styles.gridItem}>
                    <ThemedText type="small" themeColor="textSecondary">Min. 1 bon numéro</ThemedText>
                    <ThemedText style={styles.gridVal}>{model.at_least_1_win}</ThemedText>
                  </View>
                </View>

                <ThemedText type="small" style={styles.modelDesc}>
                  {model.description}
                </ThemedText>
              </ThemedView>
            ))}
          </View>
        )}
      </ThemedView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    justifyContent: 'center',
    flexDirection: 'row',
  },
  container: {
    maxWidth: MaxContentWidth,
    flexGrow: 1,
    paddingHorizontal: Spacing.four,
    paddingTop: Spacing.four,
    paddingBottom: BottomTabInset + Spacing.six,
    gap: Spacing.four,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  tabContainer: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
    marginBottom: Spacing.two,
  },
  tab: {
    flex: 1,
    paddingVertical: Spacing.three,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#9ca3af',
  },
  activeTabText: {
    color: '#10b981',
  },
  section: {
    gap: Spacing.three,
  },
  sectionTitle: {
    fontWeight: 'bold',
    marginBottom: Spacing.two,
  },
  introText: {
    lineHeight: 18,
    marginBottom: Spacing.three,
  },
  drawCard: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  drawMeta: {
    gap: Spacing.one,
  },
  drawDate: {
    fontWeight: 'bold',
    fontSize: 15,
  },
  drawGame: {
    fontSize: 13,
  },
  winningRow: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  miniBall: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 2,
  },
  miniBallText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: 'bold',
  },
  modelCard: {
    padding: Spacing.four,
    borderRadius: Spacing.three,
    gap: Spacing.two,
  },
  modelHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modelName: {
    fontWeight: 'bold',
    fontSize: 16,
  },
  modelScore: {
    fontWeight: 'bold',
    fontSize: 16,
  },
  modelGrid: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: '#374151',
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
    paddingVertical: Spacing.two,
    marginVertical: Spacing.one,
  },
  gridItem: {
    flex: 1,
    alignItems: 'center',
  },
  gridVal: {
    fontWeight: 'bold',
    fontSize: 15,
    marginTop: Spacing.one,
  },
  modelDesc: {
    lineHeight: 16,
  },
});
