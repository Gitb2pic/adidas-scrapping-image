"""
Systeme de logging thread-safe pour le scraper.

Ce module fournit deux fonctions :
- log()    : affiche un message avec icone et prefixe SKU, protege par un verrou
- banner() : affiche un titre encadre pour delimiter les sections
"""

import threading  # Pour le verrou (Lock) qui protege les prints en multi-thread

# Verrou global pour empecher les messages de se melanger
# quand plusieurs threads ecrivent en meme temps
_log_lock = threading.Lock()


def log(msg, level="INFO", sku=""):
    """
    Affiche un message de log formate avec une icone et un prefixe SKU optionnel.

    Le message est protege par un verrou pour eviter les melanges
    en environnement multi-thread (mode RACE).

    Args:
        msg:   Le message a afficher.
        level: Le niveau de log parmi "INFO", "OK", "WARN", "ERR", "DL".
        sku:   La reference produit (optionnel), affichee comme prefixe [SKU].
    """
    # Dictionnaire des icones associees a chaque niveau de log
    icons = {"INFO": "i ", "OK": "OK", "WARN": "! ", "ERR": "X ", "DL": "->"}
    # Prefixe avec le SKU si fourni, sinon chaine vide
    prefix = f"[{sku}] " if sku else ""
    # Acquisition du verrou pour ecrire sans collision entre threads
    with _log_lock:
        # Affichage formate : [icone] [SKU] message
        print(f"  [{icons.get(level, '  ')}] {prefix}{msg}")


def banner(text):
    """
    Affiche un titre encadre par des barres de separation.

    Utilise pour delimiter visuellement les grandes sections
    du traitement (demarrage d'un mode, etc.).

    Args:
        text: Le texte du titre a afficher.
    """
    # Ligne de separation de 60 caracteres "="
    bar = "=" * 60
    # Affichage avec saut de ligne avant et apres pour la lisibilite
    print(f"\n{bar}\n  {text}\n{bar}\n")
