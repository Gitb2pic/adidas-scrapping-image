"""
Configuration globale du scraper.

Ce module centralise toutes les constantes utilisees par le scraper :
- Les URLs de recherche par defaut
- Les headers HTTP pour le telechargement
- Les noms de colonnes pour l'export Odoo 18
- Les selecteurs CSS pour detecter les liens produits sur tout site
"""

# ================================================================
# URLs de recherche par defaut
# ================================================================

# Liste des URLs utilisees pour chercher un produit par SKU.
# Le placeholder {sku} sera remplace par la reference du produit.
# Le placeholder {brand} sera remplace par le nom de la marque (ou supprime si vide).
DEFAULT_URLS = [
    # Recherche Google Images pour trouver le produit sur n'importe quel site
    "https://www.google.com/search?q={brand}+{sku}+product&udm=2",
    # Recherche sur le site Mostly Heard Rarely Seen 8-Bit (Shopify)
    "https://mostlyheardrarelyseen8bit.com/search?q={sku}",
    # Recherche sur Farfetch (marketplace mode luxe)
    "https://www.farfetch.com/be/search?q={sku}",
]

# ================================================================
# Headers HTTP pour le telechargement d'images
# ================================================================

# Headers envoyes avec chaque requete de telechargement d'image.
# Simule un navigateur reel pour eviter le blocage par les serveurs.
DOWNLOAD_HEADERS = {
    # User-Agent Chrome sur Windows 10 pour simuler un vrai navigateur
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    # Referer Google pour simuler une visite venant d'un moteur de recherche
    "Referer": "https://www.google.com/",
}

# ================================================================
# Noms de colonnes pour l'export Odoo 18
# ================================================================

# Colonne contenant la reference interne (SKU) du produit
ODOO_SKU_COLUMN = "Internal Reference"
# Colonne ou sera inscrit le nom du fichier image telecharge
ODOO_IMG_COLUMN = "Variant Image"
# Colonne contenant l'identifiant externe Odoo
ODOO_EXT_COLUMN = "External ID"
# Colonne contenant les valeurs de variantes (taille, couleur, etc.)
ODOO_VAR_COLUMN = "Variant Values"

# ================================================================
# Selecteurs CSS pour detecter les liens produits
# ================================================================

# Liste ordonnee de selecteurs CSS utilises pour trouver un lien
# vers une page produit sur n'importe quel site e-commerce.
# Les selecteurs sont testes du plus specifique au plus generique.
PRODUCT_LINK_SELECTORS = [
    # --- Selecteurs specifiques e-commerce ---
    # Shopify : lien grille de produits
    "a.grid-view-item__link",
    # Carte produit generique
    "a.product-card",
    # Shopify : lien grille alternative
    "a.grid-product__link",
    # Lien d'article produit
    "a.product-item__link",
    # Attribut data-testid pour les sites modernes (React, etc.)
    "a[data-testid='product-card-link']",
    # Classe contenant "product-card" (match partiel)
    "a[class*='product-card']",
    # Lien a l'interieur d'une div carte produit
    "div[class*='product-card'] a",
    # Lien produit generique
    "a[class*='product-link']",
    # Article produit generique
    "a[class*='product-item']",
    # Tuile produit (Amazon, Zalando, etc.)
    "a[class*='product-tile']",
    # --- Selecteurs generiques (tout site) ---
    # Lien dont l'URL contient "/product"
    "a[href*='/product']",
    # Lien dont l'URL contient "/products/" (Shopify standard)
    "a[href*='/products/']",
    # Lien court "/p/" (Zara, H&M, etc.)
    "a[href*='/p/']",
    # Lien "/item/" (eBay, etc.)
    "a[href*='/item/']",
    # Lien "/dp/" (Amazon)
    "a[href*='/dp/']",
    # Lien a l'interieur d'un conteneur avec classe "product"
    "[class*='product'] a[href]",
    # Lien a l'interieur d'un conteneur avec classe "item"
    "[class*='item'] a[href]",
    # Lien a l'interieur d'un conteneur avec classe "card"
    "[class*='card'] a[href]",
    # Lien a l'interieur d'un conteneur avec classe "tile"
    "[class*='tile'] a[href]",
    # Lien a l'interieur d'un element avec attribut data-product
    "[data-product] a[href]",
    # Lien a l'interieur d'un element avec attribut data-item
    "[data-item] a[href]",
]
