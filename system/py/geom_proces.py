import argparse
import numpy as np
from pathlib import Path
import cv2
import torch 
from geom_snap_matrix import create_debug_image
from geom_find_best_normal_regions import apply_dominant_normals, find_dominant_normal_directions
from geom_planes import create_plane_tensor, save_plane_debug
from geom_generate_poligon_base_on_planes import polygonize_planes, save_polygon_debug
from geom_plane_group import find_plane_groups, save_plane_groups_debug, save_plane_statistics, sort_and_filter
from geom_normal_base_on_dominant import create_group_normals
from geom_boundary import find_plane_boundary_directions, save_plane_boundaries_debug
from geom_poligon_from_boundaries import build_polygons_from_plane_boundaries, save_polygons_debug
from geom_find_plane_rectangle import find_plane_rectangles
from geom_rectangle_texture import create_rectangle_textures, save_rectangle_textures
from geom_save_glb import save_rectangles_to_glb


def load_output(path, device="cuda"):
    data = torch.load(path, map_location=device)

    return {
        "points": data["points"].float().to(device),
        "depth": data["depth"].float().to(device),
        "mask": data["mask"].bool().to(device),
        "normals": data["normals"].float().to(device),
    }


def save_dominant_directions_debug(
    labels,
    similarity,
    directions,
    output_path
):
    # GPU -> CPU
    if torch.is_tensor(labels):
        labels = labels.detach().cpu().numpy()

    if torch.is_tensor(similarity):
        similarity = similarity.detach().cpu().numpy()

    if torch.is_tensor(directions):
        directions = directions.detach().cpu().numpy()

    labels = np.asarray(labels)
    similarity = np.asarray(similarity)

    h, w = labels.shape

    # ---------------------------------------------------------
    # 1. REGIONY / DOMINUJĄCE KIERUNKI
    # ---------------------------------------------------------

    debug = np.zeros((h, w, 3), dtype=np.uint8)

    num_directions = len(directions)

    # Stała paleta kolorów
    colors = cv2.applyColorMap(
        np.linspace(0, 255, num_directions, dtype=np.uint8).reshape(-1, 1),
        cv2.COLORMAP_TURBO
    ).reshape(-1, 3)

    for i in range(num_directions):
        debug[labels == i] = colors[i]

    # -1 = brak przypisania
    debug[labels < 0] = (0, 0, 0)

    cv2.imwrite(
        str(output_path) + "_regions.png",
        debug
    )

    # ---------------------------------------------------------
    # 2. SIMILARITY
    # ---------------------------------------------------------

    sim = np.clip(similarity, 0.0, 1.0)

    sim_img = (sim * 255).astype(np.uint8)

    sim_img[labels < 0] = 0

    sim_img = cv2.applyColorMap(
        sim_img,
        cv2.COLORMAP_TURBO
    )

    cv2.imwrite(
        str(output_path) + "_similarity.png",
        sim_img
    )

    # ---------------------------------------------------------
    # 3. INFORMACJA TEKSTOWA
    # ---------------------------------------------------------

    print("Dominant directions:")

    for i, direction in enumerate(directions):
        print(
            f"{i:2d}: "
            f"[{direction[0]: .4f}, "
            f"{direction[1]: .4f}, "
            f"{direction[2]: .4f}]"
        )


