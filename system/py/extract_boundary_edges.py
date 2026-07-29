import cv2
import numpy as np


def extract_boundary_edges(mask):
    """
    Zwraca:
    - boundary mask
    - edge image

    Bez zapisu plików.
    """

    kernel = np.ones(
        (3,3),
        np.uint8
    )


    eroded = cv2.erode(
        mask,
        kernel,
        iterations=1
    )


    boundary = cv2.subtract(
        mask,
        eroded
    )


    edges = cv2.Canny(
        mask,
        50,
        150
    )


    edges = cv2.bitwise_and(
        edges,
        boundary
    )


    return boundary, edges