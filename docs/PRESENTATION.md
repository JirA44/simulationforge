# Simulationforge — Présentation complète

## Présentation
simulationforge est un registre immuable, hashé (SHA-256), auditable et rejouable.

## À quoi ça sert ? (problèmes réglés)
- **Scénario extrême oublié** → résolu par un dossier déterministe, ordre-indépendant
- **Borne non justifiée** → résolu par un dossier déterministe, ordre-indépendant
- **Stress test qui ne couvre pas l'intervalle annoncé** → résolu par un dossier déterministe, ordre-indépendant

## Cas d'utilisation concrets
- Finance: prouver que le stress test couvre [-40%, +60%] sur 100 scénarios
- Jumeau numérique usine: borner la panne
- Climat: dossier de couverture de scénarios RCP

## Exemples d'utilisation (API)
```bash
curl -X POST http://localhost:8000/v1/scenario-coverage-dossiers -d '{"simulation_ids": [...] }'
# → { "qualification": "COMPLETE|GAPPED|INSUFFICIENT|INCOMPATIBLE", "coverage_ratio": 0.94, ... }
```

## À quoi ça pourrait servir (futur / possibilités)
- Risk management bancaire
- War-gaming militaire
- Assurance: tarification par dossier de scénarios

## Pour qui ?
Devs, auditeurs, ops, chercheurs — qui ont besoin d'une preuve opposable, pas d'un verdict déclaratif.

## Problèmes réglés (détaillés)
- **Simulationforge** → - Preuve / dossier / trace non opposable → résolu par dossier immuable et hash SHA-256
- **Simulationforge** → - Verdict déclaratif sans justification → le dossier expose obligations, fournisseurs et ratios
- **Simulationforge** → - Chaînage caché ou lacune invisible → serveur recharge et recalcule indépendamment du client
- **Simulationforge** → - Tiers qui ne peut pas relancer → le dossier est public et rejouable sans clé client

## Exemples d'utilisation (scénarios réels)
- **Finance stress test [-40%,+60%]** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **Jumeau numérique usine (borne panne)** → le dossier sert de preuve technique (pas d'autorité déclarative)
- **Climat : scénarios RCP couverts** → le dossier sert de preuve technique (pas d'autorité déclarative)


