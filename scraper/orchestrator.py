"""
Orchestration du scraping : coordination entre navigation, extraction et export.

Ce module est le chef d'orchestre du scraper. Il fournit trois fonctions :
- scrape_sku()       : traite un seul SKU (navigation + extraction + telechargement)
- run_single()       : mode 1 — traitement d'un SKU unique depuis la ligne de commande
- run_excel_batch()  : mode 2 — traitement batch depuis un fichier Excel + export Odoo
"""

import sys       # Pour sys.exit() en cas d'erreur fatale
import time      # Pour les delais d'attente entre les actions
from pathlib import Path      # Manipulation de chemins de fichiers
from datetime import datetime  # Pour horodater le fichier Excel de sortie

import pandas as pd  # Lecture du fichier Excel source

from .config import DEFAULT_URLS, ODOO_SKU_COLUMN   # URLs par defaut et nom de colonne SKU
from .logger import log, banner                       # Logging et affichage de titres
from .driver import build_driver, accept_cookies      # Creation du navigateur Chrome
from .images import extract_images                    # Extraction d'images depuis une page
from .navigation import navigate_single, navigate_race  # Modes de navigation
from .download import download_all                    # Telechargement de toutes les images
from .excel import export_odoo_excel                  # Export Excel Odoo 18


def scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls, brand=""):
    """
    Traite un seul SKU : recherche, extraction et telechargement des images.

    Choisit automatiquement le mode de navigation :
    - Mode RACE si use_race=True ou si plusieurs URLs sont disponibles
    - Mode sequentiel sinon (un seul navigateur)

    Si une marque est specifiee, elle est ajoutee a la recherche et
    verifiee sur la page du produit avant de telecharger les images.

    Args:
        sku:         La reference produit a traiter (ex: "MH03AC-T03RED").
        output_base: Repertoire de destination pour les images (Path).
        headless:    Si True, le navigateur tourne sans fenetre visible.
        dry_run:     Si True, simule le traitement sans telecharger.
        use_race:    Si True, force le mode RACE multi-URL.
        custom_urls: Liste d'URLs personnalisees (vide = URLs par defaut).
        brand:       Nom de la marque pour enrichir la recherche et verifier (optionnel).

    Returns:
        Dict avec deux cles :
        - "all":       Liste de tous les fichiers telecharges.
        - "preferred": Le fichier prefere pour Excel (images[0]).
        Retourne des listes vides si aucune image n'est trouvee.
    """
    # Utilise les URLs personnalisees si fournies, sinon les URLs par defaut
    urls = custom_urls if custom_urls else DEFAULT_URLS

    # Log de la marque si specifiee
    if brand:
        log(f"Marque specifiee : '{brand}'", sku=sku)

    # Choix du mode de navigation
    if use_race or len(urls) > 1:
        # Mode RACE : lance tous les URLs en parallele, le premier gagne
        images = navigate_race(sku, urls, headless, brand=brand)
    else:
        # Mode sequentiel : un seul navigateur sur une seule URL
        driver = build_driver(headless)
        try:
            # Navigue vers la page de recherche et tente de trouver un produit
            if not navigate_single(driver, sku, url=urls[0] if urls else None, brand=brand):
                # Echec de la navigation ou marque non trouvee : retourne un resultat vide
                return {"all": [], "preferred": None}
            # Ferme la banniere de cookies sur la page produit
            accept_cookies(driver)
            # Attend 2 secondes que la page se charge completement
            time.sleep(2)
            # Extrait les images depuis la page courante
            images = extract_images(driver, sku)
        finally:
            # Ferme toujours le navigateur pour liberer les ressources
            driver.quit()

    # Verifie si des images ont ete trouvees
    if not images:
        # Aucune image : log et retourne un resultat vide
        log("Processus termine : Aucune image", "WARN", sku=sku)
        return {"all": [], "preferred": None}

    # Mode dry-run : affiche les URLs sans telecharger
    if dry_run:
        # Log de la premiere URL detectee
        log(f"[DRY-RUN] Cible detectee : {images[0]['url']}", "OK", sku=sku)
        # Retourne les URLs sans les telecharger
        return {
            # Liste de toutes les URLs trouvees (sans fichier)
            "all": [{"filename": "", "url": img["url"]} for img in images],
            # Image preferee : toujours images[0] (premiere image)
            "preferred": {
                "filename": "",
                "url": images[0]["url"],
            },
        }

    # Telecharge toutes les images et retourne le resultat
    return download_all(images, output_base, sku)


