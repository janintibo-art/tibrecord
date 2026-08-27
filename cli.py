#!/usr/bin/env python3
"""
Tibrecord en ligne de commande. Aucune dependance.

    python cli.py info son.wav
    python cli.py traiter dossier/ -o sortie/ -p punch
    python cli.py decouper son.wav -o bout.wav --debut 200 --fin 800
    python cli.py presets
"""

import argparse
import os
import sys

from noyau import __version__, audio, batch


def cmd_info(a):
    cibles = []
    for e in a.entree:
        cibles.extend(batch.list_wavs(e))
    if not cibles:
        print("Aucun WAV trouve.")
        return 1
    for p in cibles:
        try:
            s = audio.read_wav(p)
            i = s.info()
            print("%-30s %7.0f ms  crete %6.1f  RMS %6.1f  LUFS %6.1f" % (
                os.path.basename(p)[:30], i["duree_ms"], i["peak_db"],
                i["rms_db"], audio.loudness_lufs(s)))
        except Exception as e:  # noqa: BLE001
            print("%-30s ERREUR : %s" % (os.path.basename(p)[:30], e))
    return 0


def cmd_presets(_a):
    for nom, cfg in audio.PRESETS.items():
        print("%-8s %s" % (nom, cfg["desc"]))
    return 0


def cmd_traiter(a):
    src = a.entree
    if os.path.isfile(src):
        out = a.sortie or os.path.splitext(src)[0] + "_traite.wav"
        s = audio.read_wav(src)
        s, rap = audio.process(s, a.preset, a.gain)
        audio.write_wav(out, s)
        print("%s -> %s  (%+.1f dB)" % (os.path.basename(src), out,
                                        rap["gain_db"]))
        return 0

    dst = a.sortie or os.path.join(src.rstrip("/\\"), "traite")

    def prog(i, n, rap):
        print("[%d/%d] %s" % (i, n, rap["fichier"]))

    raps = batch.process_folder(src, dst, a.preset, a.gain, prog)
    print()
    print(batch.resume(raps))
    return 0


def cmd_decouper(a):
    s = audio.read_wav(a.entree)
    r = s.rate
    i0 = int((a.debut or 0) * r / 1000)
    i1 = int((a.fin if a.fin is not None else s.duration_ms) * r / 1000)
    s.data = s.data[max(0, i0):min(len(s.data), i1)]
    out = a.sortie or os.path.splitext(a.entree)[0] + "_coupe.wav"
    audio.write_wav(out, s)
    print("%s : %.0f ms -> %s" % (os.path.basename(a.entree),
                                  s.duration_ms, out))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="tibrecord", description="Traitement de samples")
    ap.add_argument("--version", action="version",
                    version="Tibrecord " + __version__)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("info", help="afficher les niveaux")
    p.add_argument("entree", nargs="+")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("presets", help="lister les presets")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("traiter", help="traiter un fichier ou un dossier")
    p.add_argument("entree")
    p.add_argument("-o", "--sortie")
    p.add_argument("-p", "--preset", default="punch",
                   choices=sorted(audio.PRESETS))
    p.add_argument("-g", "--gain", type=float, default=0.0)
    p.set_defaults(func=cmd_traiter)

    p = sub.add_parser("decouper", help="extraire un morceau")
    p.add_argument("entree")
    p.add_argument("-o", "--sortie")
    p.add_argument("--debut", type=float, help="en ms")
    p.add_argument("--fin", type=float, help="en ms")
    p.set_defaults(func=cmd_decouper)

    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
