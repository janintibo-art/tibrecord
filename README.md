# Tibrecord

Enregistrer au micro du téléphone et travailler le son. Android et
Windows, développé depuis un téléphone.

## Ce que ça fait

- **Enregistrement** au micro, vu-mètre, minuteur au milliseconde
- **Forme d'onde zoomable** jusqu'à voir les échantillons un par un
- **Découpe** précise, avec temps et numéro d'échantillon affichés
- **Traitement** : six presets, normalisation, fondus
- **Export** WAV mono 16 bits 44,1 kHz

## Installation

**Android** : télécharger le `.apk` dans les releases et l'installer.

**Windows** : télécharger le `.zip`, décompresser, lancer l'exécutable.

## En ligne de commande

Aucune dépendance, fonctionne dans Termux tel quel.

```bash
python cli.py info son.wav
python cli.py presets
python cli.py traiter dossier/ -o sortie/ -p punch
python cli.py decouper son.wav --debut 200 --fin 800
```

## Développement

```bash
python -m unittest discover -s . -p "test_*.py"
```

Le dossier `noyau/` ne dépend de rien : il tourne dans Termux tel quel.
Kivy sert uniquement à l'affichage.

## Licence

MIT
