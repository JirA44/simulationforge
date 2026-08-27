# Changelog

## V1.07 — 1.0.7

- ajout des dossiers de couverture explicite sur 2 à 100 scénarios d'un même modèle figé ;
- vérification des hashes, canonicalisation de la requête et ordre chronologique côté serveur ;
- mesure par paramètre des valeurs surchargées, de l'étendue relative et de la couverture des deux bornes ;
- repérage des paramètres manquants, partiels, complets et du pire paramètre ;
- qualifications `COMPLETE`, `PARTIAL`, `INSUFFICIENT` et `INCOMPATIBLE`, sans validation prédictive ;
- snapshots immuables, idempotents, hashés et audités ;
- API, SQLite, PostgreSQL, OpenAPI, documentation, packaging et tests cumulatifs mis à jour.

## V1.06 — 1.0.6

- ajout des dossiers de dérive de distributions sur 2 à 100 runs de scénarios distincts d'un même modèle ;
- ordre chronologique déterminé côté serveur, recalcul strict des distributions et vérification des hashes ;
- transitions sur moyenne, P05 et P95, directions descriptives, pire transition et scénarios affectés ;
- qualifications `STABLE`, `DRIFTING`, `INSUFFICIENT` et `INCOMPATIBLE` avec seuil fixe de 5 % et budget minimal de 1 000 itérations ;
- snapshots ordre-indépendants, immuables, idempotents, hashés et audités ;
- API, SQLite, PostgreSQL, OpenAPI, documentation, packaging et tests cumulatifs mis à jour.

## V1.05 — 1.0.5

- ajout des dossiers de convergence sur 3 à 50 runs persistés partageant scénario, modèle et seed ;
- recalcul des runs, vérification des hashes et comparaison de `mean`, `p05` et `p95` au plus grand budget ;
- qualifications serveur `CONVERGED`, `UNSTABLE`, `INSUFFICIENT` et `INCOMPATIBLE` avec seuil fixe de 2 % et référence minimale de 1 000 itérations ;
- snapshots ordre-indépendants, immuables, idempotents, hashés et audités ;
- API, SQLite, PostgreSQL, OpenAPI, documentation et tests cumulatifs mis à jour.

## V1.04 — 1.0.4

- ajout des dossiers d'enveloppe d'incertitude fondés exclusivement sur 2 à 100 `run_ids` persistés ;
- rechargement et recalcul de chaque run, puis vérification des statistiques et des hashes modèle, scénario et résultat ;
- agrégation des sept métriques de simulation en enveloppes avec minimum, maximum, moyenne, P05, médiane, P95, largeur et largeur relative ;
- limites optionnelles déclaratives, violations calculées côté serveur et sélection déterministe du run le plus défavorable ;
- analyse de direction des moyennes et de concordance des classements moyenne/médiane ;
- qualifications `ROBUST`, `UNCERTAINTY_SENSITIVE`, `LIMIT_BREACH`, `INSUFFICIENT` et `INCOMPATIBLE` selon des seuils fixes ;
- snapshots ordre-indépendants, immuables, idempotents, hashés et audités ;
- nouveaux endpoints `/v1/uncertainty-dossiers` et `/v1/uncertainty-dossiers/{dossier_id}` ;
- version interne portée à 1.0.4 sans action automatique ni retrait des capacités précédentes.

## V1.03 — 1.0.3

- ajout des surfaces d'interaction reproductibles entre deux paramètres distincts ;
- grilles explicites ou générées, de 2 à 7 valeurs par axe et 49 cellules au maximum ;
- tirages déterministes communs pour toutes les cellules ;
- distributions par cellule, effets principaux, étendue, pentes par axe, résidus additifs et cellule de moyenne minimale ;
- termes d'interaction optionnels et rétrocompatibles dans les modèles de sortie ;
- qualifications descriptives `ADDITIVE`, `INTERACTIVE`, `SENSITIVE` et `INSUFFICIENT` selon des seuils fixes ;
- snapshots immuables, idempotents, hashés et audités ;
- nouveaux endpoints `/v1/interaction-surfaces` et `/v1/interaction-surfaces/{surface_id}` ;
- version interne et métadonnées portées à 1.0.3 sans retrait des capacités précédentes.

## V1.02 — 1.0.2

- ajout de l'analyse de sensibilité paramétrique reproductible d'un scénario ;
- grilles explicites ou générées par `start/stop/steps`, de 2 à 21 points et bornées par la variable figée ;
- mêmes tirages déterministes pour la distribution de référence et chaque point ;
- calcul côté serveur des distributions, deltas, étendue, pente, élasticité et monotonie ;
- qualifications descriptives `STABLE`, `SENSITIVE` et `INSUFFICIENT` ;
- snapshots immuables, idempotents, hashés et inscrits dans l'audit append-only ;
- nouveaux endpoints `/v1/sensitivities` et `/v1/sensitivities/{analysis_id}` ;
- ajout de `/info` et alignement complet à la version interne 1.0.2 ;
- aucune fonction V1.00 ou V1.01 retirée.

## V1.01 — 1.0.1

- ajout des comparaisons baseline/stress recalculées côté serveur ;
- utilisation de tirages communs déterministes pour les deux distributions ;
- calcul des deltas moyenne, P05, P95 et downside ;
- qualifications descriptives `ROBUST`, `FRAGILE` et `INSUFFICIENT` ;
- vérification du même modèle figé, des variables et des unités ;
- rapports immuables, idempotents, hashés et inscrits dans l'audit append-only ;
- nouveaux endpoints `/v1/comparisons` et `/v1/comparisons/{comparison_id}` ;
- version interne portée à 1.0.1 sans retrait des capacités V1.00.

## V1.00 — 1.0.0

- modèles et scénarios versionnés immuables ;
- simulations Monte Carlo déterministes côté serveur ;
- résultats reproductibles, idempotents et auditables.
