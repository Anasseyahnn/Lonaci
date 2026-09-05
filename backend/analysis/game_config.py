"""Classification des jeux LONACI par mécanisme de tirage — source unique de
vérité, à importer partout au lieu de recopier les listes (elles étaient
dupliquées dans eda_gaps_crossgame.py, prospective_tracker.py et
model_challenge/compare_models.py, avec le risque qu'elles divergent).

Digital  : tirages rapides multiples/jour, RNG logiciel suspecté (pas de
           machine à boules physique) — seul mécanisme où un biais
           algorithmique est plausible.
Physique : tirages classiques à boules, servent de témoin (doivent rester
           à ~0% d'écart au hasard théorique).

Ne jamais pooler les deux groupes dans un même calcul de fréquence/biais :
un biais Digital viendrait d'une faiblesse logicielle, un biais physique
d'une usure mécanique — ce sont deux phénomènes différents, mélanger leurs
tirages dilue ou fabrique un signal qui n'existe dans aucun des deux.
"""

DIGITAL_GAMES = ['Digital Reveil 7h', 'Digital Reveil 8h', 'Digital 21h', 'Digital 22h', 'Digital 23h']
CONTROL_GAMES = ['Special Weekend 1h', 'Special Weekend 3h', 'Wari', 'Soutra', 'National']

ALL_KNOWN_GAMES = DIGITAL_GAMES + CONTROL_GAMES


def classify_game(game):
    if game in DIGITAL_GAMES:
        return 'digital'
    if game in CONTROL_GAMES:
        return 'physique'
    return 'inconnu'
