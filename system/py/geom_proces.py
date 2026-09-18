import time
_start_time = time.perf_counter()
_frame_time = _start_time
_last_logtime = _start_time

import argparse
import numpy as np
from pathlib import Path
import cv2
import torch 
from geom_snap_matrix import create_debug_image
from geom_find_best_normal_regions import find_dominant_normal_directions, filter_direction_components, filter_top_directions
from geom_planes import create_plane_tensor, save_plane_debug
from geom_generate_poligon_base_on_planes import polygonize_planes
from geom_plane_group import find_plane_groups, save_plane_groups_debug, save_plane_statistics, sort_and_filter
from geom_boundary import find_plane_boundary_directions, save_plane_boundaries_debug
from geom_poligon_from_boundaries import build_polygons_from_plane_boundaries, save_polygons_debug
from geom_find_plane_rectangle import find_plane_rectangles
from geom_rectangle_texture import create_rectangle_textures, save_rectangle_textures, analyze_texture_coverage
from geom_save_glb import save_rectangles_to_glb
from save_glb import save_dominant_normal_pixels_to_glb

def logtime(functionName, counterType="last_invoke"):
    global _last_logtime, _frame_time

    now = time.perf_counter()

    if counterType == "last_invoke":
        elapsed = now - _last_logtime
        _last_logtime = now

    elif counterType == "frame":
        elapsed = now - _frame_time
        _frame_time = now
        _last_logtime = now

    elif counterType == "from_start":
        elapsed = now - _start_time

    else:
        raise ValueError(
            f"Nieznany counterType: {counterType}"
        )

    total_ms = int(elapsed * 1000)
    minutes = total_ms // 60000
    seconds = (total_ms % 60000) // 1000
    milliseconds = total_ms % 1000
    color = counterType == "last_invoke" and 93 or counterType == "frame" and 92 or 0
    print(f"Czas trwania '{functionName}': \033[{color}m{minutes:02d}:{seconds:02d}:{milliseconds:03d}\033[0m")

def load_output(path, device="cuda"):
    data = torch.load(path, map_location=device)

    return {
        "points": data["points"].float().to(device),
        "depth": data["depth"].float().to(device),
        "mask": data["mask"].bool().to(device),
        "normals": data["normals"].float().to(device),
    }

