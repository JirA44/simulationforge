# SimulationForge V1.07

SimulationForge exécute côté serveur des simulations Monte Carlo simples, déterministes et auditables. Un modèle et ses hypothèses sont figés par version, puis un scénario versionné peut fixer certaines variables à l'intérieur de leurs bornes. Le client transmet uniquement l'identifiant du scénario, une seed explicite et un nombre d'itérations : il ne peut jamais fournir le résultat, le verdict ou les statistiques.

> **Avertissement permanent :** une simulation est une description conditionnelle fondée sur des hypothèses. Elle n'est ni une prédiction, ni une certification, ni une certitude, ni un conseil de décision.

## Nouveauté V1.07 : couverture explicite de l'espace des scénarios

V1.07 construit un dossier immuable à partir de 2 à 100 scénarios figés d'un même modèle. Le serveur vérifie les hashes du modèle et de chaque scénario, canonicalise la requête, puis ordonne les scénarios par date de création et identifiant. Le client fournit uniquement les `scenario_ids` : il ne peut transmettre ni couverture, ni lacune, ni qualification.

Pour chaque paramètre du modèle, le dossier mesure les valeurs explicitement surchargées, leur étendue relative aux bornes figées et la présence des deux limites. Les paramètres constants sont signalés séparément. Le résultat expose les paramètres manquants, partiellement couverts, entièrement couverts et le pire paramètre :

- `COMPLETE` : au moins trois scénarios et toutes les bornes des paramètres variables sont explicitement couvertes ;
- `PARTIAL` : au moins un paramètre variable est absent ou ne couvre pas ses deux bornes ;
- `INSUFFICIENT` : moins de trois scénarios, même si les deux bornes apparaissent ;
- `INCOMPATIBLE` : modèles ou hashes divergent.

Cette couverture décrit uniquement les points de stress explicitement persistés. Elle ne démontre ni une exploration exhaustive, ni une probabilité, ni une validité prédictive et ne déclenche aucune action.

## Nouveauté V1.06 : dérive des distributions entre scénarios

V1.06 construit un dossier immuable à partir de 2 à 100 runs associés à des scénarios distincts d'un même modèle figé. Le serveur impose une seed et un budget d'itérations communs, recharge chaque run, recalcule les distributions et vérifie les hashes avant d'ordonner les scénarios par date de création puis identifiant.

Chaque transition expose les écarts absolus et relatifs de `mean`, `p05` et `p95`, une direction descriptive (`UPWARD`, `DOWNWARD`, `MIXED` ou `STABLE`), la pire transition et les scénarios affectés. Le seuil de dérive est fixé à 5 % et le budget probant minimal à 1 000 itérations :

- `STABLE` : aucune transition ne dépasse 5 % ;
- `DRIFTING` : au moins une transition dépasse 5 % ;
- `INSUFFICIENT` : le budget commun est inférieur à 1 000 itérations ;
- `INCOMPATIBLE` : modèle, seed, budget, recalcul ou hash divergent.

Une hausse ou une baisse n'est pas jugée favorable par le système. Le dossier décrit seulement l'évolution des distributions sous les hypothèses fournies et ne déclenche aucune action.

## Nouveauté V1.05 : convergence selon le budget d'itérations

V1.05 construit un dossier immuable à partir de 3 à 50 runs du même scénario, du même modèle et de la même seed, mais avec des budgets d'itérations distincts. Le serveur recharge et recalcule chaque run, vérifie statistiques et hashes, puis choisit comme référence le budget le plus élevé.

Pour `mean`, `p05` et `p95`, chaque point expose l'écart absolu et l'écart relatif à la référence. Le dossier retient le pire point et utilise un seuil fixe de 2 %. La référence doit compter au moins 1 000 itérations :

- `CONVERGED` : trois budgets distincts ou plus, référence suffisante et aucun écart relatif supérieur à 2 % ;
- `UNSTABLE` : au moins un écart relatif dépasse 2 % ;
- `INSUFFICIENT` : la référence reste sous 1 000 itérations ou les budgets distincts sont insuffisants ;
- `INCOMPATIBLE` : scénario, modèle ou seed diffèrent, ou un recalcul/hash échoue.

