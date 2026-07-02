# PMD - Statuts de box et rendu locker

Date: 2026-03-23

## 1. Objectif

Ce document decrit comment la vue locker PMD reconstitue l'etat des boxes et applique un rendu visuel
(couleurs, motifs, icones) pour afficher un locker similaire a:

- `/front-pmd/parcel-lockers/detail/{deviceCode}`

L'objectif est de permettre a un autre projet de:

1. recuperer les bons statuts depuis l'API PMD,
2. reconstruire l'etat des boxes,
3. appliquer le meme type de rendu que le front PMD.

## 2. Vue d'ensemble

La vue locker PMD combine plusieurs sources:

1. `GET /api/assets/devices/{deviceCode}`
2. `GET /api/tracking-device/parcel-lockers/{deviceCode}`
3. `GET /api/parcel_events_in_devices/{deviceCode}/boxView`
4. `GET /api/tracking-parcel/parcels?fterms_events.locker.deviceCode={deviceCode}`

Base URL front:

- `API_BASE = ${ROUTE_PUBLIC}/api`

Role de chaque endpoint:

| Endpoint | Role principal |
|---|---|
| `GET /api/assets/devices/{deviceCode}` | description physique du device, arbre des modules/colonnes/boxes, etat technique courant de chaque box |
| `GET /api/tracking-device/parcel-lockers/{deviceCode}` | donnees de tracking locker et attributs metier complementaires |
| `GET /api/parcel_events_in_devices/{deviceCode}/boxView` | derniers evenements colis par box |
| `GET /api/tracking-parcel/parcels?...` | historique tracking colis, utilise notamment pour corriger certains cas `COLADM` |

## 3. Donnees exploitees pour une box

### 3.1 Source device

Depuis `GET /api/assets/devices/{deviceCode}`, le front parcourt l'arbre du device et, pour chaque box, projette les etats dans une structure simplifiee:

- `box.state.door`
- `box.state.cleanliness`
- `box.state.hard`
- `box.state.securityBreach`
- eventuellement `box.state.printer...` pour les boxes printer

Les valeurs brutes surveillees pour le rendu locker sont:

| Champ | Valeurs utiles |
|---|---|
| `state.door.value` | `OPENED` |
| `state.cleanliness.value` | `SOILED` |
| `state.hard.value` | `DAMAGED` |
| `state.securityBreach.value` | `BURGLARY`, `BOXFULLBURGLARY`, `DOORBLOCKEDBURGLARY`, `BOXFULLDOORBLOCKEDBURGLARY`, `DOORBLOCKED`, `BOXFULLDOORBLOCKED`, `BOXFULL`, `BOXFULLBURGLARY`, ... |

Le front conserve aussi les timestamps associes pour afficher "depuis quand":

- `openedFrom`
- `dysfunctionalFrom`
- `soiledFrom`
- `burglaryFrom`
- `securityServiceFrom`
- `detectedFrom`

### 3.2 Source boxView

Depuis `GET /api/parcel_events_in_devices/{deviceCode}/boxView`, le front lit, pour chaque box:

- `boxPath`
- `parcels[]`
- `parcels[].status`
- `parcels[].parcelNumber`
- `parcels[].statusDate`

Ces statuts colis servent a determiner les couleurs colis dans la box.

### 3.3 Source tracking parcel

Depuis `GET /api/tracking-parcel/parcels?fterms_events.locker.deviceCode={deviceCode}`, le front retrouve l'historique complet d'un parcel.

Usage principal:

- verifier si le dernier statut non-admin doit etre remplace visuellement par `COLADM`.

## 4. Typologie complete des statuts affiches

Le front gere 10 categories principales dans la barre de statut et dans le rendu locker.

### 4.1 Statuts "colis" (couleurs)

| ID front | Origine PMD | Regle metier | Rendu |
|---|---|---|---|
| `loaded` | `LIVCFP` | colis livre dans la box | couleur verte `#3cc113` |
| `toBeUnloaded` | `RETCFM`, `LIVEXP`, `LIVBLK` | box a decharger / dropoff / expire / bloque | couleur bleue `#3399cc` |
| `markedPickedUp` | `COLADM` | marque comme retire par admin | couleur vert clair `#d6f9cb` |
| `reserved` | `RESVAL` | reservation validee | motif `pattern15` |

### 4.2 Statuts "box" (motifs / alertes)

