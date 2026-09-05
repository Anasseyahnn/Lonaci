"""Classification des jeux LONACI par mécanisme de tirage — source unique de
vérité, à importer partout au lieu de recopier les listes (elles étaient
dupliquées dans eda_gaps_crossgame.py, prospective_tracker.py et
model_challenge/compare_models.py, avec le risque qu'elles divergent).

Digital  : tirages rapides, tous les 7 jours de la semaine, RNG logiciel
           suspecté (pas de machine à boules physique) — seul mécanisme où
           un biais algorithmique est plausible.
Physique : tirages spéciaux, UN SEUL jour fixe par semaine (ex. Wari=vendredi,
           Baraka=mercredi...) — servent de témoin (doivent rester à ~0%
           d'écart au hasard théorique).

Classification (2026-09-05) fondée sur la cadence empirique par jeu, pas sur
le nom : tous les jeux ci-dessous se répartissent en deux profils temporels
nets et mutuellement exclusifs, sans zone grise (voir calcul dans
[[project-lonaci-alignement-comprehension-jeu]]) —
  - profil "Digital" : ~7 tirages/semaine, actif les 7 jours
  - profil "Physique" : ~1 tirage/semaine, actif un seul jour fixe
Aucun jeu n'a un nom contenant "Digital" en dehors du premier groupe, et
aucun des jeux au profil hebdomadaire fixe n'a jamais eu un tirage un autre
jour que le sien sur 3 ans de données (1114-1131 jours d'historique selon le
jeu) — le signal est net, pas une extrapolation fragile.
C'est une inférence par cadence opérationnelle, PAS une confirmation
officielle LONACI du mécanisme physique/logiciel réel — à traiter comme
« très probable », pas « certain ».

Cas à part :
  - Afterwork : profil quasi-identique au groupe Digital (~6.8 tirages/semaine,
    actif 7j/7) malgré un nom qui ne contient pas "Digital" — classé digital.
  - Day Off : cadence irrégulière (~0.28 tirage/semaine, jours non fixes) —
    ne correspond à aucun des deux profils, classé "inconnu" volontairement.

Ne jamais pooler les deux groupes dans un même calcul de fréquence/biais :
un biais Digital viendrait d'une faiblesse logicielle, un biais physique
d'une usure mécanique — ce sont deux phénomènes différents, mélanger leurs
tirages dilue ou fabrique un signal qui n'existe dans aucun des deux.
"""

DIGITAL_GAMES = [
    'Digital Reveil 7h', 'Digital Reveil 8h', 'Digital 21h', 'Digital 22h', 'Digital 23h',
    'Afterwork',
]

CONTROL_GAMES = [
    'Special Weekend 1h', 'Special Weekend 3h', 'Wari', 'Soutra', 'National',
    'Akwaba', 'Awale', 'Baraka', 'Benediction', 'Cash', 'Diamant', 'Emergence',
    'Espoir', 'Etoile', 'Fortune', 'Fortune Thursday', 'Friday Bonanza', 'Kado',
    'La Matinale', 'Lucky Tuesday', 'Midweek', 'Moaye', 'Monday Special', 'Monni',
    'Premiere Heure', 'Prestige', 'Privilege', 'Reveil', 'Sika', 'Solution',
]

# Cadence irrégulière (~0.28 tirage/semaine, jours non fixes) — ne correspond
# à aucun des deux profils, classification volontairement laissée ouverte.
UNCLASSIFIED_GAMES = ['Day Off']

ALL_KNOWN_GAMES = DIGITAL_GAMES + CONTROL_GAMES + UNCLASSIFIED_GAMES


def classify_game(game):
    if game in DIGITAL_GAMES:
        return 'digital'
    if game in CONTROL_GAMES:
        return 'physique'
    return 'inconnu'
