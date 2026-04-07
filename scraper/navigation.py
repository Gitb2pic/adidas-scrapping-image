import time
import threading
from concurrent.futures import ThreadPoolExecutor

from selenium.webdriver.common.by import By

from .config import DEFAULT_URLS, PRODUCT_LINK_SELECTORS
from .logger import log
from .driver import build_driver, accept_cookies
from .images import extract_images


def navigate_single(driver, sku, url=None):
    search = (url or DEFAULT_URLS[0]).replace("{sku}", sku.upper())
    log(f"Recherche : {search}", sku=sku)
    driver.get(search)
    accept_cookies(driver)
    time.sleep(3)

    for selector in PRODUCT_LINK_SELECTORS:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            href = el.get_attribute("href")
            if href and href.startswith("http"):
                log(f"Produit detecte : {href}", sku=sku)
                driver.get(href)
                time.sleep(3)
                return True
        except Exception:
            continue

    log("Extraction directe depuis la page de recherche.", "INFO", sku=sku)
    return True


class RaceResult:
    def __init__(self):
        self.winner_url = None
        self.winner_images = []
        self.lock = threading.Lock()
        self.found = threading.Event()

    def claim(self, url, images):
        with self.lock:
            if not self.found.is_set():
                self.winner_url = url
                self.winner_images = images
                self.found.set()
                return True
        return False


def _race_worker(url, sku, headless, race):
    if race.found.is_set():
        return

    driver = None
    try:
        driver = build_driver(headless)
        log(f"[RACE] -> {url}", sku=sku)
        driver.get(url)
        accept_cookies(driver)
        time.sleep(3)

        if "404" in driver.title.lower():
            log(f"[RACE] Erreur 404 : {url}", "WARN", sku=sku)
            return

        if race.found.is_set():
            return

        # Essayer de naviguer vers une page produit
        for selector in PRODUCT_LINK_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                href = el.get_attribute("href")
                if href and href.startswith("http"):
                    log(f"[RACE] Produit detecte : {href}", sku=sku)
                    driver.get(href)
                    time.sleep(3)
                    break
            except Exception:
                continue

        if race.found.is_set():
            return

        images = extract_images(driver, sku)

        if images and not race.found.is_set():
            if race.claim(url, images):
                log(f"[RACE] SUCCES sur : {url}  ({len(images)} images)", "OK", sku=sku)
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
    expanded = [u.replace("{sku}", sku.upper()) for u in urls]
    race = RaceResult()
    log(f"[RACE] {len(expanded)} URLs en parallele", sku=sku)

    with ThreadPoolExecutor(max_workers=len(expanded)) as pool:
        for url in expanded:
            pool.submit(_race_worker, url, sku, headless, race)
        race.found.wait(timeout=timeout)

    if not race.found.is_set():
        log("Echec (timeout ou aucune source valide).", "ERR", sku=sku)
        return []

    return race.winner_images
