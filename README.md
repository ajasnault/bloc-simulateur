# Simulateur de bloc opératoire

Prototype pédagogique de simulation à événements discrets d'un bloc opératoire
(salles, SSPI/réveil, personnel, maintenance), avec un module de coûts en
francs suisses pour arbitrer des décisions de dimensionnement (ajouter une
salle, des lits de réveil, ou renforcer une équipe).

Le moteur (`bloc_operatoire_sim.py`) illustre un phénomène contre-intuitif
central en planification de bloc : le **goulot d'aval**. Quand la SSPI manque
de lits, les salles d'opération restent bloquées — ajouter des lits de réveil
peut donc augmenter le débit plus qu'ajouter une salle.

## ⚠️ Données

Le fichier `donnees_hug_bloc.csv` contient des **données synthétiques**,
calibrées à partir d'ordres de grandeur publics (rapports d'activité,
littérature de planification de bloc). Ce ne sont **pas des données internes
réelles des HUG** — elles ne servent qu'à illustrer le modèle avec des chiffres
plausibles par spécialité.

## Utilisation

```bash
pip install -r requirements.txt
streamlit run app.py
```

L'application Streamlit (`app.py`) permet de régler salles, lits SSPI,
effectifs, demande, durées et coûts via des curseurs, et affiche en direct les
KPIs opérationnels et financiers, avec un comparatif "+1 salle" vs "+2 lits
SSPI".

D'autres scripts illustrent des aspects spécifiques en ligne de commande :
- `niveaux_demo.py` — empile les 4 niveaux de complexité du modèle.
- `demo_personnel.py` — dimensionnement et absentéisme du personnel.
- `couts_demo.py` — arbitrage salle/SSPI/personnel en CHF.
- `charger_donnees_hug.py` — simulation par spécialité depuis le CSV.
- `jouer.py` — version interactive en terminal (questions/réponses).

## Avertissement

Outil pédagogique et exploratoire — les valeurs par défaut (durées, coûts,
probabilités) sont des hypothèses raisonnables, pas des mesures validées. À
calibrer avec des données réelles avant tout usage opérationnel.
