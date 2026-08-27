# Utilisations de SimulationForge

## Pour quelles utilisations ?

- rejouer une simulation Monte Carlo à seed explicite ;
- comparer un scénario de référence à un scénario de stress ;
- mesurer la sensibilité d'une sortie à un paramètre ;
- explorer une surface d'interaction entre deux paramètres ;
- agréger plusieurs runs dans une enveloppe d'incertitude et contrôler des limites déclarées.
- suivre la dérive de moyenne, P05 et P95 entre plusieurs versions de scénarios.
- mesurer la couverture explicite des bornes paramétriques par une collection de scénarios figés.

## Exemple

Un modèle de demande fait varier prix et tendance dans des bornes versionnées. L'équipe exécute plusieurs seeds, crée un dossier d'incertitude, puis inspecte le P05 et la largeur relative. `ROBUST` signifie uniquement que les runs fournis respectent les seuils fixes ; le modèle, ses hypothèses et le futur ne sont pas certifiés.

## Convergence d'un budget de calcul

Exécutez le même scénario avec la même seed et plusieurs budgets, par exemple 100, 1 000 et 5 000 itérations. Envoyez leurs identifiants à `POST /v1/convergence-dossiers`. Le serveur choisit le budget le plus élevé comme référence et calcule les écarts relatifs de moyenne, P05 et P95.

`CONVERGED` signifie que ces trois métriques restent dans le seuil fixe de 2 % pour les runs fournis. Cela ne prouve pas que le modèle est juste ni que d'autres seeds ou hypothèses convergeront.

## Dérive entre scénarios

Créez plusieurs scénarios versionnés du même modèle, puis exécutez chacun avec la même seed et le même budget d'au moins 1 000 itérations. Envoyez les identifiants des runs à `POST /v1/scenario-drift-dossiers`.

Le serveur les ordonne chronologiquement, recalcule les distributions et mesure chaque transition. `STABLE` signifie seulement qu'aucun écart relatif de moyenne, P05 ou P95 ne dépasse 5 % dans cette série. `DRIFTING` localise les transitions concernées, sans dire si la hausse ou la baisse est souhaitable et sans déclencher d'action.

## Couverture explicite des scénarios

Créez au moins trois scénarios du même modèle en fixant explicitement des points de stress, puis transmettez leurs identifiants à `POST /v1/scenario-coverage-dossiers`. Le serveur vérifie les hashes et mesure, pour chaque paramètre, si les valeurs persistées atteignent les deux bornes du modèle.

```json
{
  "scenario_ids": ["<scenario_bas>", "<scenario_central>", "<scenario_haut>"]
}
```

`COMPLETE` signifie uniquement que les scénarios fournis couvrent explicitement les deux bornes de chaque paramètre variable. Cela ne prouve ni une exploration exhaustive de l'espace, ni la validité du modèle, ni une probabilité future.