La convergence décrit uniquement les métriques et budgets fournis. Elle ne valide ni le modèle, ni les hypothèses, ni une prédiction future.

## Nouveauté V1.04 : dossier d'incertitude et de robustesse

V1.04 construit un dossier immuable à partir de 2 à 100 `run_ids` déjà persistés. Les identifiants doivent appartenir exactement au même scénario et au même modèle figés. Le serveur recharge chaque run, recalcule sa distribution depuis la seed et le nombre d'itérations stockés, puis vérifie les statistiques ainsi que les hashes du modèle, du scénario et du résultat. Aucun résultat, verdict ou qualification fourni par le client n'est accepté.

Pour chacune des sept métriques (`minimum`, `maximum`, `mean`, `population_stddev`, `p05`, `median`, `p95`), le dossier fournit minimum, maximum, moyenne, P05, médiane, P95, largeur et largeur relative. La largeur relative est définie par `largeur / max(|moyenne de l'enveloppe|, 1)`. Le client peut uniquement fournir des limites déclaratives minimales/maximales; les violations sont calculées par le serveur.

Le `worst_run` est choisi déterministement : nombre de violations décroissant, puis P05 croissant, puis identifiant. Cette convention est descriptive et ne remplace pas un objectif métier. La stabilité indique aussi la direction commune des moyennes et la concordance paire à paire du classement par moyenne avec celui par médiane; une concordance d'au moins 80 % est `STABLE`, sinon `MIXED`, et les égalités non comparables donnent `NOT_APPLICABLE`.

Les qualifications sont appliquées dans cet ordre :

- `INCOMPATIBLE` si les runs divergent de scénario/modèle ou si un recalcul/hash échoue ;
- `INSUFFICIENT` avec seulement 2 runs — seuil statistique fixé à 3 ;
- `LIMIT_BREACH` si au moins une limite est violée ;
- `UNCERTAINTY_SENSITIVE` si la largeur relative de `mean`, `p05` ou `p95` dépasse 5 % ;
- `ROBUST` sinon.

Les `run_ids` et limites sont canonicalisés : changer leur ordre retourne le même snapshot. Le dossier ne déclenche aucune action automatique et ne constitue ni une prédiction ni une certification.

## Nouveauté V1.03 : surface d'interaction

V1.03 construit une surface reproductible entre deux paramètres distincts d'un scénario figé. Chaque axe accepte une grille explicite de 2 à 7 valeurs ou un triplet `start/stop/steps`; la surface est limitée à 49 cellules. Les deux paramètres, leurs bornes et leurs unités proviennent exclusivement du modèle : le client ne peut fournir ni cellule, ni métrique, ni qualification.

Le serveur utilise les mêmes tirages SplitMix64 pour toutes les cellules, puis recalcule la distribution complète de chacune. Il produit les effets principaux marginaux, l'étendue des moyennes, une pente par axe, le résidu de chaque cellule par rapport au modèle additif, le résidu maximal et la cellule de moyenne minimale (`worst_cell`, convention descriptive qui ne constitue pas un objectif métier).

Les seuils de qualification sont fixes et appliqués dans cet ordre :

- `INSUFFICIENT` sous 100 itérations ;
- `INTERACTIVE` si le résidu additif absolu maximal dépasse 5 % de `max(|moyenne générale|, 1)` ;
- `SENSITIVE` si l'étendue des moyennes dépasse 5 % de la même échelle ;
- `ADDITIVE` sinon.

Une qualification décrit uniquement la grille et les hypothèses testées. Elle ne prédit et ne certifie rien. Pour rendre une interaction réelle représentable, `outcome.interactions` accepte désormais des termes bilinéaires optionnels `{parameter_x, parameter_y, coefficient}`; les anciens modèles sans ce champ restent inchangés.

## Nouveauté V1.02 : sensibilité paramétrique

