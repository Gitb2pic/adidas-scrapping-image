import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd

from .config import DEFAULT_URLS, ODOO_SKU_COLUMN
from .logger import log, banner
from .driver import build_driver, accept_cookies
from .images import extract_images
from .navigation import navigate_single, navigate_race
from .download import download_all
from .excel import export_odoo_excel


def scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls):
    urls = custom_urls if custom_urls else DEFAULT_URLS

    if use_race or len(urls) > 1:
        images = navigate_race(sku, urls, headless)
    else:
        driver = build_driver(headless)
        try:
            if not navigate_single(driver, sku, url=urls[0] if urls else None):
                return {"all": [], "preferred": None}
            accept_cookies(driver)
            time.sleep(2)
            images = extract_images(driver, sku)
        finally:
            driver.quit()

    if not images:
        log("Processus termine : Aucune image", "WARN", sku=sku)
        return {"all": [], "preferred": None}

    if dry_run:
        log(f"[DRY-RUN] Cible detectee : {images[0]['url']}", "OK", sku=sku)
        return {
            "all": [{"filename": "", "url": img["url"]} for img in images],
            "preferred": {
                "filename": "",
                "url": images[1]["url"] if len(images) > 1 else images[0]["url"],
            },
        }

    return download_all(images, output_base, sku)


def run_single(sku, output_base, headless, dry_run, use_race, custom_urls):
    mode = "RACE (Analyse multi-URL)" if use_race else "Sequentiel"
    banner(f"MODE 1 — SKU : {sku.upper()}  [{mode}]")
    result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls)
    if not result or not result.get("all"):
        sys.exit(1)


def run_excel_batch(excel_path, output_base, headless, dry_run, use_race, custom_urls):
    banner("MODE 2 — Lecture Excel et creation du fichier Odoo")

    df = pd.read_excel(excel_path, dtype=str)
    if ODOO_SKU_COLUMN not in df.columns:
        print(f"[X] Introuvable : Colonne '{ODOO_SKU_COLUMN}'. Options detectees : {list(df.columns)}")
        sys.exit(1)

    skus = df[ODOO_SKU_COLUMN].dropna().unique().tolist()
    log(f"Demarrage sur {len(skus)} element(s) unique(s) : {skus}")

    sku_files = {}

    for i, sku in enumerate(skus, 1):
        sku = str(sku).strip()
        print(f"\n[{i}/{len(skus)}] Element: {sku} {'─' * 35}")
        result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls)
        pref = result.get("preferred") if result else None
        sku_files[sku] = [pref["filename"]] if pref and pref.get("filename") else []

    if not dry_run:
        output_base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        odoo_path = output_base / f"odoo18_import_{ts}.xlsx"
        export_odoo_excel(df, sku_files, odoo_path)

        found = sum(1 for v in sku_files.values() if v)
        missed = [s for s, v in sku_files.items() if not v]
        print(f"\n  Bilan du traitement : {found}/{len(skus)} succes.")
        if missed:
            print(f"  Elements non resolus : {', '.join(missed)}")
        print(f"  Archive generee : {odoo_path.resolve()}\n")
