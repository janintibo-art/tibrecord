"""
Enregistrement au micro.

Sur Android, on passe par AudioRecord, l'interface bas niveau du systeme.
Elle donne du PCM 16 bits brut, directement exploitable : pas de MP3 ni
de m4a a decoder, ce qui evite toute dependance supplementaire.

Sur ordinateur, il n'y a pas de capture : la classe se comporte comme un
enregistreur muet, ce qui permet de developper et de tester la logique
sans micro.

ATTENTION : le chemin Android n'a pas pu etre teste au moment d'ecrire ce
module. Si l'enregistrement echoue, l'erreur exacte est conservee dans
`derniere_erreur` et affichee par l'application.
"""

import math
import os
import struct
import threading
import time

from . import audio

TAUX_DEFAUT = 44100
TAUX_POSSIBLES = (44100, 48000, 32000, 22050, 16000)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ


class Enregistreur:
    """Capture le micro dans un tampon, en tache de fond.

    Utilisation :
        e = Enregistreur()
        e.demarrer()
        ...
        sample = e.arreter()
    """

    def __init__(self, taux=TAUX_DEFAUT, source="micro"):
        self.taux = taux
        self.source = source
        self.morceaux = []          # blocs de flottants -1..1
        self.en_cours = False
        self.demarre_a = None
        self.derniere_erreur = None
        self.crete_courante = 0.0
        self.rms_courant = 0.0
        self._fil = None
        self._stop = threading.Event()
        self._verrou = threading.Lock()

    # ------------------------------------------------------------ etat
    @property
    def duree_s(self):
        n = sum(len(m) for m in self.morceaux)
        return n / float(self.taux) if self.taux else 0.0

    def niveau_db(self):
        return audio.lin_to_db(self.crete_courante)

    def instantane(self, n=512):
        """Copie les derniers echantillons pour le monitoring visuel.

        Cette lecture est volontairement sans effet sur la capture : elle
        ne retire rien du tampon et ne change pas le moteur audio.
        """
        n = max(1, int(n))
        with self._verrou:
            if not self.morceaux:
                return []
            out = []
            for bloc in reversed(self.morceaux):
                besoin = n - len(out)
                if besoin <= 0:
                    break
                if len(bloc) <= besoin:
                    out[0:0] = bloc
                else:
                    out[0:0] = bloc[-besoin:]
                    break
            return out[-n:]

    def disponible(self):
        """Le micro est-il utilisable sur cet appareil ?"""
        if not IS_ANDROID:
            return False
        try:
            from jnius import autoclass  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------ capture
    def demarrer(self):
        if self.en_cours:
            return False
        self.morceaux = []
        self.derniere_erreur = None
        self._stop.clear()
        self.en_cours = True
        self.demarre_a = time.time()
        cible = self._boucle_android if IS_ANDROID else self._boucle_muette
        self._fil = threading.Thread(target=cible, daemon=True)
        self._fil.start()
        return True

    def arreter(self):
        """Arrete et renvoie le Sample capture, ou None si rien."""
        if not self.en_cours:
            return None
        self._stop.set()
        self.en_cours = False
        if self._fil is not None:
            self._fil.join(timeout=2.0)
        with self._verrou:
            data = [v for bloc in self.morceaux for v in bloc]
        if not data:
            return None
        s = audio.Sample(data, self.taux, "enregistrement")
        if self.taux != audio.TARGET_RATE:
            s.data = audio.resample_linear(s.data, self.taux,
                                           audio.TARGET_RATE)
            s.rate = audio.TARGET_RATE
        return s

    def _ajouter(self, bloc):
        if not bloc:
            return
        with self._verrou:
            self.morceaux.append(bloc)
        crete = max(abs(v) for v in bloc)
        somme = 0.0
        for v in bloc:
            somme += v * v
        self.crete_courante = crete
        self.rms_courant = math.sqrt(somme / len(bloc))

    # ------------------------------------------------------------ Android
    def _boucle_android(self):
        """Lit le micro par blocs jusqu'a l'arret."""
        enregistreur = None
        try:
            from jnius import autoclass

            AudioRecord = autoclass("android.media.AudioRecord")
            AudioFormat = autoclass("android.media.AudioFormat")
            Source = autoclass("android.media.MediaRecorder$AudioSource")

            source = getattr(Source, "MIC")
            if self.source == "camera":
                source = getattr(Source, "CAMCORDER", source)
            elif self.source == "brut":
                source = getattr(Source, "UNPROCESSED", source)

            mono = AudioFormat.CHANNEL_IN_MONO
            pcm16 = AudioFormat.ENCODING_PCM_16BIT
            mini = AudioRecord.getMinBufferSize(self.taux, mono, pcm16)
            if mini <= 0:
                raise RuntimeError(
                    "taux %d Hz refuse par l'appareil" % self.taux)
            taille = max(mini * 2, self.taux // 5 * 2)

            enregistreur = AudioRecord(source, self.taux, mono, pcm16, taille)
            if enregistreur.getState() != AudioRecord.STATE_INITIALIZED:
                raise RuntimeError(
                    "micro indisponible : autorisation refusee ou "
                    "deja utilise par une autre application")

            enregistreur.startRecording()
            tampon = bytearray(taille)
            while not self._stop.is_set():
                lus = enregistreur.read(tampon, 0, taille)
                if lus is None or lus <= 0:
                    time.sleep(0.01)
                    continue
                n = lus // 2
                vals = struct.unpack("<%dh" % n, bytes(tampon[:n * 2]))
                self._ajouter([v / 32768.0 for v in vals])
        except Exception as e:  # noqa: BLE001
            self.derniere_erreur = "%s : %s" % (type(e).__name__, e)
            self.en_cours = False
        finally:
            try:
                if enregistreur is not None:
                    enregistreur.stop()
                    enregistreur.release()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ bureau
    def _boucle_muette(self):
        """Hors Android : du silence, pour que la logique reste testable."""
        bloc = self.taux // 10
        while not self._stop.is_set():
            self._ajouter([0.0] * bloc)
            time.sleep(0.1)


# --------------------------------------------------------------------------
def demander_micro():
    """Demande l'autorisation d'enregistrer. Renvoie un message lisible."""
    if not IS_ANDROID:
        return "hors Android"
    try:
        from android.permissions import Permission, request_permissions
        request_permissions([Permission.RECORD_AUDIO])
        return "autorisation demandee"
    except Exception as e:  # noqa: BLE001
        return "impossible : %s" % e


def micro_autorise():
    if not IS_ANDROID:
        return False
    try:
        from android.permissions import Permission, check_permission
        return bool(check_permission(Permission.RECORD_AUDIO))
    except Exception:  # noqa: BLE001
        return False