V1.02 mesure comment la distribution de sortie d'un scénario change lorsque l'une de ses variables autorisées parcourt une grille bornée. Le client transmet uniquement `scenario_id`, le nom du paramètre, une grille explicite de 2 à 21 valeurs — ou `start`, `stop`, `steps` — ainsi qu'une seed et un nombre d'itérations. Il ne peut transmettre ni résultat, ni métrique, ni qualification.

Le serveur vérifie que le paramètre existe, intervient dans la sortie et que tous les points restent dans les bornes du modèle figé. Il recalcule la distribution de référence et chaque distribution de grille avec les mêmes tirages déterministes (`splitmix64-linear-sensitivity-v1`). Le snapshot contient les deltas de moyenne/P05/P95, l'étendue relative des moyennes, la pente entre extrémités, l'élasticité lorsqu'elle est définie et la monotonie.

La qualification est uniquement descriptive :

- `INSUFFICIENT` sous 100 itérations ;
- `SENSITIVE` si l'étendue des moyennes dépasse 5 % de l'échelle de la moyenne de référence ;
- `STABLE` sinon.

Elle ne prédit rien et ne certifie ni le modèle, ni ses hypothèses, ni un résultat futur.

## Comparaison baseline/stress héritée de V1.01

V1.01 compare deux scénarios immuables rattachés exactement au même modèle figé. Le client fournit seulement les deux identifiants, une seed et un nombre d'itérations entre 1 et 10 000. Le serveur vérifie le modèle, les variables et leurs unités, puis recalcule les deux distributions avec des tirages communs déterministes (`splitmix64-linear-paired-v1`). Aucun résultat, delta ou verdict fourni par le client n'est accepté.

Le rapport immuable contient les statistiques baseline/stress, les deltas `mean`, `p05`, `p95`, ainsi que le downside. Ici, le downside est défini comme `max(0, moyenne - P05)`; le delta downside vaut `downside_stress - downside_baseline`.

La qualification est descriptive :

- `INSUFFICIENT` sous 100 itérations ;
- `FRAGILE` si au moins un delta de moyenne/P05/P95 baisse de plus de 5 % de l'échelle baseline, ou si le downside augmente de plus de 5 % ;
- `ROBUST` sinon.

Ces libellés comparent uniquement deux distributions sous leurs hypothèses. Ils ne certifient ni le modèle, ni une décision, ni un résultat futur.

## Capacités cumulatives V1.07

- modèles immuables avec hypothèses, distributions et fonction de sortie linéaire/bilinéaire versionnées ;
- distributions sans dépendance scientifique lourde : constante, uniforme et triangulaire ;
- paramètres strictement bornés entre -1 000 000 et 1 000 000, puis bornés à nouveau par variable lors des surcharges ;
- générateur pseudo-aléatoire SplitMix64 explicite et seed obligatoire ;
- statistiques calculées exclusivement par le serveur : minimum, maximum, moyenne, écart-type population, P05, médiane et P95 ;
- rejeu idempotent sur `(scenario_id, seed, iterations, algorithm_version)` ;
- empreintes SHA-256 canoniques pour les modèles, scénarios et résultats ;
- journal d'audit chaîné par hash et protégé contre la modification/suppression ;
- qualification conservatrice unique `DESCRIPTIVE_ONLY` et avertissement inclus dans `/health` et chaque résultat ;
- validation Pydantic stricte avec `extra="forbid"` ;
- comparaison baseline/stress reproductible avec tirages communs ;
- vérification stricte du même modèle, des mêmes variables et des mêmes unités ;
- rapports de comparaison idempotents et hashés sur `(baseline, stress, seed, iterations, algorithm_version)` ;
- qualifications prudentes `ROBUST`, `FRAGILE` et `INSUFFICIENT`, toujours accompagnées de l'avertissement permanent.
- analyse de sensibilité avec grille bornée, tirages communs, métriques calculées côté serveur et snapshot SHA-256 ;
- rejeu idempotent sur `(scenario_id, parameter, grid, seed, iterations, algorithm_version)` ;
- qualifications descriptives `STABLE`, `SENSITIVE` et `INSUFFICIENT`, sans prédiction ni certification.
- surfaces 2D bornées à 49 cellules, distributions recalculées avec tirages communs et effets principaux ;
- décomposition additive avec résidus d'interaction et qualification descriptive à seuils fixes ;
- rejeu idempotent sur le scénario, les deux paramètres, les deux grilles, la seed, les itérations et l'algorithme.
- dossiers d'incertitude fondés uniquement sur des runs persistés et recalculés ;
- enveloppes multi-runs, limites, violations, run défavorable et stabilité de direction/classement ;
- snapshots ordre-indépendants et qualifications prudentes à seuils fixes.
- dossiers de dérive entre scénarios avec ordre serveur, transitions, pire écart et scénarios affectés ;
- comparaison stricte sur même modèle, seed et budget, avec recalcul intégral et seuil fixe de 5 %.
- dossiers de couverture explicite des scénarios avec vérification des hashes, étendue par paramètre, bornes couvertes et pire lacune ;
- snapshots ordre-indépendants et qualifications prudentes `COMPLETE`, `PARTIAL`, `INSUFFICIENT` ou `INCOMPATIBLE`.

