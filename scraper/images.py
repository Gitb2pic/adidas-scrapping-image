"""
Extraction et validation des images depuis une page web.

Ce module fournit trois strategies d'extraction (par ordre de priorite) :
1. HTML DOM   : parcourt les balises <img> de la page
2. JSON cache : explore les objets JS embarques (__NEXT_DATA__, etc.)
3. Regex      : recherche brute des URLs d'images dans le code source

Fonctions publiques :
- get_high_res_url() : supprime les suffixes de taille Shopify
- is_valid_image()   : filtre les icones/logos pour garder les vraies images
- extract_images()   : orchestre les 3 strategies d'extraction
"""

import re    # Expressions regulieres pour la validation et le nettoyage d'URLs
import json  # Pour parser les donnees JSON embarquees dans les pages

from selenium.webdriver.common.by import By  # Localisation d'elements Selenium

from .logger import log  # Logging thread-safe


def get_high_res_url(url: str) -> str:
    """
    Supprime les suffixes de taille Shopify pour obtenir l'image en haute resolution.

    Shopify ajoute des suffixes comme '_200x200', '_400x' aux URLs d'images.
    Cette fonction les supprime pour forcer le telechargement de l'image originale.

    Exemple :
        'image_200x300.jpg' -> 'image.jpg'
        'photo_800x.png'    -> 'photo.png'

    Args:
        url: L'URL de l'image a nettoyer.

    Returns:
        L'URL sans suffixe de taille, ou chaine vide si l'URL est vide.
    """
    # Si l'URL est vide ou None, on retourne une chaine vide
    if not url:
        return ""
    # Regex : supprime le pattern _WIDTHxHEIGHT avant l'extension du fichier
    # Exemple : _200x300.jpg -> .jpg
    return re.sub(
        r'_([0-9]+x[0-9]*|[0-9]*x[0-9]+)(\.[a-zA-Z0-9]{3,4})',
        r'\2',
        url,
        flags=re.IGNORECASE,
    )


def is_valid_image(url: str) -> bool:
    """
    Verifie qu'une URL correspond a une vraie image de produit.

    Filtre les faux positifs : logos, icones, badges, favicons, placeholders, etc.
    Accepte les images avec une extension valide (jpg, png, webp) ou provenant
    de CDN connus (Shopify).

    Args:
        url: L'URL de l'image a valider (sans parametres de requete).

    Returns:
        True si l'URL est une image de produit valide, False sinon.
    """
    # Convertit en minuscules pour une comparaison insensible a la casse
    url_lower = url.lower()
    # Supprime les parametres de requete (tout apres le '?')
    clean = url.split("?")[0]

    # Liste des patterns a exclure (logos, icones, badges, etc.)
    excluded_patterns = [
        "/logo", "/icon", "/badge", "/banner",
        "/flag", "/avatar", "/favicon", "/sprite",
        "placeholder", "fallback", "default",
    ]
    # Si l'URL contient un des patterns exclus, c'est pas une image produit
    if any(p in url_lower for p in excluded_patterns):
        return False

    # Verifie si l'URL se termine par une extension d'image valide
    if re.search(r'\.(jpg|jpeg|png|webp)$', clean, re.I):
        return True

    # Accepte les URLs provenant de CDN Shopify ou contenant /products/ ou /files/
    if "cdn.shopify.com" in url_lower or "/products/" in url_lower or "/files/" in url_lower:
        return True

    # Par defaut, l'URL n'est pas consideree comme une image valide
    return False