def process(image_dir, data):
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
    
    # DEBUG image
    image_path = image_dir.parent / f"{image_dir.name}.png"
    image = cv2.imread(str(image_path))

    # ============================================================
    # 1. ZNAJDŹ DOMINUJĄCE KIERUNKI NORMAL
    # sprowadza normalne do kilku dominujących kierunków
    # ============================================================
    # directions: [N, 3] pixel_dirId: [H, W] similarity: [H, W] density: [N]
    print("Finding dominant normal directions...")
    ( directions, pixel_dirId, dir_similarity, dir_density ) = find_dominant_normal_directions(
        normals, mask,
        num_directions=15,
        angle_radius_deg=7.0,
        min_similarity=0.90
    )
    
    logfile = OUTPUT_DIR / f"{image_dir.name}_1_regions_by_normals.png"
    create_debug_image(pixel_dirId, logfile)
      
    #============================================================
    # 2. Zmień NORMALNE NA PODSTAWIE DOMINUJ
    # Zapisuje dominujące normalne w tensorze normalnych
    #===========================================================
    
    print("Applying dominant normals...")
    normals_consolidated = directions[pixel_dirId]
    #============================================================
    # Planes tensors
    # wykrywa płaszczyzny na podstawie dominujących normalnych i punktów 3D
    # Zwraca [W,H,4] tensor płaszczyzn w formie [nx, ny, nz, d] dla równania płaszczyzn Ax + By + Cz + D = 0
    #============================================================
    print("Creating planes tensor and saving debug images...")
    pixel_planes = create_plane_tensor(points, normals_consolidated, mask)
    print(f"Planes tensor shape: {pixel_planes.shape}")
    print(f"Planes count: {pixel_planes.shape[0] * pixel_planes.shape[1]}")
    logfile = OUTPUT_DIR / f"{image_dir.name}_3"
    save_plane_debug( pixel_planes, mask, logfile )
    
    #===========================================================
    # Plane grouping
    # grupuje płaszczyzny w oparciu o podobieństwo normalnych i odległość punktów
    # plane_labels [H, W] - etykiety grup płaszczyzn
    # plane_counts [N] - liczba punktów w każdej grupie
    # planes_consolidated [N, 4] [nx, ny, nz, d] - parametry płaszczyzn w formie Ax + By + Cz + D = 0
    #===========================================================
    print("Finding plane groups...")
    plane_labels, plane_counts, planes_consolidated = find_plane_groups(
        pixel_planes,
        pixel_dirId,
        directions,
        mask,
        distance_threshold=0.02,
        min_points=300
    )

    #===========================================================
    # Sort and filter planes
    # wybranie największych płaszczyzn
    #===========================================================
    plane_labels, planes_consolidated, plane_counts = sort_and_filter(plane_labels, planes_consolidated, plane_counts, limit = 10)

    print("Saving plane groups debug images...")
    logfile = OUTPUT_DIR / f"{image_dir.name}_4_plane_groups.txt"
    save_plane_statistics( plane_labels, plane_counts, planes_consolidated, logfile, top_n=200 )
    
    logfile = OUTPUT_DIR / f"{image_dir.name}_4_plane_groups"
    save_plane_groups_debug( plane_labels, plane_counts, planes_consolidated, image,  logfile, top_n=200 )
    
    #===========================================================
    # Plane rectangles
    # zwraca prostokątne regiony w obrębie płaszczyzn na podstawie ekstremów x,y,z
    #===========================================================
    print("Finding plane rectangles...")
    rectangles = find_plane_rectangles(
        points,
        plane_labels,
        planes_consolidated
    )
    print(f"Rectangles found: {len(rectangles)}")
    
    logdir = OUTPUT_DIR / f"{image_dir.name}_textures"
    textures = create_rectangle_textures(
        image,
        points,
        plane_labels,
        rectangles,
        texture_size=256
    )
    save_rectangle_textures(textures, logdir)
    
    print(f"Textures created: {len(textures)}")
    
    save_rectangles_to_glb(
        rectangles,
        textures,
        OUTPUT_DIR / f"{image_dir.name}_planes.glb",
    )
    
    exit()
    return
    #===========================================================
    # Boundary detection
    # wykrywa granice między płaszczyznami i zapisuje ich kierunki
    #===========================================================
    print("Finding plane boundary directions...")
    boundaries = find_plane_boundary_directions(
        plane_labels,
        min_boundary_pixels=20,
        num_directions=18
    )
    print(f"Boundaries found: {len(boundaries)}")
    save_plane_boundaries_debug(
        image,
        boundaries,
        OUTPUT_DIR / f"{image_dir.name}_5_boundaries.png",
        top_n=100,
        line_thickness=1,
    )
    
    polygons = build_polygons_from_plane_boundaries(
        plane_labels,
        boundaries,
        max_edges_per_plane=8,
        max_vertices=10,
        min_edge_length=30.0,
        intersection_tolerance=5.0
    )
    save_polygons_debug(
        image,
        polygons[:50],
        OUTPUT_DIR / f"{image_dir.name}_6_polygons.png",
    )
    
    return
    #===========================================================
    # Polygonization
    #===========================================================
    print("Polygonization...")
           
    
    poligon_debugpath = OUTPUT_DIR / f"{image_dir.name}_debug"
    poligon_debugpath.mkdir(parents=True, exist_ok=True)
    polygons = polygonize_planes(
        plane_labels,
        planes,
        min_region_size=500,
        smooth_radius=7,
        line_tolerance=3.0,
        min_segment_length=20,
        max_segment_length=250,
        segment_step=5,
        max_vertices=10,
        min_inlier_ratio=0.75,
        debug_dir=poligon_debugpath,
        debug_image=image,
    )

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


if __name__ == "__main__":
    main()