## Limites explicites

V1.07 ne calibre pas de modèle, ne récupère aucune donnée externe, ne valide pas les hypothèses et ne garantit aucune performance future. Elle ne produit aucune certification et n'agit jamais automatiquement. Un dossier `ROBUST`, `CONVERGED`, `STABLE` ou `COMPLETE` décrit seulement les références fournies et leurs seuils. Une sensibilité faible, un résidu additif faible ou une couverture explicite complète ne démontre pas une robustesse globale. SplitMix64 vise la reproductibilité, pas la cryptographie. La fonction de sortie est volontairement limitée à :

```text
sortie = intercept
       + somme(coefficient_variable × valeur_variable)
       + somme(coefficient_interaction × valeur_x × valeur_y)
```

## Démarrage sous Windows PowerShell

Guides complémentaires : [exemples d'utilisation](docs/USAGE_EXAMPLES.md) et [contribution](CONTRIBUTING.md).

```powershell
Set-Location .\simulationforge
.\scripts\Setup.ps1
.\scripts\Start.ps1
```

L'API écoute par défaut sur `http://127.0.0.1:8016` et sa documentation interactive est disponible sur `http://127.0.0.1:8016/docs`.

Pour changer de base SQLite :

```powershell
$env:SIMULATIONFORGE_DB = "D:\Data\simulationforge.db"
.\scripts\Start.ps1
```

## Exemple minimal

Créer un modèle :

```json
{
  "name": "demand_model",
  "version": "1.0.0",
  "summary": "Demande conditionnelle à un prix et à une tendance",
  "assumptions": ["La relation linéaire reste une approximation locale"],
  "variables": [
    {"name": "price", "distribution": "uniform", "low": 90, "high": 110, "unit": "EUR"},
    {"name": "trend", "distribution": "triangular", "low": -1, "mode": 0, "high": 2}
  ],
  "outcome": {
    "name": "demand",
    "unit": "units",
    "intercept": 1000,
    "coefficients": {"price": -4, "trend": 25},
    "interactions": []
  }
}
```

Créer ensuite un scénario avec le `model_id` retourné, puis exécuter :

```json
{"scenario_id": "<scenario_id>", "seed": 20260822, "iterations": 5000}
```

Deux appels identiques retournent le même identifiant et le même `result_hash`; le second indique `idempotent_replay: true`.

Comparer ensuite deux scénarios compatibles :

```json
{
  "baseline_scenario_id": "<baseline_id>",
  "stress_scenario_id": "<stress_id>",
  "seed": 20260822,
  "iterations": 5000
}
```

Deux requêtes identiques vers `/v1/comparisons` retournent le même rapport et le même `report_hash`.

Analyser ensuite la sensibilité du prix :

```json
{
  "scenario_id": "<scenario_id>",
  "parameter": "price",
  "start": 90,
  "stop": 110,
  "steps": 5,
  "seed": 20260822,
  "iterations": 5000
}
```

Une grille explicite, par exemple `"grid": [90, 95, 100, 105, 110]`, peut remplacer `start/stop/steps`. Deux requêtes résolvant la même grille retournent le même snapshot et le même `snapshot_hash`.

Construire une surface prix/tendance :

```json
{
  "scenario_id": "<scenario_id>",
  "parameter_x": "price",
  "parameter_y": "trend",
  "start_x": 90,
  "stop_x": 110,
  "steps_x": 5,
  "grid_y": [-1, 0, 1, 2],
  "seed": 20260822,
  "iterations": 5000
}
```

Deux requêtes résolvant les mêmes axes retournent le même `snapshot_hash`; la seconde porte `idempotent_replay: true`.

Créer un dossier à partir de runs persistés :

```json
{
  "run_ids": ["<run_id_1>", "<run_id_2>", "<run_id_3>"],
  "limits": [
    {"metric": "p05", "minimum_allowed": 500},
    {"metric": "population_stddev", "maximum_allowed": 50}
  ]
}
```

L'ordre des runs et des limites n'influence ni l'identifiant ni le `snapshot_hash`.

Contrôler la convergence entre trois budgets de calcul utilisant la même seed :

```json
{
  "run_ids": ["<run_100>", "<run_1000>", "<run_5000>"]
}
```

Le serveur ordonne les budgets et compare chaque métrique au run de référence ayant le plus d'itérations.

Suivre ensuite la dérive de scénarios compatibles :

```json
{
  "run_ids": ["<run_scenario_v1>", "<run_scenario_v2>", "<run_scenario_v3>"]
}
```

Les runs doivent partager le même modèle, la même seed et le même budget. L'ordre envoyé n'influence ni l'identifiant ni le `snapshot_hash`.

## Endpoints

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/health` | état, version et avertissement |
| GET | `/info` | identité, version et capacités |
| POST/GET | `/v1/models` | figer ou lister les modèles |
| GET | `/v1/models/{model_id}` | lire un modèle |
| POST/GET | `/v1/scenarios` | figer ou lister les scénarios |
| GET | `/v1/scenarios/{scenario_id}` | lire un scénario |
| POST/GET | `/v1/runs` | exécuter ou lister les simulations |
| GET | `/v1/runs/{run_id}` | lire un résultat |
| POST/GET | `/v1/comparisons` | calculer ou lister les comparaisons baseline/stress |
| GET | `/v1/comparisons/{comparison_id}` | lire un rapport immuable |
| POST/GET | `/v1/sensitivities` | calculer ou lister les sensibilités paramétriques |
| GET | `/v1/sensitivities/{analysis_id}` | lire un snapshot de sensibilité immuable |
| POST/GET | `/v1/interaction-surfaces` | calculer ou lister les surfaces d'interaction |
| GET | `/v1/interaction-surfaces/{surface_id}` | lire une surface immuable |
| POST/GET | `/v1/uncertainty-dossiers` | créer ou lister les dossiers d'incertitude |
| GET | `/v1/uncertainty-dossiers/{dossier_id}` | lire un dossier immuable |
| POST/GET | `/v1/convergence-dossiers` | créer ou lister les dossiers de convergence |
| GET | `/v1/convergence-dossiers/{dossier_id}` | lire un dossier de convergence immuable |
| POST/GET | `/v1/scenario-drift-dossiers` | créer ou lister les dossiers de dérive entre scénarios |
| GET | `/v1/scenario-drift-dossiers/{dossier_id}` | lire un dossier de dérive immuable |
| GET | `/v1/audit-events` | lire le journal append-only |

Le contrat statique se trouve dans `packages/contracts/openapi.yaml`. Le schéma PostgreSQL de référence se trouve dans `packages/database/schema.sql`; l'application V1.07 fonctionne directement avec SQLite.

## Tests

```powershell
.\scripts\Test.ps1
```

Le script exécute Pytest, `compileall` et valide la cohérence du contrat OpenAPI statique et runtime.
