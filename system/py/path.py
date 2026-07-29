from pathlib import Path
import re


def ObjectIdFromMaskPath(path):
    """
    Pobiera ID obiektu z nazwy pliku.

    Przykłady:
        masks/mask_000123.png -> 123
        C:/project/masks/mask_15.png -> 15

    Zwraca:
        int - ID obiektu
        None - jeżeli nie znaleziono ID
    """
    filename = Path(path).name
    match = re.search(r"mask_(\d+)", filename)
    if match:
        return int(match.group(1))
    return None