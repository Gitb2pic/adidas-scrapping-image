"""
Navigation et recherche de produits sur les sites web.

Ce module gere deux modes de navigation :
- navigate_single() : navigation sequentielle sur un seul site
- navigate_race()   : mode RACE multi-URL en parallele (le premier gagne)

Le mode RACE lance plusieurs navigateurs simultanement sur differents sites
et retourne les images du premier site qui repond avec des resultats.
"""

import time       # Pour les delais d'attente entre les actions
import threading  # Pour la synchronisation entre threads (Lock, Event)
from concurrent.futures import ThreadPoolExecutor  # Pool de threads pour le mode RACE

from selenium.webdriver.common.by import By  # Localisation d'elements Selenium

from .config import DEFAULT_URLS, PRODUCT_LINK_SELECTORS  # URLs par defaut et selecteurs CSS
from .logger import log                                     # Logging thread-safe
from .driver import build_driver, accept_cookies            # Creation du navigateur et gestion cookies
from .images import extract_images                          # Extraction d'images depuis une page


def _expand_url(url_template, sku, brand=""):
    """
    Remplace les placeholders {sku} et {brand} dans un template d'URL.

    Si la marque est vide, le placeholder {brand} est supprime proprement
    (y compris le '+' qui le precede pour eviter un '+' orphelin).

    Args:
        url_template: L'URL avec les placeholders {sku} et {brand}.
        sku:          La reference produit (sera mise en majuscules).
        brand:        Le nom de la marque (optionnel, chaine vide par defaut).

    Returns:
        L'URL avec les placeholders remplaces.
    """
    # Remplace {sku} par la reference produit en majuscules
    url = url_template.replace("{sku}", sku.upper())
    # Si une marque est fournie, on la remplace dans l'URL
    if brand:
        url = url.replace("{brand}", brand)
    else:
        # Si pas de marque, on supprime le placeholder et le '+' qui le precede
        url = url.replace("{brand}+", "").replace("{brand}", "")
    return url


def verify_brand(driver, brand):
    """
    Verifie que le nom de la marque apparait sur la page courante.

    Cherche le nom de la marque dans le titre de la page et dans le texte
    visible du body. La comparaison est insensible a la casse.

    Args:
        driver: L'instance Selenium Chrome avec la page chargee.
        brand:  Le nom de la marque a verifier (ex: "adidas").

    Returns:
        True si la marque est trouvee sur la page, False sinon.
    """
    # Convertit la marque en minuscules pour une comparaison insensible a la casse
    brand_lower = brand.lower()
    # Verifie si la marque apparait dans le titre de la page
    if brand_lower in driver.title.lower():
        return True
    # Recupere le texte visible de la page entiere (body)
    try:
        # Utilise JavaScript pour recuperer le texte du body (plus rapide que Selenium)
        page_text = driver.execute_script("return document.body.innerText || ''")
        # Verifie si la marque apparait dans le texte visible
        if brand_lower in page_text.lower():
            return True
    except Exception:
        pass
    # La marque n'a pas ete trouvee sur la page
    return False


