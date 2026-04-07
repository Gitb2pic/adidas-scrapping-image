import re
import json

from selenium.webdriver.common.by import By

from .logger import log


def get_high_res_url(url: str) -> str:
    if not url:
        return ""
    return re.sub(
        r'_([0-9]+x[0-9]*|[0-9]*x[0-9]+)(\.[a-zA-Z0-9]{3,4})',
        r'\2',
        url,
        flags=re.IGNORECASE,
    )


def is_valid_image(url: str) -> bool:
    url_lower = url.lower()
    clean = url.split("?")[0]

    excluded_patterns = [
        "/logo", "/icon", "/badge", "/banner",
        "/flag", "/avatar", "/favicon", "/sprite",
        "placeholder", "fallback", "default",
    ]
    if any(p in url_lower for p in excluded_patterns):
        return False

    if re.search(r'\.(jpg|jpeg|png|webp)$', clean, re.I):
        return True

    if "cdn.shopify.com" in url_lower or "/products/" in url_lower or "/files/" in url_lower:
        return True

    return False


def extract_images(driver, sku):
    images = []
    seen = set()

    def add(url, label):
        if url.startswith("//"):
            url = "https:" + url

        url = get_high_res_url(url)
        clean = url.split("?")[0]

        if clean in seen:
            return
        seen.add(clean)

        if is_valid_image(clean):
            images.append({"url": url, "label": label})

    # 1. HTML DOM
    try:
        selectors = [
            "img[class*='product']",
            "img[class*='grid']",
            "img[class*='card']",
            "a[class*='product'] img",
            "img",
        ]

        for sel in selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                for attr in ("src", "data-src", "srcset", "data-srcset"):
                    val = el.get_attribute(attr) or ""
                    if "srcset" in attr and val:
                        for part in val.split(","):
                            part_url = part.strip().split(" ")[0]
                            if part_url.startswith("http") or part_url.startswith("//"):
                                add(part_url, "html_srcset")
                    else:
                        if val.startswith("http") or val.startswith("//"):
                            add(val, "html_img")

        if images:
            log(f"{len(images)} image(s) valide(s) extraite(s) du visuel HTML", "OK", sku=sku)
            return images
    except Exception:
        pass

    # 2. Objets JSON imbriques
    for var in ("__NEXT_DATA__", "__STATE__", "__PRELOADED_STATE__", "__INITIAL_STATE__"):
        try:
            if var == "__NEXT_DATA__":
                el = driver.find_element(By.ID, var)
                raw = el.get_attribute("textContent")
            else:
                raw = driver.execute_script(f"return JSON.stringify(window.{var})")

            if raw:
                _walk_json(json.loads(raw), add)
                if images:
                    log(f"{len(images)} image(s) extraite(s) des donnees cachees {var}", "OK", sku=sku)
                    return images
        except Exception:
            pass

    # 3. Regex de secours
    cdn_re = re.compile(
        r'(?:https?:)?//[^\s"\'\\<>]+\.(?:jpg|jpeg|png|webp)', re.I
    )
    for m in cdn_re.finditer(driver.page_source):
        add(m.group(0), "regex_cdn")

    if images:
        log(f"{len(images)} image(s) valide(s) recuperee(s) par Regex", "OK", sku=sku)
    else:
        log("Aucune image valide trouvee sur cette page.", "WARN", sku=sku)

    return images


def _walk_json(node, callback):
    if isinstance(node, dict):
        for key in ("view_list", "images", "gallery_images", "media", "src", "url"):
            val = node.get(key)
            if isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, str) and (item.startswith("http") or item.startswith("//")):
                        callback(item, f"{key}_{i}")
                    elif isinstance(item, dict):
                        for k in ("image_url", "src", "url", "href"):
                            u = item.get(k, "")
                            if u and (u.startswith("http") or u.startswith("//")):
                                callback(u, f"{key}_{i}_{k}")
                                break
            elif isinstance(val, str) and (val.startswith("http") or val.startswith("//")):
                callback(val, f"json_direct_{key}")

        for v in node.values():
            _walk_json(v, callback)
    elif isinstance(node, list):
        for item in node:
            _walk_json(item, callback)