| ID front | Origine PMD | Regle metier | Rendu |
|---|---|---|---|
| `open` | `state.door.value = OPENED` | porte ouverte | couleur orange `#ffa429` |
| `burglary` | `state.securityBreach.value in {BURGLARY, BOXFULLBURGLARY, DOORBLOCKEDBURGLARY, BOXFULLDOORBLOCKEDBURGLARY}` | violation / effraction | couleur rouge `#ff0303` |
| `dysfunctional` | `state.hard.value = DAMAGED` | box endommagee | motif `pattern11` |
| `soiled` | `state.cleanliness.value = SOILED` | box sale | motif `pattern12` |
| `securityService` | `state.securityBreach.value in {DOORBLOCKED, BOXFULLDOORBLOCKED, DOORBLOCKEDBURGLARY, BOXFULLDOORBLOCKEDBURGLARY}` | porte bloquee / service securite | motif `pattern13` |
| `object_detected` | `state.securityBreach.value in {BOXFULL, BOXFULLDOORBLOCKED, BOXFULLBURGLARY, BOXFULLDOORBLOCKEDBURGLARY}` | objet detecte / box pleine | motif `pattern14` |

## 5. Table de correspondance API PMD -> rendu locker

| Signal PMD | Endpoint source | Champ source | Type de rendu | Valeur de rendu |
|---|---|---|---|---|
| `LIVCFP` | `/api/parcel_events_in_devices/{deviceCode}/boxView` | `parcels[].status` | couleur | vert `#3cc113` |
| `RETCFM` | `/api/parcel_events_in_devices/{deviceCode}/boxView` | `parcels[].status` | couleur | bleu `#3399cc` |
| `LIVEXP` | `/api/parcel_events_in_devices/{deviceCode}/boxView` | `parcels[].status` | couleur | bleu `#3399cc` |
| `LIVBLK` | `/api/parcel_events_in_devices/{deviceCode}/boxView` | `parcels[].status` | couleur | bleu `#3399cc` |
| `COLADM` | `/api/parcel_events_in_devices/{deviceCode}/boxView` ou correction via `/api/tracking-parcel/parcels` | `parcels[].status` / historique | couleur | vert clair `#d6f9cb` |
| `RESVAL` | `/api/parcel_events_in_devices/{deviceCode}/boxView` | `parcels[].status` | motif | `pattern15` |
| `OPENED` | `/api/assets/devices/{deviceCode}` | `state.door.value` | couleur | orange `#ffa429` |
| `DAMAGED` | `/api/assets/devices/{deviceCode}` | `state.hard.value` | motif | `pattern11` |
| `SOILED` | `/api/assets/devices/{deviceCode}` | `state.cleanliness.value` | motif | `pattern12` |
| `DOORBLOCKED*` | `/api/assets/devices/{deviceCode}` | `state.securityBreach.value` | motif | `pattern13` |
| `BOXFULL*` | `/api/assets/devices/{deviceCode}` | `state.securityBreach.value` | motif | `pattern14` |
| `BURGLARY*` | `/api/assets/devices/{deviceCode}` | `state.securityBreach.value` | couleur | rouge `#ff0303` |

Notes:

- `DOORBLOCKED*` couvre aussi les variantes combinees avec `BOXFULL` et/ou `BURGLARY`.
- `BOXFULL*` couvre aussi les variantes combinees avec `DOORBLOCKED` et/ou `BURGLARY`.
- `BURGLARY*` couvre aussi les variantes combinees avec `BOXFULL` et/ou `DOORBLOCKED`.

## 6. Regles de priorite appliquees par PMD front

### 6.1 Priorite des couleurs colis

Quand plusieurs statuts colis existent sur une meme box, le front privilegie:

1. `toBeUnloaded`
2. `markedPickedUp`
3. `loaded`

Effets concrets:

- si une box a du `COLADM`, on retire le rendu `loaded` si necessaire,
- si une box a du `toBeUnloaded`, on retire le rendu `loaded` et `markedPickedUp`.

### 6.2 Superposition couleur + motif

Le rendu final d'une box peut combiner:

1. une couleur de fond ou une combinaison de couleurs liees aux parcels,
2. un motif lie a l'etat technique de la box.

Exemples:

- box chargee et sale: fond vert + motif soiled,
- box en dropoff et object detected: fond bleu + motif triangles rouges,
- box reservee: motif reserve,
- box burglary: couleur rouge, qui prend le dessus sur l'etat "open".

### 6.3 Cas particuliers de priorite technique

Le front applique aussi quelques regles implicites:

1. `burglary` remplace visuellement `open` si les deux existent.
2. `securityService` remplace le motif `dysfunctional` dans la pile de motifs quand les deux sont presentes.
3. `object_detected` est calcule a partir des valeurs `BOXFULL*`.

