"""
Telechargement d'images depuis des URLs distantes.

Ce module fournit deux fonctions :
- download_image() : telecharge une seule image vers un fichier local
- download_all()   : telecharge toutes les images d'un produit et
                     identifie l'image preferee pour l'export Excel
"""

import urllib.request  # Module standard Python pour les requetes HTTP

from .config import DOWNLOAD_HEADERS  # Headers HTTP pour simuler un vrai navigateur
from .logger import log               # Logging thread-safe


def download_image(url, dest):
    """
    Telecharge une image depuis une URL et la sauvegarde sur le disque.

    Utilise les headers configures dans DOWNLOAD_HEADERS pour simuler
    un navigateur reel et eviter les blocages par les serveurs.

    Args:
        url:  L'URL de l'image a telecharger.
        dest: L'objet Path de destination (chemin complet du fichier).

    Returns:
        True si le telechargement a reussi, False en cas d'erreur.
    """
    # Cree une requete HTTP avec les headers anti-detection
    req = urllib.request.Request(url, headers=DOWNLOAD_HEADERS)
    try:
        # Ouvre la connexion HTTP avec un timeout de 20 secondes
        with urllib.request.urlopen(req, timeout=20) as resp:
            # Lit la reponse complete et ecrit les bytes dans le fichier
            dest.write_bytes(resp.read())
        # Telechargement reussi
        return True
    except Exception as e:
        # Erreur (timeout, SSL, 403, etc.) : log et retourne False
        log(f"Echec du telechargement {dest.name} : {e}", "ERR")
        return False


def download_all(images, output_dir, sku):
    """
    Telecharge TOUTES les images d'un produit et identifie la preferee.

    Chaque image est sauvegardee sous le nom SKU_INDEX.extension
    (ex: MH03AC-T03RED_0.png, MH03AC-T03RED_1.jpg, etc.).

    L'image preferee pour l'export Excel est :
    - images[1] en priorite (deuxieme image, souvent la meilleure vue)
    - images[0] en fallback (premiere image si la deuxieme echoue)

    Args:
        images:     Liste de dicts [{"url": str, "label": str}, ...].
        output_dir: Repertoire de destination (Path).
        sku:        La reference produit (pour le nommage des fichiers).

    Returns:
        Dict avec deux cles :
        - "all":       Liste de tous les fichiers telecharges avec succes.
        - "preferred": Le fichier prefere pour l'export Excel (ou None).
    """
    # Cree le repertoire de sortie s'il n'existe pas (parents inclus)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Liste de toutes les images telechargees avec succes
    downloaded = []
    # Image preferee pour l'export Excel (None par defaut)
    preferred = None

    # Parcourt chaque image avec son index
    for idx, img in enumerate(images):
        # Recupere l'URL de l'image
        url = img["url"]
        # Supprime les parametres de requete pour detecter l'extension
        clean_url = url.split("?")[0]
        # Extrait l'extension du fichier (apres le dernier point)
        ext = clean_url.rsplit(".", 1)[-1] if "." in clean_url else "jpg"
        # Verifie que l'extension est une extension d'image valide, sinon jpg
        ext = ext if ext.lower() in {"jpg", "jpeg", "png", "webp"} else "jpg"

        # Construit le nom de fichier : SKU_INDEX.extension
        fname = f"{sku.upper()}_{idx}.{ext}"
        # Construit le chemin complet du fichier de destination
        dest = output_dir / fname

        # Log du debut du telechargement
        log(f"Telechargement image[{idx}]: {fname}", "DL", sku=sku)
        # Tente le telechargement de l'image
        if download_image(url, dest):
            # Log de la taille du fichier telecharge (en KB)
            log(f"OK : {dest.stat().st_size // 1024} KB", "OK", sku=sku)
            # Cree l'entree du fichier telecharge
            entry = {"filename": fname, "path": dest, "url": url, "index": idx}
            # Ajoute l'entree a la liste des telechargements reussis
            downloaded.append(entry)
            # Selection de l'image preferee pour Excel :
            # Priorite a images[1] (deuxieme image)
            if idx == 1:
                preferred = entry
            # Fallback sur images[0] (premiere image) si images[1] pas encore vu
            elif idx == 0 and preferred is None:
                preferred = entry
        else:
            # Echec du telechargement de cette image
            log(f"Echec image[{idx}]", "WARN", sku=sku)

    # Log du bilan des telechargements
    if downloaded:
        log(f"{len(downloaded)}/{len(images)} image(s) telechargee(s)", "OK", sku=sku)
    else:
        log("Impossible de sauvegarder aucun fichier.", "ERR", sku=sku)

    # Retourne toutes les images et l'image preferee
    return {"all": downloaded, "preferred": preferred}