def process(image_dir, data, logEnabled=False):
    """
    Tutaj wykonujemy właściwe operacje na:
        data["points"]
        data["depth"]
        data["mask"]
        data["normals"]
    """

    points = data["points"]
    depth = data["depth"]
    mask = data["mask"]
    normals = data["normals"] # [H, W, 3]

    OUTPUT_DIR = image_dir.parent.parent / "geometry"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    image_path = image_dir.parent / f"{image_dir.name}.png"
    image = cv2.imread(str(image_path))
    
    if logEnabled:
        logtime("Ładowanie klatki")
    # DEBUG image
        
    # ============================================================
    # 1. ZNAJDŹ DOMINUJĄCE KIERUNKI NORMAL
    # sprowadza normalne do kilku dominujących kierunków
    # ============================================================
    # directions: [N, 3] pixel_dirId: [H, W] similarity: [H, W] density: [N]
    if logEnabled:
        print("Finding dominant normal directions...")
    ( directions, pixel_dirId, dir_similarity, dir_density ) = find_dominant_normal_directions(
        normals, mask,
        num_directions=15,
        angle_radius_deg=7.0,
        min_similarity=0.90
    )
    if logEnabled:
        logtime("find_dominant_normal_directions")
    # print(f"Liczba rozpoznanych kierunków: {len(directions)}")
    
    # directions, pixel_dirId, dir_similarity, dir_density = filter_top_directions( directions, pixel_dirId, dir_similarity, dir_density,
    #     top_n=2 )
    
    # logfile = OUTPUT_DIR / f"{image_dir.name}_1_regions_by_normals.png"
    # create_debug_image(pixel_dirId, logfile)
      
    #============================================================
    # 1.5 Filtrowanie
    #============================================================
    pixel_dirId = filter_direction_components( pixel_dirId, min_component_size=100 )
    if logEnabled:
        logtime("filter_direction_components")

    
    #============================================================
    # 2. Zmień NORMALNE NA PODSTAWIE DOMINUJ
    # Zapisuje dominujące normalne w tensorze normalnych
    # normals_consolidated: [H, W, 3]
    #===========================================================
    print("Applying dominant normals...")
    normals_consolidated = torch.zeros_like(normals)
    valid = pixel_dirId >= 0
    normals_consolidated[valid] = directions[pixel_dirId[valid]]
    if logEnabled:
        logtime("normals_consolidated")

    # Debug
    # save_dominant_normal_pixels_to_glb( points, normals_consolidated, OUTPUT_DIR / f"{image_dir.name}_dominant_normal_pixels.glb", size=0.05, )
    
    #============================================================
    # 3. Planes tensors
    # wykrywa płaszczyzny na podstawie dominujących normalnych i punktów 3D
    # Zwraca [W,H,4] tensor płaszczyzn w formie [nx, ny, nz, d] dla równania płaszczyzn Ax + By + Cz + D = 0
    #============================================================
    if logEnabled:
        print("Creating planes tensor and saving debug images...")
    pixel_planes = create_plane_tensor(points, normals_consolidated)
    logtime("create_plane_tensor")
    
    
    # import trimesh
    # scene = trimesh.load(OUTPUT_DIR / f"{image_dir.name}_pixel_planes.glb")
    # scene.show()
    
    if logEnabled:
        logfile = OUTPUT_DIR / f"{image_dir.name}_3"
        save_plane_debug( pixel_planes, mask, logfile )
        logtime("save_plane_debug( pixel_planes, mask, logfile )")
    
    #===========================================================
    # 4. Plane grouping
    # grupuje płaszczyzny w oparciu o podobieństwo normalnych i odległość punktów
    # plane_labels [H, W] - etykiety grup płaszczyzn
    # plane_counts [N] - liczba punktów w każdej grupie
    # planes_consolidated [N, 4] [nx, ny, nz, d] - parametry płaszczyzn w formie Ax + By + Cz + D = 0
    #===========================================================
    print("Finding plane groups...")
    plane_labels, plane_counts, planes_consolidated = find_plane_groups(
        pixel_planes,
        normals_consolidated,
        distance_threshold=0.002,
        min_points=300
    )
    if logEnabled:
        logtime("find_plane_groups")    
        print(f"Liczba rozpoznanych płaszczyzn: {len(plane_labels)}")
    #===========================================================
    # Sort and filter planes
    # wybranie największych płaszczyzn
    #===========================================================
    # plane_labels, planes_consolidated, plane_counts = sort_and_filter(
    #     plane_labels, 
    #     planes_consolidated, 
    #     plane_counts, 
    #     limit = 100
    # )

    print("Saving plane groups debug images...")
    if logEnabled:
        logfile = OUTPUT_DIR / f"{image_dir.name}_4_plane_groups.txt"
        save_plane_statistics( plane_labels, plane_counts, planes_consolidated, logfile, top_n=2000 )
    
        logfile = OUTPUT_DIR / f"{image_dir.name}_4_plane_groups"
        save_plane_groups_debug( plane_labels, plane_counts, planes_consolidated, image,  logfile, top_n=2000 )
        logtime("save_plane_statistics")    
  
    #===========================================================
    # Plane rectangles
    # zwraca prostokątne regiony w obrębie płaszczyzn na podstawie ekstremów x,y,z
    #===========================================================
    if logEnabled:
        print("Finding plane rectangles...")
    rectangles = find_plane_rectangles(
        points,
        plane_labels,
        planes_consolidated
    )
    if logEnabled:
        print(f"Rectangles found: {len(rectangles)}")
        logtime("find_plane_rectangles")    
      
    textures, rectangles = create_rectangle_textures(
        image,
        points,
        plane_labels,
        rectangles,
        texture_size=512,
        min_coverage=1.0
    )
    logtime(f"Textured rectangles: {len(rectangles)}")        
    if logEnabled:
        logdir = OUTPUT_DIR / f"{image_dir.name}_textures"
        save_rectangle_textures(textures, logdir)
        logtime("save_rectangle_textures")
    
    # ===== Sorting planes =====
    coverage = analyze_texture_coverage(textures)
    from collections import Counter

    groups = Counter(
        round(x["image_percent"])
        for x in coverage["textures"]
    )

    if logEnabled:
        for percent, count in sorted(groups.items(), reverse=True):
            print(f"{percent:3d}%: {count} plane")
    
    if logEnabled:
        logtime("Sorting planes")
    
    save_rectangles_to_glb(
        rectangles,
        textures,
        OUTPUT_DIR / f"{image_dir.name}_planes.glb",
    )
    logtime("save_rectangles_to_glb")

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Katalog ze zdjęciami"
    )

    args = parser.parse_args()
    logtime("Wczytywanie bibliotek")
    input_dir = args.input

    if not input_dir.is_dir():
        raise Exception(f"Input directory not found: {input_dir}")

    image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff"
    }

    images = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in image_extensions
    )

    print(f"Images found: {len(images)}")
    logtime("Przygotowywanie zdjęć")
    
    for image_path in images:

        # Podkatalog o nazwie takiej samej jak zdjęcie
        image_dir = image_path.with_suffix("")

        moge3_path = image_dir / "moge3.pt"

        if not moge3_path.exists():
            print(f"[SKIP] Missing: {moge3_path}")
            continue

        print(f"[PROCESS] {image_path.name}")

        data = load_output(moge3_path)
        print(f"Loaded data from {moge3_path}")
        process(
            image_dir,
            data
        )

        # Opcjonalnie zwolnij pamięć GPU
        del data
        torch.cuda.empty_cache()
        logtime(f"Frame \033[92m{image_path.name}\033[0m done", "frame")


if __name__ == "__main__":
    main()