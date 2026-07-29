import os
import time
from pathlib import Path
from tqdm import tqdm
import xai_sdk
from PIL import Image

client = xai_sdk.Client(api_key="xai-XXXXXXXXXXXXXXXXXXXXXXXX")

PROMPT = """
Create a clean, simplified vector-style technical drawing of only the building's 3D mass, visible walls, and roof. 
Remove ALL background, ground, doors, windows, balcony, solar panels and details. 
Fill all window and door areas with solid wall color so they disappear. 
Outline all walls and roof edges with thin black lines (~1px). 
Flat colors, minimalist architectural style.
"""

def process_image(image_path: str, output_dir: str):
    output_path = Path(output_dir) / f"processed_{Path(image_path).name}"
    
    # Wczytaj obraz jako base64 lub użyj URL (lepiej uploadować)
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    response = client.image.sample(
        model="grok-imagine-image",   # lub "grok-imagine-image-quality" (droższe)
        prompt=PROMPT,
        image=image_data,             # można też image_url
        resolution="1k",              # lub "2k"
    )
    
    # Zapisz wynik
    response.save(str(output_path))
    return output_path


def main():
    input_folder = "budynki_input"
    output_folder = "budynki_output"
    os.makedirs(output_folder, exist_ok=True)
    
    images = list(Path(input_folder).glob("*.jpg")) + list(Path(input_folder).glob("*.png"))
    
    print(f"Znaleziono {len(images)} zdjęć do przetworzenia.")
    
    for img_path in tqdm(images):
        try:
            process_image(str(img_path), output_folder)
            time.sleep(0.6)          # szacunek rate limit (bezpiecznie)
        except Exception as e:
            print(f"Błąd przy {img_path}: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()