"""
Faire un calcul long sans figer l'ecran.

Le probleme mesure : un preset sur cinq secondes de son coute 600 ms ici,
donc trois a six secondes sur telephone. Pendant ce temps l'interface ne
repond plus, et Android tue une application figee plus de cinq secondes.
L'utilisateur ne voit pas un traitement lent : il voit un plantage.

La regle est donc : tout calcul au-dela de quelques dixiemes de seconde
part dans un fil, et l'ecran affiche une fenetre de patience.

Ce module ne connait pas Kivy. Le rappel vers l'interface passe par une
fonction `planifier` injectee : Clock.schedule_once dans l'application,
un appel direct dans les tests. C'est ce qui permet de tester le
mecanisme complet sans ecran.
"""

import threading


def en_fond(calcul, sur_succes, sur_echec, planifier):
    """Lance calcul() dans un fil et livre le resultat au bon endroit.

    calcul      : fonction sans argument, executee dans le fil
    sur_succes  : recoit le resultat de calcul()
    sur_echec   : recoit l'exception si calcul() leve
    planifier   : fait executer un rappel sur le fil d'interface ;
                  signature planifier(fonction), la fonction recevant
                  des arguments ignores (compatibilite Clock)

    Renvoie le fil, deja demarre. Le fil est un demon : il ne retient
    jamais la fermeture de l'application.

    Regle importante : sur_succes et sur_echec ne sont JAMAIS appeles
    directement depuis le fil de calcul. Toucher l'interface depuis un
    autre fil produit des plantages rares et indebogables ; tout passe
    par planifier, sans exception.
    """
    def fil():
        try:
            resultat = calcul()
        except Exception as e:  # noqa: BLE001
            # Piege de Python : la variable d'exception est effacee a la
            # sortie du bloc except. Le rappel s'execute PLUS TARD, sur
            # l'autre fil : il faut donc figer l'erreur tout de suite.
            planifier(lambda *_a, err=e: sur_echec(err))
            return
        planifier(lambda *_a: sur_succes(resultat))

    t = threading.Thread(target=fil, daemon=True)
    t.start()
    return t


class Serie:
    """Empeche deux travaux de tourner en meme temps.

    Deux traitements simultanes sur le meme son se marchent dessus et le
    resultat depend de l'ordre d'arrivee. On refuse donc le second appui
    au lieu de le mettre en attente : l'utilisateur qui tapote deux fois
    attend UN resultat, pas deux appliques l'un sur l'autre.
    """

    def __init__(self):
        self._occupe = False
        self._verrou = threading.Lock()

    @property
    def occupe(self):
        return self._occupe

    def lancer(self, calcul, sur_succes, sur_echec, planifier):
        """Comme en_fond, mais refuse si un travail tourne deja.

        Renvoie True si le travail part, False s'il est refuse.
        """
        with self._verrou:
            if self._occupe:
                return False
            self._occupe = True

        def succes(resultat):
            self._occupe = False
            sur_succes(resultat)

        def echec(e):
            self._occupe = False
            sur_echec(e)

        en_fond(calcul, succes, echec, planifier)
        return True
