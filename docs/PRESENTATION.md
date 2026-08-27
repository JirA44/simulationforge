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