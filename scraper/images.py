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
import time  # Pour les delais d'attente apres le scroll (lazy loading)

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
    Accepte les images avec :
    - Une extension valide (jpg, jpeg, png, webp, avif)
    - Une URL provenant d'un CDN e-commerce connu
    - Une URL contenant un chemin typique d'image produit

    Args:
        url: L'URL de l'image a valider.

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
        "/pixel", "/tracking", "/analytics",
        "/social", "/share", "/button",
    ]
    # Si l'URL contient un des patterns exclus, c'est pas une image produit
    if any(p in url_lower for p in excluded_patterns):
        return False

    # Rejette les images trop petites (1x1 pixels de tracking, icones minuscules)
    # Detecte les patterns comme _1x1, /1x1, -1x1 dans l'URL
    if re.search(r'[/_-]1x1[./]', url_lower):
        return False

    # Verifie si l'URL se termine par une extension d'image valide
    if re.search(r'\.(jpg|jpeg|png|webp|avif)$', clean, re.I):
        return True

    # Verifie si l'extension est presente avant des parametres de requete
    # Ex: image.jpg?w=800 -> le split("?")[0] gere deja ca, mais certaines
    # URLs ont l'extension suivie de parametres de chemin : image.jpg/resize/800
    if re.search(r'\.(jpg|jpeg|png|webp|avif)[/?&]', url_lower):
        return True

    # Liste des domaines CDN e-commerce connus
    # Ces CDN servent exclusivement des images de produits
    known_cdns = [
        # Shopify
        "cdn.shopify.com",
        # Scene7 / Adobe Dynamic Media (Hugo Boss, Adidas, Nike, Zara, etc.)
        "/is/image/",
        "/is/render/",
        "scene7.com",
        # Cloudinary (utilise par beaucoup de sites e-commerce)
        "cloudinary.com",
        "res.cloudinary.com",
        # Imgix (CDN d'images populaire)
        "imgix.net",
        # Contentful
        "ctfassets.net",
        # Shopify alternatif
        "/products/",
        "/files/",
        # Farfetch
        "farfetch.com/img/",
        # Hugo Boss
        "hugoboss.com",
        # Adidas
        "adidas.com",
        "assets.adidas.com",
        # Zalando
        "zalando.com",
        "ztat.net",
        # Amazon
        "images-na.ssl-images-amazon.com",
        "m.media-amazon.com",
        # Generic e-commerce patterns
        "/product-img/",
        "/product_images/",
        "/media/catalog/",
        "/images/products/",
        "/img/product/",
    ]
    # Si l'URL contient un des CDN connus, c'est une image valide
    if any(cdn in url_lower for cdn in known_cdns):
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
        # Ignore les data URIs (placeholders SVG, base64, etc.)
        if url.startswith("data:"):
            return

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

    # ---- STRATEGIE 0 : Meta tags (og:image, twitter:image) ----
    # Les meta tags sont TOUJOURS presents dans le HTML initial,
    # meme sur les sites full-JS (Hugo Boss, etc.) qui utilisent le lazy loading.
    try:
        for sel in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                # Le contenu de l'image est dans l'attribut "content"
                val = el.get_attribute("content") or ""
                if val.startswith("http") or val.startswith("//"):
                    add(val, "meta_og")
    except Exception:
        pass

    # ---- SCROLL pour declencher le lazy loading ----
    # Beaucoup de sites (Hugo Boss, Adidas, etc.) ne chargent les images
    # que quand elles sont visibles dans le viewport. On scrolle pour forcer le chargement.
    try:
        # Scrolle jusqu'au milieu de la page pour declencher le lazy loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(1)
        # Revient en haut pour que le DOM soit dans l'etat attendu
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(1)
    except Exception:
        pass

    # ---- STRATEGIE 1 : Extraction JS de TOUS les attributs ----
    # Au lieu de verifier une liste fixe d'attributs, on utilise JavaScript
    # pour scanner TOUS les attributs de chaque <img> et <source>.
    # Cela capture les attributs custom (data-normal-src, data-original-src, etc.)
    try:
        all_img_urls = driver.execute_script("""
            var urls = [];
            document.querySelectorAll('img, picture source, [role="img"]').forEach(function(el) {
                for (var i = 0; i < el.attributes.length; i++) {
                    var val = el.attributes[i].value;
                    if (val && (val.startsWith('http') || val.startsWith('//'))) {
                        urls.push(val);
                    }
                    // Gere les srcset (plusieurs URLs separees par des virgules)
                    if (val && el.attributes[i].name.indexOf('srcset') !== -1) {
                        val.split(',').forEach(function(part) {
                            var u = part.trim().split(' ')[0];
                            if (u && (u.startsWith('http') || u.startsWith('//'))) {
                                urls.push(u);
                            }
                        });
                    }
                }
            });
            return urls;
        """)
        # Ajoute chaque URL trouvee par le scan JS
        for url in (all_img_urls or []):
            add(url, "js_attr_scan")

        # Si des images ont ete trouvees, on retourne directement
        if images:
            log(f"{len(images)} image(s) valide(s) extraite(s) du DOM", "OK", sku=sku)
            return images
    except Exception:
        pass

    # ---- STRATEGIE 1b : Fallback DOM classique ----
    # Si le scan JS a echoue, on parcourt les elements avec des selecteurs CSS
    try:
        selectors = [
            "img[class*='product']",
            "img[class*='gallery']",
            "img[class*='grid']",
            "img[class*='card']",
            "a[class*='product'] img",
            "picture source",
            "picture img",
            "img",
        ]
        img_attrs = (
            "src", "data-src", "data-lazy-src",
            "data-zoom-src", "data-image", "data-original",
            "srcset", "data-srcset",
        )

        for sel in selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                for attr in img_attrs:
                    val = el.get_attribute(attr) or ""
                    if "srcset" in attr and val:
                        for part in val.split(","):
                            part_url = part.strip().split(" ")[0]
                            if part_url.startswith("http") or part_url.startswith("//"):
                                add(part_url, "html_srcset")
                    else:
                        if val.startswith("http") or val.startswith("//"):
                            add(val, "html_img")

        if images:
            log(f"{len(images)} image(s) valide(s) extraite(s) du visuel HTML", "OK", sku=sku)
            return images
    except Exception:
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
    # Pattern 1 : URLs avec extension d'image classique
    cdn_re = re.compile(
        r'(?:https?:)?//[^\s"\'\\<>]+\.(?:jpg|jpeg|png|webp|avif)', re.I
    )
    # Parcourt toutes les correspondances dans le code source de la page
    for m in cdn_re.finditer(driver.page_source):
        # Ajoute chaque URL trouvee avec le label "regex_cdn"
        add(m.group(0), "regex_cdn")

    # Pattern 2 : URLs Scene7 / Dynamic Media (Hugo Boss, Adidas, Nike, etc.)
    # Ces URLs n'ont pas d'extension mais contiennent "/is/image/" ou "/is/render/"
    scene7_re = re.compile(
        r'(?:https?:)?//[^\s"\'\\<>]+/is/(?:image|render)/[^\s"\'\\<>]+', re.I
    )
    for m in scene7_re.finditer(driver.page_source):
        add(m.group(0), "regex_scene7")

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
