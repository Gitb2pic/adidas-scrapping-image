DEFAULT_URLS = [
    "https://www.google.com/search?q={sku}+product&udm=2",
    "https://mostlyheardrarelyseen8bit.com/search?q={sku}",
    "https://www.farfetch.com/be/search?q={sku}",
]

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.google.com/",
}

ODOO_SKU_COLUMN = "Internal Reference"
ODOO_IMG_COLUMN = "Variant Image"
ODOO_EXT_COLUMN = "External ID"
ODOO_VAR_COLUMN = "Variant Values"

# Selecteurs generiques pour detecter un lien produit sur n'importe quel site
PRODUCT_LINK_SELECTORS = [
    # Selecteurs specifiques e-commerce
    "a.grid-view-item__link",
    "a.product-card",
    "a.grid-product__link",
    "a.product-item__link",
    "a[data-testid='product-card-link']",
    "a[class*='product-card']",
    "div[class*='product-card'] a",
    "a[class*='product-link']",
    "a[class*='product-item']",
    "a[class*='product-tile']",
    # Selecteurs generiques (tout site)
    "a[href*='/product']",
    "a[href*='/products/']",
    "a[href*='/p/']",
    "a[href*='/item/']",
    "a[href*='/dp/']",
    "[class*='product'] a[href]",
    "[class*='item'] a[href]",
    "[class*='card'] a[href]",
    "[class*='tile'] a[href]",
    "[data-product] a[href]",
    "[data-item] a[href]",
]
