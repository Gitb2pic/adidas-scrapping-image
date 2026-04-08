"""
Gestion du navigateur Selenium Chrome.

Ce module fournit deux fonctions :
- build_driver()    : cree et configure une instance Chrome anti-detection
- accept_cookies()  : ferme automatiquement les bannieres de cookies
"""

import time  # Pour le delai apres le clic sur les cookies

# Imports Selenium pour le controle du navigateur
from selenium import webdriver                          # Classe principale du navigateur
from selenium.webdriver.chrome.service import Service   # Service Chrome (gere le processus chromedriver)
from selenium.webdriver.chrome.options import Options   # Options de configuration Chrome
from selenium.webdriver.common.by import By             # Methodes de localisation d'elements (CSS, ID, etc.)
from selenium.webdriver.support.ui import WebDriverWait # Attente explicite avec timeout
from selenium.webdriver.support import expected_conditions as EC  # Conditions d'attente (cliquable, visible, etc.)
from webdriver_manager.chrome import ChromeDriverManager  # Telecharge automatiquement le bon chromedriver


def build_driver(headless):
    """
    Cree une instance Chrome configuree pour eviter la detection anti-bot.

    Le navigateur est configure avec :
    - Un user-agent realiste (Chrome sur Windows 10)
    - La suppression des marqueurs d'automatisation Selenium
    - Une taille de fenetre fixe pour un rendu coherent

    Args:
        headless: Si True, le navigateur tourne en arriere-plan sans fenetre visible.

    Returns:
        Une instance webdriver.Chrome prete a naviguer.
    """
    # Creation de l'objet options pour configurer Chrome
    opts = Options()
    # Si headless, on utilise le nouveau mode headless de Chrome (plus stable)
    if headless:
        opts.add_argument("--headless=new")
    # Desactive le sandboxing (necessaire dans certains environnements Linux/Docker)
    opts.add_argument("--no-sandbox")
    # Evite les problemes de memoire partagee dans les conteneurs
    opts.add_argument("--disable-dev-shm-usage")
    # Desactive la detection automatique de Selenium par les sites
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # Taille de fenetre fixe pour un rendu coherent des pages
    opts.add_argument("--window-size=1400,900")
    # Supprime le flag "Chrome is being controlled by automated software"
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    # Desactive l'extension d'automatisation Chrome
    opts.add_experimental_option("useAutomationExtension", False)
    # User-Agent realiste pour simuler un vrai utilisateur Chrome
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    # Telecharge et installe automatiquement la bonne version de chromedriver
    service = Service(ChromeDriverManager().install())
    # Cree l'instance Chrome avec les options et le service configures
    driver = webdriver.Chrome(service=service, options=opts)
    # Injecte un script JS pour masquer la propriete navigator.webdriver
    # (les sites l'utilisent pour detecter Selenium)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    # Retourne le navigateur pret a l'emploi
    return driver


def accept_cookies(driver):
    """
    Tente de fermer la banniere de cookies si elle apparait.

    Cherche les boutons "Accepter" les plus courants sur les sites web
    (OneTrust, boutons data-testid, classes generiques).
    Si aucun bouton n'est trouve dans les 5 secondes, on passe sans erreur.

    Args:
        driver: L'instance Selenium Chrome active.
    """
    try:
        # Attend jusqu'a 5 secondes qu'un bouton d'acceptation de cookies soit cliquable
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    # OneTrust (utilise par beaucoup de sites)
                    "button#onetrust-accept-btn-handler, "
                    # Bouton avec attribut data-testid (sites React/modernes)
                    "button[data-testid='cookie-accept-button'], "
                    # Classe generique "accepter tout"
                    "button.btn-accept-all",
                )
            )
        )
        # Clic sur le bouton trouve
        btn.click()
        # Petit delai pour laisser la banniere se fermer
        time.sleep(1)
    except Exception:
        # Aucun bouton trouve ou timeout : on continue sans erreur
        pass
