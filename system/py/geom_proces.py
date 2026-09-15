import argparse
import numpy as np
from pathlib import Path
import cv2
import torch 
from geom_snap_matrix import create_debug_image
from geom_find_best_normal_regions import find_dominant_normal_directions
from geom_planes import create_plane_tensor, save_plane_debug
from geom_generate_poligon_base_on_planes import polygonize_planes, save_polygon_debug
from geom_plane_group import find_plane_groups, save_plane_groups_debug, save_plane_statistics
from geom_normal_base_on_dominant import create_group_normals


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
    normals = data["normals"]


    # ============================================================
    # 1. ZNAJDŹ DOMINUJĄCE KIERUNKI NORMAL
    # ============================================================
    (
        directions,
        labels,
        similarity,
        density
    ) = find_dominant_normal_directions(
        normals,
        mask,
        num_directions=15,
        angle_radius_deg=7.0,
        min_similarity=0.90
    )
    debug = create_debug_image(labels)
    OUTPUT_DIR = image_dir.parent.parent / "geometry"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(
        OUTPUT_DIR / f"{image_dir.name}_1_regions_by_normals.png",
        cv2.cvtColor(debug, cv2.COLOR_RGB2BGR)
    )
    
    new_normals, group_normals = create_group_normals(
        normals,
        labels,
        mask
    )

    print("Dominant directions found.")
        
    save_dominant_directions_debug(
        labels,
        similarity,
        directions,
        OUTPUT_DIR / f"{image_dir.name}_2"
    )
    
    #============================================================
    # Planes tensors
    #============================================================
    print("Creating planes tensor and saving debug images...")
    planes = create_plane_tensor(points, new_normals, mask)
    save_plane_debug(
        planes,
        mask,
        OUTPUT_DIR / f"{image_dir.name}_3"
    )
    
    #===========================================================
    # Plane grouping
    #===========================================================
    print("Finding plane groups...")
    plane_labels, plane_counts, planes_ = find_plane_groups(
        points,
        planes,
        mask,
        normal_angle_deg=5.0,
        distance_threshold=0.5,
        min_points=300
    )
    
    logfile = OUTPUT_DIR / f"{image_dir.name}_4_plane_groups.txt"
    save_plane_statistics(
        plane_labels,
        plane_counts,
        planes_,
        logfile,
        top_n=100
    )
    
    image_path = image_dir.parent / f"{image_dir.name}.png"
    image = cv2.imread(str(image_path))
    
    save_plane_groups_debug(
        plane_labels,
        plane_counts,
        planes_,
        image,
        OUTPUT_DIR / f"{image_dir.name}_4_planes",
        top_n=200
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