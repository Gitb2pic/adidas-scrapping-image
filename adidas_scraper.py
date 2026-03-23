#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         Adidas Image Scraper  —  3 modes                    ║
╠══════════════════════════════════════════════════════════════╣
║  MODE 1  SKU unique                                         ║
║    python adidas_scraper.py --sku HT3463                    ║
║                                                              ║
║  MODE 2  Batch depuis Excel  +  export Odoo 18              ║
║    python adidas_scraper.py --excel variants.xlsx           ║
║                                                              ║
║  MODE 3  Multi-URL async (course, premier gagne)            ║
║    python adidas_scraper.py --sku HT3463 --urls             ║
║        https://www.adidas.co.uk/{sku}.html                  ║
║        https://www.adidas.com/us/{sku}.html                 ║
║        https://www.adidas.fr/{sku}.html                     ║
║                                                              ║
║  Options : --output ./images  --headless  --dry-run         ║
╚══════════════════════════════════════════════════════════════╝

Requirements:
    pip install selenium webdriver-manager openpyxl pandas
"""

import os
import re
import sys
import json
import time
import argparse
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("\n[X] Dependances manquantes. Lance d'abord :\n")
    print("    pip install selenium webdriver-manager openpyxl pandas\n")
    sys.exit(1)

try:
    import pandas as pd
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ================================================================
# CONFIG
# ================================================================

DEFAULT_URLS = [
    "https://www.adidas.co.uk/search?q={sku}",
    "https://www.adidas.com/us/search?q={sku}",
    "https://www.adidas.fr/search?q={sku}",
    "https://www.adidas.de/search?q={sku}",
    "https://www.adidas.co.uk/search?q={sku}",
    "https://www.adidas.com/us/search?q={sku}",
    "https://www.adidas.com/om/en/search?q={sku}",
    "https://www.adidas.com/om/en/search?q={sku}",
]

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.adidas.co.uk/",
}

ODOO_SKU_COLUMN = "Internal Reference"
ODOO_IMG_COLUMN = "Variant Image"
ODOO_EXT_COLUMN = "External ID"
ODOO_VAR_COLUMN = "Variant Values"


# ================================================================
# LOGGING (thread-safe)
# ================================================================

_log_lock = threading.Lock()

def log(msg, level="INFO", sku=""):
    icons = {"INFO": "i ", "OK": "OK", "WARN": "! ", "ERR": "X ", "DL": "->"}
    prefix = f"[{sku}] " if sku else ""
    with _log_lock:
        print(f"  [{icons.get(level, '  ')}] {prefix}{msg}")

def banner(text):
    bar = "=" * 60
    print(f"\n{bar}\n  {text}\n{bar}\n")


# ================================================================
# SELENIUM DRIVER
# ================================================================

def build_driver(headless):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1400,900")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
    )
    return driver


def accept_cookies(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "button#onetrust-accept-btn-handler, "
                "button[data-testid='cookie-accept-button'], "
                "button.btn-accept-all"
            ))
        )
        btn.click()
        time.sleep(1)
    except Exception:
        pass


# ================================================================
# EXTRACTION D'IMAGES
# ================================================================

def extract_images(driver, sku):
    images = []
    seen   = set()

    def add(url, label):
        clean = url.split("?")[0]
        if clean and clean not in seen and "adidas" in clean:
            seen.add(clean)
            images.append({"url": clean, "label": label})

    # 1. __NEXT_DATA__
    try:
        el   = driver.find_element(By.ID, "__NEXT_DATA__")
        data = json.loads(el.get_attribute("textContent"))
        _walk_json(data, add)
        if images:
            return images
    except Exception:
        pass

    # 2. window state objects
    for var in ("__STATE__", "__PRELOADED_STATE__", "__INITIAL_STATE__"):
        try:
            raw = driver.execute_script(f"return JSON.stringify(window.{var})")
            if raw:
                _walk_json(json.loads(raw), add)
                if images:
                    return images
        except Exception:
            pass

    # 3. Balises img + scroll lazy-load
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        for sel in [
            "img[data-testid='pdp-gallery-image']",
            "img[class*='gallery']",
            "img[class*='product-image']",
            "div[class*='gallery'] img",
            "div[class*='carousel'] img",
            "img[src*='adidas']",
        ]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                for attr in ("src", "data-src", "data-original"):
                    val = el.get_attribute(attr) or ""
                    if val.startswith("http"):
                        add(val, "img_tag")
        if images:
            return images
    except Exception:
        pass

    # 4. Regex CDN
    cdn_re = re.compile(
        r'https://assets\.adidas\.com/images/[^\s"\'\\<>]+\.(?:jpg|jpeg|png|webp)'
    )
    for m in cdn_re.finditer(driver.page_source):
        add(m.group(0), "regex_cdn")

    return images


def _walk_json(node, callback):
    if isinstance(node, dict):
        for key in ("view_list", "images", "gallery_images", "media"):
            val = node.get(key)
            if isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, str) and item.startswith("http"):
                        callback(item, f"{key}_{i}")
                    elif isinstance(item, dict):
                        for k in ("image_url", "src", "url", "href"):
                            u = item.get(k, "")
                            if u and u.startswith("http"):
                                callback(u, f"{key}_{i}_{k}")
                                break
        for v in node.values():
            _walk_json(v, callback)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, callback)


# ================================================================
# MODE 1 : Navigation sequentielle (SKU unique)
# ================================================================

def navigate_single(driver, sku):
    direct = f"https://www.adidas.co.uk/search?q={sku.upper()}"
    log(f"Navigation directe : {direct}", sku=sku)
    driver.get(direct)
    time.sleep(3)

    if "404" not in driver.title.lower() and sku.upper() in driver.current_url.upper():
        log("Page produit OK", "OK", sku=sku)
        return True

    search = f"https://www.adidas.co.uk/search?q={sku.upper()}"
    log(f"Recherche : {search}", sku=sku)
    driver.get(search)
    accept_cookies(driver)
    time.sleep(3)

    try:
        first = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR,
                "a.glass-product-card__assets-link, "
                "a[data-testid='product-card-link'], "
                "a[class*='product-card'], "
                "div[class*='product-card'] a"
            ))
        )
        href = first.get_attribute("href")
        log(f"Premier resultat : {href}", sku=sku)
        driver.get(href)
        time.sleep(3)
        return True
    except Exception as e:
        log(f"Introuvable : {e}", "ERR", sku=sku)
        return False


# ================================================================
# MODE 3 : Multi-URL ASYNC (course, premier gagnant)
# ================================================================

class RaceResult:
    def __init__(self):
        self.winner_url    = None
        self.winner_images = []
        self.lock          = threading.Lock()
        self.found         = threading.Event()

    def claim(self, url, images):
        with self.lock:
            if not self.found.is_set():
                self.winner_url    = url
                self.winner_images = images
                self.found.set()
                return True
        return False


def _race_worker(url, sku, headless, race):
    """Thread worker : ouvre Chrome, charge l'URL, extrait les images."""
    if race.found.is_set():
        return  # Deja gagne

    driver = None
    try:
        driver = build_driver(headless)
        log(f"[RACE] -> {url}", sku=sku)
        driver.get(url)
        accept_cookies(driver)
        time.sleep(3)

        if "404" in driver.title.lower():
            log(f"[RACE] 404 : {url}", "WARN", sku=sku)
            return

        if race.found.is_set():
            return

        images = extract_images(driver, sku)

        if images and not race.found.is_set():
            if race.claim(url, images):
                log(f"[RACE] GAGNANT : {url}  ({len(images)} images)", "OK", sku=sku)
        else:
            log(f"[RACE] Aucune image : {url}", "WARN", sku=sku)

    except Exception as e:
        if not race.found.is_set():
            log(f"[RACE] Erreur {url} : {e}", "WARN", sku=sku)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def navigate_race(sku, urls, headless, timeout=90):
    """
    Lance tous les URLs en parallele dans des threads independants.
    Des qu'un thread trouve des images, on retourne immediatement.
    Les autres threads continuent en arriere-plan puis se ferment.
    """
    expanded = [u.replace("{sku}", sku.upper()) for u in urls]
    race = RaceResult()

    log(f"[RACE] {len(expanded)} URLs en parallele pour {sku}", sku=sku)

    with ThreadPoolExecutor(max_workers=len(expanded)) as pool:
        for url in expanded:
            pool.submit(_race_worker, url, sku, headless, race)
        # Attendre le premier gagnant ou le timeout
        race.found.wait(timeout=timeout)

    if not race.found.is_set():
        log("Aucun URL n'a trouve d'images (timeout).", "ERR", sku=sku)
        return []

    return race.winner_images


