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

Requirements:
    pip install -r requirements.txt
"""

import sys
import argparse
from pathlib import Path

try:
    from scraper import run_single, run_excel_batch
except ImportError:
    print("\n[X] Dependances manquantes. Lancer d'abord :\n")
    print("    pip install -r requirements.txt\n")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Extracteur d'Images — Mode Unitaire | Mode Excel | Mode Asynchrone",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--sku", help="Reference unique, ex: MH03AC-T03RED")
    src.add_argument("--excel", help="Fichier source (doit contenir la colonne 'Internal Reference')")

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
    parser.add_argument("--output", default="./images_dl", help="Repertoire cible")
    parser.add_argument("--headless", action="store_true", help="Executer en arriere-plan sans interface")
    parser.add_argument("--dry-run", action="store_true", help="Effectuer une simulation sans telecharger")

    args = parser.parse_args()
    use_race = args.urls is not None or args.sites is not None
    custom_urls = args.urls if args.urls else []
    if args.sites:
        custom_urls.extend(args.sites)
    output_base = Path(args.output)

    if args.excel:
        run_excel_batch(args.excel, output_base, args.headless, args.dry_run, use_race, custom_urls)
    else:
        run_single(args.sku.strip(), output_base, args.headless, args.dry_run, use_race, custom_urls)

    print("  Operation terminee avec succes.\n")


if __name__ == "__main__":
    main()
