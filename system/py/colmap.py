from pathlib import Path
import subprocess
import time
import struct
import argparse
import sqlite3
from colmap_debug import draw_colmap_features, draw_colmap_3d_points

import argparse
parser = argparse.ArgumentParser()

parser.add_argument(
    "-i",
    required=True,
    help="Path to the input directory"
)
parser.add_argument(
    "--command",
    help="Path to the input directory"
)
args = parser.parse_args()

COLMAP = r"colmap.exe"
PROJECT = Path(args.i)
IMAGES = PROJECT / "frames"
DATABASE = PROJECT / "database.db"
SPARSE = PROJECT / "sparse"
DENSE = PROJECT / "dense"

COMMAND = args.command

def export_points_ply():
    points_file = SPARSE / "0" / "points3D.bin"
    if not points_file.exists():
        print("Brak points3D.bin")
        return
    import struct
    points = []
    with open(points_file, "rb") as f:
        count = struct.unpack(
            "<Q",
            f.read(8)
        )[0]
        for i in range(count):
            point_id = struct.unpack(
                "<Q",
                f.read(8)
            )[0]
            x,y,z = struct.unpack(
                "<ddd",
                f.read(24)
            )
            r,g,b = struct.unpack(
                "<BBB",
                f.read(3)
            )
            error = struct.unpack(
                "<d",
                f.read(8)
            )[0]
            track = struct.unpack(
                "<Q",
                f.read(8)
            )[0]
            f.seek(
                track * 8,
                1
            )
            points.append(
                (
                    x,y,z,
                    r,g,b
                )
            )

    out = PROJECT / "debug_points.ply"
    with open(out,"w") as f:
        f.write(
f"""ply
format ascii 1.0
element vertex {len(points)}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
"""
        )

        for p in points:
            f.write(
                f"{p[0]} {p[1]} {p[2]} "
                f"{p[3]} {p[4]} {p[5]}\n"
            )

    print()
    print("Saved:")
    print(out)
    print("points:", len(points))

def convert_sparse_to_txt():
    txt_path = SPARSE / "txt"
    if (txt_path / "points3D.txt").exists():
        return txt_path
    if not is_mapper_done():
        print("Brak modelu sparse/0")
        return None
    txt_path.mkdir(
        parents=True,
        exist_ok=True
    )
    run([
        COLMAP,
        "model_converter",
        "--input_path",
        SPARSE / "0",
        "--output_path",
        txt_path,
        "--output_type",
        "TXT"
    ])
    return txt_path

def points3d_stats(limit=10):
    points_file = SPARSE / "0" / "points3D.bin"
    if not points_file.exists():
        print("Brak:", points_file)
        return
    points = []
    with open(points_file, "rb") as f:
        # liczba punktów
        num_points = struct.unpack("<Q", f.read(8))[0]
        for i in range(num_points):
            # POINT3D_ID
            point_id = struct.unpack("<Q", f.read(8))[0]
            # XYZ
            x, y, z = struct.unpack(
                "<ddd",
                f.read(24)
            )
            # RGB
            r, g, b = struct.unpack(
                "<BBB",
                f.read(3)
            )
            # reprojection error
            error = struct.unpack(
                "<d",
                f.read(8)
            )[0]
            # track length
            track_length = struct.unpack(
                "<Q",
                f.read(8)
            )[0]
            # pomijamy track:
            # IMAGE_ID + POINT2D_IDX
            f.read(
                track_length * 8
            )
            if len(points) < limit:
                points.append(
                    (
                        point_id,
                        x,
                        y,
                        z,
                        r,
                        g,
                        b,
                        error,
                        track_length
                    )
                )
    print()
    print("=== SPARSE 3D POINTS ===")
    print("count:", num_points)
    print("\nFirst points:")
    for p in points:
        print(
            f"id={p[0]} "
            f"XYZ=({p[1]:.3f}, {p[2]:.3f}, {p[3]:.3f}) "
            f"RGB=({p[4]},{p[5]},{p[6]}) "
            f"error={p[7]:.3f} "
            f"track={p[8]}"
        )

def db_count(table):
    if not DATABASE.exists():
        return 0
    con = sqlite3.connect(DATABASE)
    try:
        cur = con.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {table}"
        )
        return cur.fetchone()[0]
    except:
        return 0
    finally:
        con.close()
        
def keypoint_stats():
    if not DATABASE.exists():
        return
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT 
                COUNT(*),
                SUM(rows),
                AVG(rows),
                MIN(rows),
                MAX(rows)
            FROM keypoints
        """)
        result = cur.fetchone()
        print("SIFT Keypoints:")
        print(" images:", result[0])
        print(" total:", result[1])
        print(" avg/image:", int(result[2]))
        print(" min:", result[3])
        print(" max:", result[4])
    except Exception as e:
        print("keypoints error:", e)
    finally:
        con.close()

def match_stats():
    if not DATABASE.exists():
        return
    con = sqlite3.connect(DATABASE)
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT 
                COUNT(*),
                SUM(rows),
                AVG(rows)
            FROM matches
        """)
        result = cur.fetchone()
        print("Matches:")
        print(" pairs:", result[0])
        print(" total matches:", result[1])
        print(" avg/pair:", int(result[2]))
    except Exception as e:
        print("matches error:", e)
    finally:
        con.close()