# ================================================================
# TELECHARGEMENT
# ================================================================

def download_image(url, dest):
    req = urllib.request.Request(url, headers=DOWNLOAD_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        log(f"Echec {dest.name} : {e}", "ERR")
        return False


def download_all(images, output_dir, sku):
    """
    Telecharge uniquement la 1ere image.
    Nom du fichier = SKU.ext  (ex: HT3463.jpg)
    Retourne une liste avec 1 dict : { "filename", "path", "url" }
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    log(f"Dossier : {output_dir.resolve()}")

    img = images[0]
    url = img["url"]
    ext = url.rsplit(".", 1)[-1] if "." in url else "jpg"
    ext = ext if ext in {"jpg", "jpeg", "png", "webp"} else "jpg"
    fname = f"{sku.upper()}.{ext}"
    dest  = output_dir / fname

    log(f"{fname}", "DL", sku=sku)
    if download_image(url, dest):
        log(f"{dest.stat().st_size // 1024} KB", "OK", sku=sku)
        return [{"filename": fname, "path": dest, "url": url}]
    return []


# ================================================================
# EXPORT ODOO 18
# ================================================================

def export_odoo_excel(df, sku_files, output_path):
    """
    Genere un fichier Excel compatible import Odoo 18.
    Colonne 'Variant Image' = nom du fichier image telecharge (ex: HT3463_01_view_list_0.jpg).
    sku_files : { 'HT3463': ['HT3463_01_...jpg', 'HT3463_02_...jpg', ...] }
    """
    out = df.copy()
    if ODOO_IMG_COLUMN not in out.columns:
        out[ODOO_IMG_COLUMN] = ""

    # Pour chaque ligne on met le 1er fichier telecharge pour ce SKU
    out[ODOO_IMG_COLUMN] = out[ODOO_SKU_COLUMN].apply(
        lambda sku: sku_files.get(str(sku).strip(), [""])[0]
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "product.product"

    headers = list(out.columns)
    hdr_fill = PatternFill("solid", start_color="1D3557")
    hdr_font = Font(bold=True, color="FFFFFF", name="Arial", size=10)
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for ci, col in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=col)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = hdr_align

    alt_fill  = PatternFill("solid", start_color="F0F4F8")
    ok_fill   = PatternFill("solid", start_color="D4EDDA")
    miss_fill = PatternFill("solid", start_color="FFF3CD")
    norm_font = Font(name="Arial", size=9)
    img_ci    = headers.index(ODOO_IMG_COLUMN) + 1

    for ri, row in enumerate(out.itertuples(index=False), 2):
        for ci, value in enumerate(row, 1):
            val = "" if str(value) in ("nan", "None") else str(value)
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = norm_font
            c.alignment = Alignment(vertical="center")
            if ci == img_ci:
                # Vert si un nom de fichier est present, orange sinon
                c.fill = ok_fill if val and not val in ("nan", "None", "") else miss_fill
            elif ri % 2 == 0:
                c.fill = alt_fill

    col_widths = {
        ODOO_EXT_COLUMN: 45,
        ODOO_SKU_COLUMN: 20,
        ODOO_VAR_COLUMN: 18,
        ODOO_IMG_COLUMN: 70,
    }
    for ci, col in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = col_widths.get(col, 20)

    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    # Feuille resume
    ws2 = wb.create_sheet("Resume")
    ws2["A1"] = "Scraping Adidas -> Odoo 18"
    ws2["A1"].font = Font(bold=True, size=14, name="Arial")
    ws2["A3"] = "Genere le"
    ws2["B3"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    ws2["A4"] = "SKUs traites"
    ws2["B4"] = len(sku_files)
    ws2["A5"] = "SKUs avec images"
    ws2["B5"] = sum(1 for v in sku_files.values() if v)
    ws2["A6"] = "Variantes mises a jour"
    img_col_letter = get_column_letter(img_ci)
    n_rows = len(out) + 1
    ws2["B6"] = f"=COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.jpg\")+COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.png\")+COUNTIF('product.product'!{img_col_letter}2:{img_col_letter}{n_rows},\"*.webp\")"
    ws2["A7"] = "Variantes sans image"
    ws2["B7"] = f"=B4-B5"
    for cell in ["A3","A4","A5","A6","A7"]:
        ws2[cell].font = Font(bold=True, name="Arial", size=10)
    ws2.column_dimensions["A"].width = 25
    ws2.column_dimensions["B"].width = 30

    wb.save(str(output_path))
    log(f"Export Odoo 18 : {output_path.resolve()}", "OK")


# ================================================================
# ORCHESTRATION
# ================================================================

def scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls):
    """
    Retourne une liste de dicts { filename, path, url }
    ou une liste d'URLs (dry-run).
    """
    urls = custom_urls if custom_urls else DEFAULT_URLS

    if use_race:
        images = navigate_race(sku, urls, headless)
    else:
        driver = build_driver(headless)
        try:
            if not navigate_single(driver, sku):
                return []
            accept_cookies(driver)
            time.sleep(2)
            images = extract_images(driver, sku)
        finally:
            driver.quit()

    if not images:
        log("Aucune image trouvee.", "WARN", sku=sku)
        return []

    if not dry_run:
        return download_all(images, output_base, sku)
    else:
        for i, img in enumerate(images, 1):
            print(f"    {i:>2}. {img['url'][:80]}")
        return [{"filename": "", "url": img["url"]} for img in images]


def run_single(sku, output_base, headless, dry_run, use_race, custom_urls):
    mode = "RACE multi-URL" if use_race else "sequentiel"
    banner(f"MODE 1 — SKU : {sku.upper()}  [{mode}]")
    result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls)
    if not result:
        sys.exit(1)


def run_excel_batch(excel_path, output_base, headless, dry_run, use_race, custom_urls):
    if not HAS_PANDAS:
        print("[X] pandas/openpyxl requis : pip install pandas openpyxl")
        sys.exit(1)
    banner("MODE 2 — Batch Excel + Export Odoo 18")

    df = pd.read_excel(excel_path, dtype=str)
    if ODOO_SKU_COLUMN not in df.columns:
        print(f"[X] Colonne '{ODOO_SKU_COLUMN}' introuvable. Colonnes : {list(df.columns)}")
        sys.exit(1)

    skus = df[ODOO_SKU_COLUMN].dropna().unique().tolist()
    log(f"{len(skus)} SKU(s) : {skus}")

    # sku_files : { "HT3463": ["HT3463_01_view_list_0.jpg", "HT3463_02_...jpg", ...] }
    sku_files = {}

    for i, sku in enumerate(skus, 1):
        sku = str(sku).strip()
        print(f"\n[{i}/{len(skus)}] SKU: {sku} {'─'*40}")
        result = scrape_sku(sku, output_base, headless, dry_run, use_race, custom_urls)
        # result = liste de dicts { filename, path, url }
        sku_files[sku] = [r["filename"] for r in result if r.get("filename")]

    if not dry_run:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        odoo_path = output_base / f"odoo18_import_{ts}.xlsx"
        output_base.mkdir(parents=True, exist_ok=True)
        export_odoo_excel(df, sku_files, odoo_path)
        print(f"\n  Fichier Odoo 18 pret : {odoo_path.resolve()}\n")


# ================================================================
# MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Adidas Image Scraper — SKU unique | Batch Excel | Multi-URL async",
        formatter_class=argparse.RawTextHelpFormatter
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--sku",   help="SKU unique, ex: HT3463")
    src.add_argument("--excel", help="Fichier Excel Odoo (colonne 'Internal Reference')")

    parser.add_argument(
        "--urls", nargs="*", metavar="URL",
        help=(
            "URLs a tester en parallele (mode course async).\n"
            "Utilisez {sku} comme placeholder :\n"
            "  --urls https://www.adidas.co.uk/search?q={sku}\n"
            "         https://www.adidas.com/us/search?q={sku}\n"
            "Sans valeur = URLs par defaut (6 regions)."
        )
    )
    parser.add_argument("--output",   default="./adidas_images", help="Dossier de sortie")
    parser.add_argument("--headless", action="store_true",        help="Chrome sans fenetre")
    parser.add_argument("--dry-run",  action="store_true",        help="Liste sans telecharger")

    args    = parser.parse_args()
    use_race    = args.urls is not None
    custom_urls = args.urls if args.urls else []
    output_base = Path(args.output)

    if args.excel:
        run_excel_batch(args.excel, output_base, args.headless, args.dry_run, use_race, custom_urls)
    else:
        run_single(args.sku.strip(), output_base, args.headless, args.dry_run, use_race, custom_urls)

    print("  Termine.\n")


if __name__ == "__main__":
    main()