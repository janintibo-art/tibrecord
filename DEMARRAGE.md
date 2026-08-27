# Tibrecord — démarrage du projet

**À lire en premier dans la nouvelle conversation.** Ce dossier contient
un projet qui compile et dont les tests passent. Il n'y a rien à écrire
de zéro : il faut le pousser, vérifier que la chaîne fonctionne, puis
construire dessus.

---

## Le projet

Une application Android et Windows pour **enregistrer au micro du
téléphone et travailler le son**. Développée **depuis un téléphone**
(Termux), compilée par GitHub Actions, publiée en release.

C'est le second projet de la même personne. Le premier, **MOC'TA BASS**,
prépare et transfère des samples vers une Korg volca sample. Celui-ci
fournira la matière première : capturer, découper, nettoyer, exporter.

Les deux sont indépendants, mais le moteur audio du premier a été repris
ici — il est éprouvé et sans aucune dépendance.

---

## Ce qui est déjà là

```
noyau/                logique métier, Python standard, AUCUNE dépendance
├── audio.py          moteur DSP repris de MOC'TA BASS, déjà testé
├── enregistrement.py capture micro via AudioRecord (Android)
├── batch.py          traitement par lot
└── __init__.py

onde.py               forme d'onde zoomable, jusqu'à l'échantillon
main.py               interface Kivy : ENREG. / EDIT. / TUTO
cli.py                interface console, sans dépendance
tests/                36 tests, tous verts
buildozer.spec        réglages de compilation éprouvés
.github/workflows/    APK Android + exe Windows + release sur tag
packaging/            spec PyInstaller
```

**36 tests passent** : `python -m unittest discover -s . -p "test_*.py"`

### Ce qui fonctionne déjà

- Enregistrement au micro, vu-mètre, minuteur au milliseconde
- Forme d'onde **zoomable jusqu'à ×100 000** — on voit les échantillons
  un par un, le compteur descend au dixième de milliseconde
- Sélection par deux poignées, affichage du temps **et** du numéro
  d'échantillon
- Rogner, normaliser, fondus, six presets de traitement, annuler sur 12
  étapes
- Écoute de la sélection
- Export WAV mono 16 bits 44,1 kHz
- Mouchard : en cas de plantage, trace en vert à l'écran et dans
  `tibrecord_crash.txt`, onglet fautif isolé

---

## Le point à vérifier en premier

**L'enregistrement Android n'a jamais été testé sur un appareil.**

Le module `noyau/enregistrement.py` utilise `AudioRecord`, l'interface
bas niveau d'Android, appelée depuis Python par jnius. Elle donne du PCM
16 bits brut — pas de MP3 ni de m4a à décoder, donc aucune dépendance
supplémentaire. C'est la bonne approche, mais elle n'a pas pu être
vérifiée faute d'appareil.

Ce qui est prévu si ça échoue :
- l'erreur exacte est conservée dans `Enregistreur.derniere_erreur` et
  affichée à l'écran
- hors Android, la capture est **muette** mais fonctionnelle : toute la
  logique reste testable sans micro

**Premier test à faire** : lancer l'application, appuyer sur
ENREGISTRER, parler, arrêter. Si le vu-mètre bouge, tout le reste suit.

---

## Réglages de compilation à ne pas casser

Chacun a coûté un build raté sur le projet précédent. Ils sont déjà dans
`buildozer.spec` et dans le workflow.

| Réglage | Valeur | Pourquoi |
|---|---|---|
| `p4a.branch` | `v2024.01.21` | master compile Python 3.14, incompatible Kivy 2.3 |
| position de `p4a.branch` | section `[app]` | en `[buildozer]` il est **ignoré en silence** |
| `cython` | `0.29.36` | va avec Python 3.11 |
| `android.api` | `33` | |
| `android.archs` | `arm64-v8a` | divise le temps de build par deux |
| titre | apostrophe **typographique** `’` | l'apostrophe droite casse gradle |
| build Windows | `KIVY_GL_BACKEND: mock` | pas de carte graphique sur le runner |
| `RECORD_AUDIO` | déclaré | sans lui, pas de micro |

Après tout changement de version d'outil : `gh cache delete --all`

---

## Démarrage, étape par étape

**1 — Créer le dépôt**
```
cd ~/projets && mkdir tibrecord && cd tibrecord && cp -r /sdcard/Download/tibrecord/. . && ls
```

**2 — Vérifier que tout tourne, avant même de pousser**
```
python -m unittest discover -s . -p "test_*.py" 2>&1 | tail -3 && python cli.py presets
```

**3 — Premier commit**
```
git init -b main && git add -A && git commit -m "Tibrecord 0.1.0 : enregistrement et edition"
```

**4 — Créer le dépôt distant et pousser**
```
gh repo create tibrecord --public --source=. --push
```

**5 — Suivre le build**
```
gh run list -L 2
```

Le premier build Android prend 30 à 40 minutes : le SDK, le NDK et
Python doivent être compilés. Les suivants durent 5 à 10 minutes grâce
au cache.

**6 — Publier quand c'est vert**
```
git tag v0.1.0 && git push --tags
```

Attendre que le build de la branche soit **vert** avant de poser le tag :
deux builds simultanés se disputent le cache.

---

## Méthode de travail à conserver

Ces règles viennent du projet précédent et ont évité beaucoup de perte de
temps.

**Livraison de code**
- Livrer **uniquement les fichiers modifiés**, en zip.
- **Ne jamais écraser** `buildozer.spec` ni le workflow.
- Dire de quel patch précédent la livraison dépend.

**Commandes Termux**
- Une commande par bloc, numérotée. Un bloc = une copie sur téléphone.
- **Aucun espace réservé** : pas de `ID`, pas de `ton_fichier.wav`.
- Une commande de vérification après chaque étape.

**Tests**
- Annoncer le nombre de tests à chaque livraison. Si le compte diffère
  chez la personne, **un patch manque**.
- Tester le résultat visé, pas l'implémentation.

**Diagnostic**
- Ne rien corriger avant d'avoir la ligne d'erreur exacte.
- L'interface web de GitHub tronque les logs : `gh run view ID
  --log-failed`.

---

## Feuille de route proposée

Par ordre d'utilité, à discuter.

**1. Vérifier le micro sur appareil.** Rien d'autre ne compte tant que ce
point n'est pas tranché.

**2. Bibliothèque de sons.** Une réserve nommée et cherchable, comme dans
MOC'TA BASS : ranger les prises, les retrouver, les rappeler.

**3. Découpe automatique.** Une longue prise contient dix frappes : les
détecter et les séparer en dix fichiers d'un coup. C'est le gain de temps
le plus net quand on enregistre des percussions.

**4. Générateur de sons.** Kick, caisse claire, charley, clap, basse, par
synthèse. Utile dans le bus, quand on n'a rien à enregistrer et qu'on ne
va pas taper sur une table en public.

**5. Effets.** Réverbération, délai, filtre balayé, bitcrush.
Faisables en Python pur, sur des sons courts.

**6. Export vers MOC'TA BASS.** Un kit `.zip` directement lisible par
l'autre application.

---

## Ce qu'il faut savoir sur l'auteur

Développe **entièrement depuis un téléphone**, dans Termux, sans
ordinateur. Les commandes doivent donc être copiables d'un bloc, sans
rien à remplacer à la main.

Ne connaît pas le jargon technique et n'a pas besoin de l'apprendre. Les
explications gagnent à être en français simple, avec le pourquoi avant le
comment.

Repère très bien les incohérences d'interface et les signale
précisément — ses retours sont fiables et méritent d'être suivis à la
lettre.