def navigate_single(driver, sku, url=None, brand=""):
    """
    Navigue vers une page de recherche et tente de cliquer sur le premier produit.

    Ouvre l'URL de recherche, accepte les cookies, puis parcourt la liste
    des selecteurs CSS pour trouver un lien vers une page produit.
    Si un produit est trouve, le navigateur navigue vers cette page.
    Si une marque est specifiee, verifie qu'elle apparait sur la page.

    Args:
        driver: L'instance Selenium Chrome active.
        sku:    La reference produit a rechercher.
        url:    L'URL de recherche personnalisee (optionnel).
                Si None, utilise la premiere URL par defaut (Google).
        brand:  Nom de la marque pour enrichir la recherche et verifier la page (optionnel).

    Returns:
        True si la page est chargee et la marque validee (ou pas de marque specifiee).
        False si la marque est specifiee mais absente de la page.
    """
    # Construit l'URL de recherche en remplacant {sku} et {brand}
    search = _expand_url(url or DEFAULT_URLS[0], sku, brand)
    # Log de l'URL de recherche utilisee
    log(f"Recherche : {search}", sku=sku)
    # Charge la page de recherche dans le navigateur
    driver.get(search)
    # Ferme la banniere de cookies si elle apparait
    accept_cookies(driver)
    # Attend 3 secondes que la page se charge completement
    time.sleep(3)

    # Parcourt chaque selecteur CSS pour trouver un lien produit
    for selector in PRODUCT_LINK_SELECTORS:
        try:
            # Cherche le premier element correspondant au selecteur
            el = driver.find_element(By.CSS_SELECTOR, selector)
            # Recupere l'attribut href (URL de destination)
            href = el.get_attribute("href")
            # Verifie que le lien est une URL absolue valide
            if href and href.startswith("http"):
                # Log du produit detecte
                log(f"Produit detecte : {href}", sku=sku)
                # Navigue vers la page du produit
                driver.get(href)
                # Attend 3 secondes que la page produit se charge
                time.sleep(3)
                # Si une marque est specifiee, verifie qu'elle apparait sur la page
                if brand and not verify_brand(driver, brand):
                    # La marque n'est pas presente : le produit ne correspond pas
                    log(f"Marque '{brand}' non trouvee sur la page, produit ignore.", "WARN", sku=sku)
                    return False
                # Produit trouve, marque validee (ou pas de marque specifiee)
                return True
        except Exception:
            # Selecteur non trouve sur la page, on essaie le suivant
            continue

    # Aucun lien produit trouve : on reste sur la page de recherche
    log("Extraction directe depuis la page de recherche.", "INFO", sku=sku)
    # Verifie la marque sur la page de recherche elle-meme
    if brand and not verify_brand(driver, brand):
        log(f"Marque '{brand}' non trouvee sur la page de recherche.", "WARN", sku=sku)
        return False
    return True


class RaceResult:
    """
    Conteneur thread-safe pour stocker le resultat du mode RACE.

    Permet a plusieurs threads de concourir : le premier qui trouve
    des images "claim" le resultat, et les autres threads s'arretent.

    Attributes:
        winner_url:    L'URL du site gagnant.
        winner_images: La liste des images trouvees par le gagnant.
        lock:          Verrou pour proteger l'acces concurrent.
        found:         Event pour signaler qu'un gagnant a ete trouve.
    """

    def __init__(self):
        """Initialise le conteneur avec des valeurs vides."""
        # URL du site qui a gagne la course (None tant qu'aucun gagnant)
        self.winner_url = None
        # Liste des images trouvees par le gagnant (vide tant qu'aucun gagnant)
        self.winner_images = []
        # Verrou pour proteger l'ecriture du resultat contre les acces concurrents
        self.lock = threading.Lock()
        # Event pour signaler a tous les threads qu'un gagnant a ete trouve
        self.found = threading.Event()

    def claim(self, url, images):
        """
        Tente de revendiquer la victoire pour un thread.

        Le premier thread a appeler cette methode gagne.
        Les appels suivants retournent False sans modifier le resultat.

        Args:
            url:    L'URL du site qui a trouve des images.
            images: La liste des images trouvees.

        Returns:
            True si ce thread est le gagnant, False si un autre a deja gagne.
        """
        # Acquisition du verrou pour un acces exclusif
        with self.lock:
            # Verifie qu'aucun autre thread n'a deja gagne
            if not self.found.is_set():
                # Enregistre l'URL et les images du gagnant
                self.winner_url = url
                self.winner_images = images
                # Signale a tous les threads que la course est terminee
                self.found.set()
                return True
        # Un autre thread a deja gagne
        return False