## 7. Algo minimal pour reproduire le rendu dans un autre projet

### 7.1 Etape 1 - Charger les sources

Recuperer en parallele:

1. `GET /api/assets/devices/{deviceCode}`
2. `GET /api/tracking-device/parcel-lockers/{deviceCode}`
3. `GET /api/parcel_events_in_devices/{deviceCode}/boxView`
4. `GET /api/tracking-parcel/parcels?fterms_events.locker.deviceCode={deviceCode}`

### 7.2 Etape 2 - Construire l'index des boxes

Pour chaque box du device, construire un objet de type:

```json
{
  "alias": "52-CL",
  "boxNumber": 52,
  "size": "CL",
  "state": {
    "door": "OPENED",
    "cleanliness": "SOILED",
    "hard": "DAMAGED",
    "securityBreach": "BOXFULLBURGLARY"
  },
  "timestamps": {
    "openedFrom": "...",
    "soiledFrom": "...",
    "dysfunctionalFrom": "...",
    "burglaryFrom": "...",
    "securityServiceFrom": "...",
    "detectedFrom": "..."
  },
  "parcels": [
    { "state": "LIVCFP" },
    { "state": "COLADM" }
  ]
}
```

### 7.3 Etape 3 - Determiner les couleurs colis

Pseudo-regles:

```text
si RESVAL -> ajouter motif reserve
sinon si COLADM -> couleur markedPickedUp
sinon si LIVCFP -> couleur loaded
si RETCFM ou LIVEXP ou LIVBLK -> couleur toBeUnloaded et retirer loaded / markedPickedUp
si door == OPENED -> ajouter couleur open
si securityBreach in BURGLARY* -> ajouter couleur burglary et retirer open
```

### 7.4 Etape 4 - Determiner les motifs box

Pseudo-regles:

```text
si cleanliness == SOILED -> pattern12
si hard == DAMAGED -> pattern11
si securityBreach in DOORBLOCKED* -> pattern13 et retirer pattern11 si besoin
si securityBreach in BOXFULL* -> pattern14
si RESVAL -> pattern15
```

## 8. Interpretation conseillee pour un autre projet

Si le but est uniquement de reproduire le rendu locker, la source minimale utile est:

1. `/api/assets/devices/{deviceCode}` pour les etats techniques,
2. `/api/parcel_events_in_devices/{deviceCode}/boxView` pour les statuts colis.

Le tracking parcel complet est seulement necessaire si vous voulez reproduire exactement la logique de correction des statuts `COLADM` et certains details de table/tooltip.

## 9. Statuts a exposer dans une API interne de facade

Pour simplifier l'exploitation dans un autre projet, une facade peut exposer pour chaque box:

```json
{
  "alias": "52-CL",
  "display": {
    "parcelStatus": ["toBeUnloaded"],
    "boxStatus": ["object_detected", "burglary"],
    "colors": ["#3399cc", "#ff0303"],
    "patterns": [14],
    "timestamps": {
      "object_detected": "2026-03-20T10:00:00.000Z",
      "burglary": "2026-03-20T10:00:00.000Z"
    }
  }
}
```

Cela permet de decoupler l'autre projet de la logique React PMD tout en gardant un rendu equivalent.

## 10. Point d'attention important

Le statut `object_detected` correspond en pratique a une famille de valeurs `BOXFULL*` dans `state.securityBreach.value`.

Autrement dit:

- il n'existe pas forcement comme champ direct nomme `object_detected` dans l'API PMD,
- c'est un statut d'affichage derive par le front a partir de `securityBreach`.

C'est la meme logique pour:

- `burglary`
- `securityService`

qui sont eux aussi des regroupements front a partir de plusieurs valeurs PMD brutes.

## 11. References front utiles

- Route detail locker:
  - `pmd-front/front-pmd/app/containers/HomePage/actions/render-page-contents.js`
- Chargement et fusion des donnees:
  - `pmd-front/front-pmd/app/containers/parcelLockers/ParcelLockerDetail/actions/map-data-be-to-ui.js`
- Mapping couleurs et motifs:
  - `pmd-front/front-pmd/app/containers/parcelLockers/actions/mapping-status-box.js`
- Barre de statut:
  - `pmd-front/front-pmd/app/components/parcellocker/GeneralInformation/components/StatusBar/StatusBarWrapper.js`
- Rendu locker et patterns:
  - `pmd-front/front-pmd/app/components/LockerVisualize/constant.js`
