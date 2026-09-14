from pathlib import Path

import numpy as np
import numpy as np
import cv2
import os
import pycolmap
import sqlite3

def draw_crosshair(img, x, y, size=10, color=(0,0,255), thickness=1):
    """
    Rysuje celownik:
    
        |
        |
    ----  ----
        |
        |
    
    bez linii w samym środku.
    """

    x = int(x)
    y = int(y)

    gap = 3  # odstęp od środka

    # pionowa górna część
    cv2.line(
        img,
        (x, y-size),
        (x, y-gap),
        color,
        thickness
    )

    # pionowa dolna część
    cv2.line(
        img,
        (x, y+gap),
        (x, y+size),
        color,
        thickness
    )

    # pozioma lewa część
    cv2.line(
        img,
        (x-size, y),
        (x-gap, y),
        color,
        thickness
    )

    # pozioma prawa część
    cv2.line(
        img,
        (x+gap, y),
        (x+size, y),
        color,
        thickness
    )

def draw_colmap_features(image_path, database_path):
    """
    Rysuje wszystkie feature points SIFT wykryte przez COLMAP.

    image_path:
        ścieżka do zdjęcia

    database_path:
        ścieżka do database.db COLMAP
    """

    image_name = os.path.basename(image_path)

    conn = sqlite3.connect(database_path)
    cur = conn.cursor()

    result = cur.execute(
        "SELECT image_id FROM images WHERE name=?",
        (image_name,)
    ).fetchone()

    if result is None:
        conn.close()
        raise Exception(
            f"Nie znaleziono obrazu {image_name} w database.db"
        )

    image_id = result[0]


    row = cur.execute(
        """
        SELECT rows, cols, data
        FROM keypoints
        WHERE image_id=?
        """,
        (image_id,)
    ).fetchone()

    conn.close()


    if row is None:
        raise Exception(
            "Brak keypointów dla tego obrazu"
        )


    rows, cols, data = row

    keypoints = np.frombuffer(
        data,
        dtype=np.float32
    ).reshape(rows, cols)


    img = cv2.imread(image_path)

    if img is None:
        raise Exception(
            "Nie można otworzyć obrazu"
        )


    for p in keypoints:
        x, y = p[:2]

        draw_crosshair(
            img,
            x,
            y,
            size=8,
            color=(0,255,0),
            thickness=1
        )

    image_path = Path(image_path)
    output_dir = image_path.parent / image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "_features.png"
    cv2.imwrite(str(output), img)

    return output, len(keypoints)



def draw_colmap_3d_points(image_path, sparse_path):
    """
    Rysuje punkty 3D COLMAP widoczne na zdjęciu.

    image_path:
        ścieżka do zdjęcia

    sparse_path:
        katalog modelu COLMAP np.
        sparse/0
    """


    reconstruction = pycolmap.Reconstruction(
        sparse_path
    )


    image_name = os.path.basename(image_path)


    colmap_image = None

    for img in reconstruction.images.values():

        if img.name == image_name:
            colmap_image = img
            break


    if colmap_image is None:
        raise Exception(
            f"Nie znaleziono {image_name} w modelu COLMAP"
        )


    img = cv2.imread(image_path)


    count = 0


    for point2D in colmap_image.points2D:

        if point2D.has_point3D():

            x, y = point2D.xy


            # współrzędne 3D
            point3D = reconstruction.points3D[
                point2D.point3D_id
            ]

            xyz = point3D.xyz


            draw_crosshair(
                img,
                x,
                y,
                size=8,
                color=(0,0,255),
                thickness=1
            )

            count += 1

    image_path = Path(image_path)
    output_dir = image_path.parent / image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "_points3D.png"

    cv2.imwrite(
        output_file,
        img
    )


    return output_file, count