def run_single(sku, output_base, headless, dry_run, use_race, custom_urls, brand=""):
    """
    Mode 1 — Traite un seul SKU depuis la ligne de commande.

    Affiche un bandeau avec le mode utilise, lance le scraping,
    et quitte avec un code d'erreur si aucune image n'est trouvee.

    Args:
        sku:         La reference produit a traiter.
        output_base: Repertoire de destination pour les images (Path).
        headless:    Si True, le navigateur tourne sans fenetre visible.
        dry_run:     Si True, simule le traitement sans telecharger.
        use_race:    Si True, utilise le mode RACE multi-URL.
        custom_urls: Liste d'URLs personnalisees.
        brand:       Nom de la marque pour enrichir la recherche et verifier (optionnel).
    """
    # Determine le libelle du mode pour l'affichage
    mode = "RACE (Analyse multi-URL)" if use_race else "Sequentiel"
    # Affiche le bandeau avec le SKU, le mode et la marque si specifiee
    brand_info = f"  [Marque: {brand}]" if brand else ""
    banner(f"MODE 1 — SKU : {sku.upper()}  [{mode}]{brand_info}")
    # Lance le scraping du SKU avec la marque
    result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls, brand=brand)
    # Quitte avec erreur si aucune image n'a ete telechargee
    if not result or not result.get("all"):
        sys.exit(1)


def run_excel_batch(excel_path, output_base, headless, dry_run, use_race, custom_urls, brand=""):
    """
    Mode 2 — Traite tous les SKUs d'un fichier Excel et genere l'export Odoo.

    Lit le fichier Excel source, extrait les SKUs uniques de la colonne
    "Internal Reference", lance le scraping pour chacun, puis genere
    un fichier Excel formate pour l'import Odoo 18.

    Args:
        excel_path:  Chemin du fichier Excel source.
        output_base: Repertoire de destination pour les images (Path).
        headless:    Si True, les navigateurs tournent sans fenetre visible.
        dry_run:     Si True, simule le traitement sans telecharger.
        use_race:    Si True, utilise le mode RACE multi-URL.
        custom_urls: Liste d'URLs personnalisees.
        brand:       Nom de la marque pour enrichir la recherche et verifier (optionnel).
    """
    # Affiche le bandeau du mode batch
    banner("MODE 2 — Lecture Excel et creation du fichier Odoo")

    # Lit le fichier Excel source (toutes les colonnes en string pour eviter les conversions)
    df = pd.read_excel(excel_path, dtype=str)
    # Verifie que la colonne SKU existe dans le fichier
    if ODOO_SKU_COLUMN not in df.columns:
        # Affiche les colonnes disponibles pour aider l'utilisateur
        print(f"[X] Introuvable : Colonne '{ODOO_SKU_COLUMN}'. Options detectees : {list(df.columns)}")
        sys.exit(1)

    # Extrait les SKUs uniques (supprime les doublons et les valeurs vides)
    skus = df[ODOO_SKU_COLUMN].dropna().unique().tolist()
    # Log du nombre de SKUs a traiter
    log(f"Demarrage sur {len(skus)} element(s) unique(s) : {skus}")

    # Dictionnaire {sku: [filename, ...]} pour stocker les resultats
    sku_files = {}

    # Boucle sur chaque SKU unique
    for i, sku in enumerate(skus, 1):
        # Nettoie le SKU (supprime les espaces en debut/fin)
        sku = str(sku).strip()
        # Affiche la progression (numero / total)
        print(f"\n[{i}/{len(skus)}] Element: {sku} {'─' * 35}")
        # Lance le scraping pour ce SKU avec la marque
        result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls, brand=brand)
        # Recupere l'image preferee (images[1] ou fallback images[0])
        pref = result.get("preferred") if result else None
        # Stocke le nom du fichier prefere (ou liste vide si aucune image)
        sku_files[sku] = [pref["filename"]] if pref and pref.get("filename") else []

    # Generation du fichier Excel Odoo (sauf en mode dry-run)
    if not dry_run:
        # Cree le repertoire de sortie s'il n'existe pas
        output_base.mkdir(parents=True, exist_ok=True)
        # Horodatage pour rendre le nom de fichier unique
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Chemin complet du fichier Excel de sortie
        odoo_path = output_base / f"odoo18_import_{ts}.xlsx"
        # Genere le fichier Excel formate Odoo
        export_odoo_excel(df, sku_files, odoo_path)

        # Calcule le nombre de SKUs avec au moins une image
        found = sum(1 for v in sku_files.values() if v)
        # Liste des SKUs sans image
        missed = [s for s, v in sku_files.items() if not v]
        # Affiche le bilan du traitement
        print(f"\n  Bilan du traitement : {found}/{len(skus)} succes.")
        # Affiche les SKUs non resolus s'il y en a
        if missed:
            print(f"  Elements non resolus : {', '.join(missed)}")
        # Affiche le chemin absolu du fichier genere
        print(f"  Archive generee : {odoo_path.resolve()}\n")
