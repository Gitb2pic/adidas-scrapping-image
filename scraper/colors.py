"""
Extraction du code couleur depuis les URLs de produits.

Ce module analyse les URLs de produits (Hugo Boss, revendeurs multimarques, etc.)
pour en extraire le code couleur selon deux patterns :

Pattern 1 — Liens officiels (Hugo Boss, etc.) :
    URL : https://www.hugoboss.com/veste/hbeu50530699_395.html
    Le code couleur (395) est situe entre le '_' et le '.html'.
    Regex : SKU 8 chiffres + '_' + code couleur 2-3 chiffres + '.html'

Pattern 2 — Liens revendeurs (Gomez.fr, etc.) :
    URL : https://gomez.fr/fr/product/boss-parlay-147-10228870-01-50467113-25
    Le code couleur (25) est situe apres le dernier '-' suivant le SKU 8 chiffres.
    Regex : SKU 8 chiffres + '-' + code couleur 2-3 chiffres en fin d'URL

Fonctions publiques :
- extract_color_code() : extrait le code couleur depuis une URL unique
- add_color_codes()    : applique l'extraction sur une colonne d'un DataFrame
"""

import re  # Expressions regulieres pour l'extraction des codes couleur

import pandas as pd  # Manipulation de DataFrames

# ================================================================
# Pattern 1 : Liens officiels (Hugo Boss, etc.)
# ================================================================
# Capture le code couleur (2-3 chiffres) entre '_' et '.html'
# Precede par un SKU de 8 chiffres commencant par 50
#
# Decomposition :
#   \d{8}   — SKU a 8 chiffres (ex: 50530699)
#   _        — tiret du bas separateur
#   (\d{2,3}) — CAPTURE : code couleur de 2 ou 3 chiffres (ex: 395)
#   \.html   — extension de la page
#
# Exemple : hbeu50530699_395.html -> capture '395'
PATTERN_OFFICIAL = re.compile(r'\d{8}_(\d{2,3})\.html', re.IGNORECASE)

# ================================================================
# Pattern 2 : Liens revendeurs (Gomez.fr, etc.)
# ================================================================
# Capture le code couleur (2-3 chiffres) apres le dernier '-' suivant le SKU
# Le code couleur est en toute fin d'URL (pas de '/' ou '?' apres)
#
# Decomposition :
#   \d{8}   — SKU a 8 chiffres (ex: 50467113)
#   -        — tiret classique separateur
#   (\d{2,3}) — CAPTURE : code couleur de 2 ou 3 chiffres (ex: 25)
#   $        — fin de la chaine (le code est tout a la fin de l'URL)
#
# Exemple : ...50467113-25 -> capture '25'
PATTERN_RESELLER = re.compile(r'\d{8}-(\d{2,3})$')


def extract_color_code(url):
    """
    Extrait le code couleur depuis une URL de produit.

    Teste le Pattern 1 (lien officiel) en priorite, puis le Pattern 2
    (lien revendeur) en fallback. Retourne None si aucun pattern ne matche.

    Args:
        url: L'URL du produit (str). Peut etre None ou NaN.

    Returns:
        Le code couleur (str de 2-3 chiffres) ou None si non detecte.
    """
    # Verifie que l'URL est une chaine valide (pas None, NaN, ou vide)
    if not isinstance(url, str) or not url.strip():
        return None

    # Supprime les parametres de requete et le fragment (tout apres '?' ou '#')
    clean_url = url.split("?")[0].split("#")[0].strip().rstrip("/")

    # Teste le Pattern 1 : lien officiel (SKU_CODE.html)
    match = PATTERN_OFFICIAL.search(clean_url)
    if match:
        # Retourne le code couleur capture (groupe 1)
        return match.group(1)

    # Teste le Pattern 2 : lien revendeur (SKU-CODE en fin d'URL)
    match = PATTERN_RESELLER.search(clean_url)
    if match:
        # Retourne le code couleur capture (groupe 1)
        return match.group(1)

    # Aucun pattern ne matche : retourne None
    return None


def _detect_url_column(df):
    """
    Detecte automatiquement la colonne contenant des URLs dans un DataFrame.

    Parcourt chaque colonne et compte le nombre de valeurs commencant par 'http'.
    Retourne la colonne avec le plus de correspondances.

    Args:
        df: Le DataFrame pandas a analyser.

    Returns:
        Le nom de la colonne contenant le plus d'URLs, ou None si aucune trouvee.
    """
    best_col = None
    best_count = 0
    for col in df.columns:
        # Compte les valeurs qui ressemblent a des URLs dans cette colonne
        count = df[col].astype(str).str.startswith("http").sum()
        if count > best_count:
            best_count = count
            best_col = col
    if best_col:
        print(f"  [AUTO] Colonne URL detectee : '{best_col}' ({best_count} URLs trouvees)")
    return best_col


def add_color_codes(df, url_column=None):
    """
    Ajoute une colonne 'Code_Couleur_Extrait' au DataFrame.

    Parcourt la colonne d'URLs et applique extract_color_code() sur chaque ligne.
    Les URLs sans code couleur detecte auront NaN dans la nouvelle colonne.
    Si url_column est None, detecte automatiquement la colonne contenant des URLs.

    Args:
        df:         Le DataFrame pandas contenant les donnees produit.
        url_column: Le nom de la colonne contenant les URLs (str).
                    Si None, detection automatique.

    Returns:
        Le DataFrame avec la nouvelle colonne 'Code_Couleur_Extrait' ajoutee.

    Raises:
        KeyError: Si la colonne url_column n'existe pas dans le DataFrame.
        ValueError: Si aucune colonne contenant des URLs n'est detectee.
    """
    # Si aucune colonne specifiee, detection automatique
    if not url_column:
        url_column = _detect_url_column(df)
        if not url_column:
            raise ValueError(
                "Aucune colonne contenant des URLs detectee. "
                "Specifiez le nom de la colonne avec --url-column."
            )

    # Verifie que la colonne URL existe dans le DataFrame
    if url_column not in df.columns:
        raise KeyError(
            f"Colonne '{url_column}' introuvable. "
            f"Colonnes disponibles : {list(df.columns)}"
        )

    # Applique extract_color_code() sur chaque URL de la colonne
    df["Code_Couleur_Extrait"] = df[url_column].apply(extract_color_code)

    # Compte les resultats pour le log
    total = len(df)
    found = df["Code_Couleur_Extrait"].notna().sum()
    print(f"  [OK] Code couleur extrait : {found}/{total} URLs traitees avec succes.")

    return df