def _race_worker(url, sku, headless, race, brand=""):
    """
    Worker execute dans un thread pour le mode RACE.

    Chaque worker ouvre un navigateur, charge une URL de recherche,
    tente de naviguer vers un produit, extrait les images, et
    revendique la victoire s'il est le premier a trouver des resultats.
    Si une marque est specifiee, verifie sa presence sur la page.

    Args:
        url:      L'URL de recherche a visiter (deja expansee avec le SKU et la marque).
        sku:      La reference produit (pour le logging).
        headless: Si True, le navigateur tourne sans fenetre visible.
        race:     L'objet RaceResult partage entre tous les workers.
        brand:    Nom de la marque a verifier sur la page (optionnel).
    """
    # Si un autre thread a deja gagne, on ne demarre meme pas
    if race.found.is_set():
        return

    # Variable pour le navigateur (initialisee a None pour le finally)
    driver = None
    try:
        # Cree un nouveau navigateur Chrome pour ce thread
        driver = build_driver(headless)
        # Log de l'URL visitee par ce worker
        log(f"[RACE] -> {url}", sku=sku)
        # Charge la page de recherche
        driver.get(url)
        # Ferme la banniere de cookies
        accept_cookies(driver)
        # Attend 3 secondes que la page se charge
        time.sleep(3)

        # Verifie si la page retourne une erreur 404
        if "404" in driver.title.lower():
            log(f"[RACE] Erreur 404 : {url}", "WARN", sku=sku)
            return

        # Verifie si un autre thread a gagne pendant le chargement
        if race.found.is_set():
            return

        # Tente de naviguer vers une page produit via les selecteurs CSS
        for selector in PRODUCT_LINK_SELECTORS:
            try:
                # Cherche un lien produit sur la page
                el = driver.find_element(By.CSS_SELECTOR, selector)
                # Recupere l'URL de destination
                href = el.get_attribute("href")
                # Verifie que c'est une URL absolue valide
                if href and href.startswith("http"):
                    log(f"[RACE] Produit detecte : {href}", sku=sku)
                    # Navigue vers la page du produit
                    driver.get(href)
                    # Attend que la page se charge
                    time.sleep(3)
                    # Sort de la boucle (un seul produit suffit)
                    break
            except Exception:
                # Selecteur non trouve, on essaie le suivant
                continue

        # Verifie a nouveau si un autre thread a gagne
        if race.found.is_set():
            return

        # Si une marque est specifiee, verifie qu'elle apparait sur la page
        if brand and not verify_brand(driver, brand):
            log(f"[RACE] Marque '{brand}' non trouvee sur : {url}", "WARN", sku=sku)
            return

        # Extrait les images depuis la page courante
        images = extract_images(driver, sku)

        # Si des images ont ete trouvees et que personne n'a encore gagne
        if images and not race.found.is_set():
            # Tente de revendiquer la victoire
            if race.claim(url, images):
                log(f"[RACE] SUCCES sur : {url}  ({len(images)} images)", "OK", sku=sku)
        else:
            # Aucune image trouvee sur cette URL
            log(f"[RACE] Aucune image : {url}", "WARN", sku=sku)

    except Exception as e:
        # Erreur inattendue (timeout, crash, etc.)
        if not race.found.is_set():
            log(f"[RACE] Erreur {url} : {e}", "WARN", sku=sku)
    finally:
        # Ferme toujours le navigateur pour liberer les ressources
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def navigate_race(sku, urls, headless, timeout=90, brand=""):
    """
    Lance une course entre plusieurs URLs pour trouver des images de produit.

    Chaque URL est visitee dans un thread separe avec son propre navigateur.
    Le premier thread qui trouve des images (et dont la marque est validee) gagne.

    Args:
        sku:      La reference produit a rechercher.
        urls:     Liste d'URLs de recherche avec les placeholders {sku} et {brand}.
        headless: Si True, les navigateurs tournent sans fenetre visible.
        timeout:  Temps maximum d'attente en secondes (defaut: 90s).
        brand:    Nom de la marque a verifier sur la page (optionnel).

    Returns:
        Liste des images trouvees par le gagnant, ou liste vide si timeout.
    """
    # Remplace {sku} et {brand} dans chaque URL
    expanded = [_expand_url(u, sku, brand) for u in urls]
    # Cree le conteneur de resultat partage entre les threads
    race = RaceResult()
    # Log du nombre d'URLs lancees en parallele
    log(f"[RACE] {len(expanded)} URLs en parallele", sku=sku)

    # Cree un pool de threads (un par URL)
    with ThreadPoolExecutor(max_workers=len(expanded)) as pool:
        # Lance un worker pour chaque URL, en passant la marque
        for url in expanded:
            pool.submit(_race_worker, url, sku, headless, race, brand)
        # Attend qu'un gagnant soit trouve ou que le timeout expire
        race.found.wait(timeout=timeout)

    # Verifie si un gagnant a ete trouve
    if not race.found.is_set():
        # Timeout expire sans resultat
        log("Echec (timeout ou aucune source valide).", "ERR", sku=sku)
        return []

    # Retourne les images du gagnant
    return race.winner_images