def extract_images(driver, sku):
    """
    Extrait toutes les images de produit depuis la page courante du navigateur.

    Utilise 3 strategies par ordre de priorite :
    1. HTML DOM   : parcourt les balises <img> (ordre du document = ordre visuel)
    2. JSON cache : explore les donnees JS embarquees (__NEXT_DATA__, etc.)
    3. Regex      : recherche brute des URLs d'images dans le code source HTML

    Chaque image trouvee est dedupliquee et validee avant d'etre ajoutee.

    Args:
        driver: L'instance Selenium Chrome avec la page chargee.
        sku:    La reference produit (pour le logging).

    Returns:
        Liste de dicts [{"url": str, "label": str}, ...] avec les images trouvees.
        Liste vide si aucune image n'est trouvee.
    """
    # Liste des images trouvees (resultat final)
    images = []
    # Set pour dedupliquer les URLs (evite les doublons)
    seen = set()

    def add(url, label):
        """
        Ajoute une image a la liste si elle est valide et pas deja presente.

        Args:
            url:   L'URL brute de l'image.
            label: Etiquette decrivant la source (html_img, html_srcset, etc.).
        """
        # Corrige les URLs qui commencent par "//" (protocole relatif)
        if url.startswith("//"):
            url = "https:" + url

        # Supprime les suffixes de taille Shopify pour la haute resolution
        url = get_high_res_url(url)
        # Supprime les parametres de requete pour la deduplication
        clean = url.split("?")[0]

        # Si l'URL (nettoyee) a deja ete vue, on l'ignore
        if clean in seen:
            return
        # Marque l'URL comme vue
        seen.add(clean)

        # Valide que c'est une vraie image de produit (pas un logo/icone)
        if is_valid_image(clean):
            # Ajoute l'image a la liste des resultats
            images.append({"url": url, "label": label})

    # ---- STRATEGIE 1 : HTML DOM ----
    # Priorite absolue : le premier element lu = la premiere image sur la page
    try:
        # Selecteurs CSS cibles, du plus specifique au plus generique
        selectors = [
            # Images avec classe contenant "product"
            "img[class*='product']",
            # Images dans une grille
            "img[class*='grid']",
            # Images dans une carte
            "img[class*='card']",
            # Images a l'interieur d'un lien produit
            "a[class*='product'] img",
            # Toutes les images (dernier recours)
            "img",
        ]

        # Parcourt chaque selecteur
        for sel in selectors:
            # Trouve tous les elements correspondant au selecteur
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                # Verifie les 4 attributs possibles contenant une URL d'image
                for attr in ("src", "data-src", "srcset", "data-srcset"):
                    # Recupere la valeur de l'attribut (ou chaine vide si absent)
                    val = el.get_attribute(attr) or ""
                    # Les attributs srcset contiennent plusieurs URLs separees par des virgules
                    if "srcset" in attr and val:
                        # Parcourt chaque URL dans le srcset
                        for part in val.split(","):
                            # Extrait l'URL (avant l'espace et le descripteur de taille)
                            part_url = part.strip().split(" ")[0]
                            # Verifie que c'est une URL absolue
                            if part_url.startswith("http") or part_url.startswith("//"):
                                add(part_url, "html_srcset")
                    else:
                        # Attributs simples (src, data-src) : une seule URL
                        if val.startswith("http") or val.startswith("//"):
                            add(val, "html_img")

        # Si des images ont ete trouvees via le DOM, on retourne directement
        if images:
            log(f"{len(images)} image(s) valide(s) extraite(s) du visuel HTML", "OK", sku=sku)
            return images
    except Exception:
        # En cas d'erreur DOM, on passe a la strategie suivante
        pass

    # ---- STRATEGIE 2 : Objets JSON embarques ----
    # Certains sites (Next.js, React, etc.) stockent les donnees dans des variables JS
    for var in ("__NEXT_DATA__", "__STATE__", "__PRELOADED_STATE__", "__INITIAL_STATE__"):
        try:
            # __NEXT_DATA__ est un element <script id="__NEXT_DATA__"> dans le HTML
            if var == "__NEXT_DATA__":
                # Recupere le contenu texte de l'element par son ID
                el = driver.find_element(By.ID, var)
                raw = el.get_attribute("textContent")
            else:
                # Les autres variables sont des objets JS globaux sur window
                raw = driver.execute_script(f"return JSON.stringify(window.{var})")

            # Si des donnees ont ete trouvees, on les parcourt recursivement
            if raw:
                # Parse le JSON et parcourt l'arbre pour trouver les URLs d'images
                _walk_json(json.loads(raw), add)
                # Si des images ont ete extraites, on retourne directement
                if images:
                    log(f"{len(images)} image(s) extraite(s) des donnees cachees {var}", "OK", sku=sku)
                    return images
        except Exception:
            # Variable non trouvee ou JSON invalide : on essaie la suivante
            pass

    # ---- STRATEGIE 3 : Regex de secours ----
    # Recherche brute de toutes les URLs d'images dans le code source HTML
    cdn_re = re.compile(
        # Match les URLs se terminant par .jpg, .jpeg, .png ou .webp
        r'(?:https?:)?//[^\s"\'\\<>]+\.(?:jpg|jpeg|png|webp)', re.I
    )
    # Parcourt toutes les correspondances dans le code source de la page
    for m in cdn_re.finditer(driver.page_source):
        # Ajoute chaque URL trouvee avec le label "regex_cdn"
        add(m.group(0), "regex_cdn")

    # Log du resultat de la recherche Regex
    if images:
        log(f"{len(images)} image(s) valide(s) recuperee(s) par Regex", "OK", sku=sku)
    else:
        log("Aucune image valide trouvee sur cette page.", "WARN", sku=sku)

    # Retourne les images trouvees (peut etre une liste vide)
    return images


def _walk_json(node, callback):
    """
    Parcourt recursivement un objet JSON pour extraire les URLs d'images.

    Cherche les cles connues (images, media, gallery_images, etc.) et
    appelle le callback pour chaque URL trouvee.

    Args:
        node:     Le noeud JSON courant (dict, list ou valeur).
        callback: Fonction callback(url, label) appelee pour chaque URL trouvee.
    """
    # Si le noeud est un dictionnaire
    if isinstance(node, dict):
        # Cherche les cles connues qui contiennent generalement des images
        for key in ("view_list", "images", "gallery_images", "media", "src", "url"):
            # Recupere la valeur associee a la cle
            val = node.get(key)
            # Si la valeur est une liste, on parcourt chaque element
            if isinstance(val, list):
                for i, item in enumerate(val):
                    # Si l'element est directement une URL string
                    if isinstance(item, str) and (item.startswith("http") or item.startswith("//")):
                        callback(item, f"{key}_{i}")
                    # Si l'element est un dict, on cherche les sous-cles d'image
                    elif isinstance(item, dict):
                        for k in ("image_url", "src", "url", "href"):
                            # Recupere l'URL dans la sous-cle
                            u = item.get(k, "")
                            # Si c'est une URL valide, on l'ajoute et on arrete
                            if u and (u.startswith("http") or u.startswith("//")):
                                callback(u, f"{key}_{i}_{k}")
                                break  # Une seule URL par sous-dict
            # Si la valeur est directement une URL string
            elif isinstance(val, str) and (val.startswith("http") or val.startswith("//")):
                callback(val, f"json_direct_{key}")

        # Parcourt recursivement toutes les valeurs du dictionnaire
        for v in node.values():
            _walk_json(v, callback)
    # Si le noeud est une liste, on parcourt chaque element
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, callback)
