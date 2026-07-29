import cv2
import numpy as np
import json
from pathlib import Path


def extract_polygon(mask_path, output_json, epsilon_ratio=0.02):
    """
    Zamienia maskę binarną na uproszczony polygon.

    mask:
        0     - tło
        255   - obiekt

    epsilon_ratio:
        procent długości konturu
    """

    mask = cv2.imread(
        str(mask_path),
        cv2.IMREAD_GRAYSCALE
    )

    if mask is None:
        raise FileNotFoundError(mask_path)


    # upewniamy się, że maska jest binarna
    _, thresh = cv2.threshold(
        mask,
        127,
        255,
        cv2.THRESH_BINARY
    )


    # wyszukiwanie konturów
    contours, _ = cv2.findContours(
        thresh,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )


    if not contours:
        raise Exception("Nie znaleziono konturu")


    # największy obiekt
    contour = max(
        contours,
        key=cv2.contourArea
    )


    area = cv2.contourArea(contour)

    perimeter = cv2.arcLength(
        contour,
        True
    )


    # epsilon Douglas-Peucker
    epsilon = epsilon_ratio * perimeter


    approx = cv2.approxPolyDP(
        contour,
        epsilon,
        True
    )


    # format [x,y]
    points = [
        [
            int(p[0][0]),
            int(p[0][1])
        ]
        for p in approx
    ]


    data = {

        "source": str(mask_path),

        "area_px": area,

        "perimeter_px": perimeter,

        "epsilon_px": epsilon,

        "points": points
    }


    with open(
        output_json,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2
        )


    print(
        f"Zapisano {len(points)} punktów"
    )

    return points



if __name__ == "__main__":


    BASE = Path(__file__).parent


    mask = BASE / "masks" / "mask_001.png"

    output = BASE / "output" / "polygon_001.json"


    extract_polygon(
        mask,
        output,
        epsilon_ratio=0.02
    )