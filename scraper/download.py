import urllib.request

from .config import DOWNLOAD_HEADERS
from .logger import log


def download_image(url, dest):
    req = urllib.request.Request(url, headers=DOWNLOAD_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        log(f"Echec du telechargement {dest.name} : {e}", "ERR")
        return False


def download_all(images, output_dir, sku):
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    preferred = None

    for idx, img in enumerate(images):
        url = img["url"]
        clean_url = url.split("?")[0]
        ext = clean_url.rsplit(".", 1)[-1] if "." in clean_url else "jpg"
        ext = ext if ext.lower() in {"jpg", "jpeg", "png", "webp"} else "jpg"

        fname = f"{sku.upper()}_{idx}.{ext}"
        dest = output_dir / fname

        log(f"Telechargement image[{idx}]: {fname}", "DL", sku=sku)
        if download_image(url, dest):
            log(f"OK : {dest.stat().st_size // 1024} KB", "OK", sku=sku)
            entry = {"filename": fname, "path": dest, "url": url, "index": idx}
            downloaded.append(entry)
            # Priorite a images[1] pour Excel, fallback images[0]
            if idx == 1:
                preferred = entry
            elif idx == 0 and preferred is None:
                preferred = entry
        else:
            log(f"Echec image[{idx}]", "WARN", sku=sku)

    if downloaded:
        log(f"{len(downloaded)}/{len(images)} image(s) telechargee(s)", "OK", sku=sku)
    else:
        log("Impossible de sauvegarder aucun fichier.", "ERR", sku=sku)

    return {"all": downloaded, "preferred": preferred}