def is_feature_extraction_done():
    return (
        DATABASE.exists()
        and db_count("keypoints") > 0
    )

def is_matching_done():
    return (
        DATABASE.exists()
        and db_count("matches") > 0
    )

def is_mapper_done():
    return (
        SPARSE / "0" / "points3D.bin"
    ).exists()

def is_undistort_done():
    return (
        DENSE / "images"
    ).exists()

def is_stereo_done():
    depth_dir = DENSE / "stereo" / "depth_maps"
    return (
        depth_dir.exists()
        and any(depth_dir.glob("*.bin"))
    )
def is_fusion_done():
    return (
        DENSE / "fused.ply"
    ).exists()

def colmap_status():
    print("\n=== COLMAP STATUS ===")
    print("Proj dir: ",PROJECT)
    print(
        "features:",
        is_feature_extraction_done(),
        "keypoints:",
        db_count("keypoints")
    )
    print(
        "matches:",
        is_matching_done(),
        "matches:",
        db_count("matches")
    )
    print(
        "mapper:",
        is_mapper_done()
    )
    print(
        "undistort:",
        is_undistort_done()
    )
    print(
        "stereo:",
        is_stereo_done()
    )
    print(
        "fusion:",
        is_fusion_done()
    )
    
    keypoint_stats()
    match_stats()

# RUNNER

def run(cmd):

    print("\n" + "=" * 80)
    print(" ".join(map(str, cmd)))
    print("=" * 80)

    subprocess.run(
        list(map(str, cmd)),
        check=True
    )

# PIPELINE
start = time.time()
if(COMMAND == "status"):
    colmap_status()
    exit()
if (COMMAND == "points3d"):
    points3d_stats()
    exit()
if COMMAND == "export_ply":
    export_points_ply()
    exit()
if COMMAND == "draw_points":
    N = 2
    frames_dir = PROJECT / "frames"
    frame_files = sorted(
        [p for p in frames_dir.iterdir() if p.is_file()]
    )[:N]
    print(frame_files)
    for frame in frame_files:
        draw_colmap_features(
            frame,
            DATABASE
        )
        draw_colmap_3d_points(
            frame,
            SPARSE / "0"
        )
    exit()
        
SPARSE.mkdir(exist_ok=True)
DENSE.mkdir(exist_ok=True)

if COMMAND == "stereo":
    run([
            COLMAP,
            "patch_match_stereo",
            "--workspace_path", DENSE
        ])
    exit()

# 1. Feature Extraction
if not is_feature_extraction_done() or COMMAND == "feature_extractor":
    print("\nRUN Feature Extraction")
    run([
        COLMAP,
        "feature_extractor",
        "--database_path", DATABASE,
        "--image_path", IMAGES,
        "--ImageReader.single_camera", "1",
        "--ImageReader.camera_model", "SIMPLE_RADIAL",
        "--FeatureExtraction.use_gpu", "1",
        "--FeatureExtraction.gpu_index", "0"
    ])

else:
    print("SKIP Feature Extraction")

# 2. Matching
if not is_matching_done() or COMMAND == "sequential_matcher":
    print("RUN Sequential Matching")
    run([
        COLMAP,
        "sequential_matcher",
        "--database_path", DATABASE,
        "--FeatureMatching.use_gpu", "1",
        "--FeatureMatching.gpu_index", "0"
    ])
else:
    print("SKIP Matching")

# 3. Mapper
if not is_mapper_done() or COMMAND == "mapper": # robi points3d
    print("RUN Mapper")
    run([
        COLMAP,
        "mapper",
        "--database_path", DATABASE,
        "--image_path", IMAGES,
        "--output_path", SPARSE,
        "--Mapper.ba_use_gpu", "1",
        "--Mapper.multiple_models", "0"
    ])
else:
    print("SKIP Mapper")

# 4. Undistort
if not is_undistort_done() or COMMAND == "image_undistorter":
    print("RUN Image Undistorter")

    run([
        COLMAP,
        "image_undistorter",
        "--image_path", IMAGES,
        "--input_path", SPARSE / "0",
        "--output_path", DENSE,
        "--output_type", "COLMAP"
    ])

else:
    print("SKIP Undistorter")

# 5. Stereo
if not is_stereo_done() or COMMAND == "patch_match_stereo": # dla każdego zdjęcia: deepMap, normalMap, consistency_graphs
    print("RUN Patch Match Stereo")
    run([
        COLMAP,
        "patch_match_stereo",
        "--workspace_path", DENSE
    ])
else:
    print("SKIP Patch Match Stereo")

# 6. Fusion
if not is_fusion_done() or COMMAND == "stereo_fusion":  # łączy każdy pixel z deepMap z innymi pixelami pozostałych klatek
    print("RUN Stereo Fusion")
    run([
        COLMAP,
        "stereo_fusion",
        "--workspace_path", DENSE,
        "--output_path",
        DENSE / "fused.ply"
    ])
else:
    print("SKIP Fusion")

print("\n" + "=" * 80)
print("COLMAP DONE")
print(
    f"Time: {time.time()-start:.1f}s"
)
print("=" * 80)







