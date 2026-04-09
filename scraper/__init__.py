"""
Package scraper — Extracteur d'images de produits universel.

Ce package permet de scraper des images de produits depuis n'importe quel
site e-commerce en utilisant Selenium. Il supporte trois modes :
- Mode 1 : SKU unique (recherche et telechargement)
- Mode 2 : Batch Excel (traitement de masse + export Odoo 18)
- Mode 3 : RACE multi-URL (plusieurs sites en parallele, le premier gagne)

Modules :
    config       — Constantes globales (URLs, headers, selecteurs, colonnes Odoo)
    logger       — Systeme de logging thread-safe
    driver       — Creation et configuration du navigateur Selenium Chrome
    images       — Extraction et validation des images depuis une page web
    navigation   — Navigation sequentielle et mode RACE multi-URL
    download     — Telechargement des images sur le disque
    excel        — Export des resultats au format Excel Odoo 18
    colors       — Extraction du code couleur depuis les URLs de produits
    orchestrator — Coordination de toutes les etapes du scraping
"""

# Expose les fonctions principales au niveau du package
# pour permettre : from scraper import run_single, run_excel_batch
from .orchestrator import scrape_sku, run_single, run_excel_batch
from .colors import extract_color_code, add_color_codes
