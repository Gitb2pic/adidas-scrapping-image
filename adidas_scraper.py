#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║      Image Scraper Générique — 3 modes                       ║
╠══════════════════════════════════════════════════════════════╣
║  MODE 1  SKU unique                                          ║
║    python adidas_scraper.py --sku MH03AC-T03RED              ║
║                                                              ║
║  MODE 2  Batch depuis Excel  +  export Odoo 18               ║
║    python adidas_scraper.py --excel variants.xlsx             ║
║                                                              ║
║  MODE 3  Multi-URL async (course, premier gagne)             ║
║    python adidas_scraper.py --sku MH03AC-T03RED --urls       ║
║                                                              ║
║  Options : --output ./images  --headless  --dry-run          ║
║            --sites https://amazon.com/s?k={sku}              ║
╚══════════════════════════════════════════════════════════════╝

Point d'entree principal du scraper.
Ce fichier ne contient que le parsing des arguments CLI et l'appel
aux fonctions d'orchestration du package scraper.

Requirements:
    pip install -r requirements.txt
"""

import sys       # Pour sys.exit() en cas d'erreur d'import
import argparse  # Parsing des arguments en ligne de commande
from pathlib import Path  # Manipulation de chemins de fichiers

# Tente d'importer les fonctions principales du package scraper
try:
    # Importe les deux fonctions d'orchestration exposees par le package
    from scraper import run_single, run_excel_batch
except ImportError:
    # Si l'import echoue, les dependances ne sont pas installees
    print("\n[X] Dependances manquantes. Lancer d'abord :\n")
    print("    pip install -r requirements.txt\n")
    sys.exit(1)


def main():
    """
    Point d'entree principal du scraper.

    Parse les arguments de la ligne de commande et lance le mode
    de traitement correspondant :
    - --sku   : Mode 1 (SKU unique)
    - --excel : Mode 2 (batch Excel + export Odoo)
    - --urls  : Active le mode RACE (multi-URL en parallele)
    - --sites : Ajoute des sites personnalises a la recherche
    """
    # Creation du parser d'arguments avec description formatee
    parser = argparse.ArgumentParser(
        description="Extracteur d'Images — Mode Unitaire | Mode Excel | Mode Asynchrone",
        # RawTextHelpFormatter preserve les sauts de ligne dans l'aide
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # Groupe mutuellement exclusif : --sku OU --excel (pas les deux)
    src = parser.add_mutually_exclusive_group(required=True)
    # Option --sku : reference produit unique a traiter
    src.add_argument("--sku", help="Reference unique, ex: MH03AC-T03RED")
    # Option --excel : fichier Excel source avec les SKUs
    src.add_argument("--excel", help="Fichier source (doit contenir la colonne 'Internal Reference')")

    # Option --urls : active le mode RACE avec des URLs personnalisees
    # nargs="*" permet de passer 0 ou N URLs (vide = URLs par defaut)
    parser.add_argument(
        "--urls",
        nargs="*",
        metavar="URL",
        help=(
            "Activer le mode de balayage asynchrone [RACE] :\n"
            "  --urls https://site.com/search?q={sku}\n"
            "  --urls   (vide = liste par defaut + Google Images)\n"
            "Utiliser {sku} comme placeholder dans l'URL."
        ),
    )
    # Option --sites : ajoute des sites supplementaires a la liste de recherche
    # nargs="+" exige au moins une URL
    parser.add_argument(
        "--sites",
        nargs="+",
        metavar="URL",
        help=(
            "Ajouter des sites personnalises a la liste de recherche :\n"
            "  --sites https://www.amazon.com/s?k={sku} https://www.ebay.com/sch/i.html?_nkw={sku}\n"
            "Ces URLs seront ajoutees aux URLs par defaut."
        ),
    )
    # Option --brand : nom de la marque pour enrichir la recherche et verifier la page
    parser.add_argument(
        "--brand",
        default="",
        help=(
            "Nom de la marque pour filtrer les resultats :\n"
            "  --brand adidas\n"
            "La marque est ajoutee a la recherche Google et verifiee sur la page produit.\n"
            "Si la marque n'est pas trouvee sur la page, le produit est ignore."
        ),
    )
    # Option --output : repertoire de destination des images (defaut: ./images_dl)
    parser.add_argument("--output", default="./images_dl", help="Repertoire cible")
    # Option --headless : lance Chrome sans fenetre visible
    parser.add_argument("--headless", action="store_true", help="Executer en arriere-plan sans interface")
    # Option --dry-run : simulation sans telechargement
    parser.add_argument("--dry-run", action="store_true", help="Effectuer une simulation sans telecharger")

    # Parse les arguments passes en ligne de commande
    args = parser.parse_args()
    # Active le mode RACE si --urls ou --sites est passe
    use_race = args.urls is not None or args.sites is not None
    # Recupere les URLs personnalisees (liste vide si --urls sans argument)
    custom_urls = args.urls if args.urls else []
    # Ajoute les sites personnalises a la liste des URLs
    if args.sites:
        custom_urls.extend(args.sites)
    # Convertit le chemin de sortie en objet Path
    output_base = Path(args.output)
    # Recupere le nom de la marque (nettoye des espaces)
    brand = args.brand.strip()

    # Lance le mode de traitement correspondant
    if args.excel:
        # Mode 2 : traitement batch Excel + export Odoo
        run_excel_batch(args.excel, output_base, args.headless, args.dry_run, use_race, custom_urls, brand=brand)
    else:
        # Mode 1 : traitement d'un SKU unique
        run_single(args.sku.strip(), output_base, args.headless, args.dry_run, use_race, custom_urls, brand=brand)

    # Message de fin si tout s'est bien passe
    print("  Operation terminee avec succes.\n")


# Point d'entree du script : execute main() uniquement si lance directement
if __name__ == "__main__":
    main()
