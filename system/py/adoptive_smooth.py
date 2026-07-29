import cv2
import numpy as np


def adaptive_smooth_edges(
    image,
    return_type="edges",
    close_ratio=0.001,
    min_line_ratio=0.02,
    hough_threshold_ratio=0.01
):
    """
    Adaptacyjne wygładzanie krawędzi niezależne od rozdzielczości.

    image:
        obraz BGR albo grayscale albo gotowe edges

    return_type:
        "edges" -> zwraca mapę krawędzi
        "lines" -> zwraca linie HoughLinesP

    close_ratio:
        wielkość zamykania dziur względem szerokości obrazu

    min_line_ratio:
        minimalna długość linii względem szerokości obrazu

    hough_threshold_ratio:
        próg Hough względem szerokości obrazu
    """

    # -------------------------
    # rozmiar
    # -------------------------

    if len(image.shape) == 3:
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )
    else:
        gray = image


    h, w = gray.shape[:2]


    # -------------------------
    # jeżeli to nie są edge
    # -------------------------

    if np.max(gray) > 1:

        edges = cv2.Canny(
            gray,
            50,
            150
        )

    else:
        edges = gray.copy()


    # -------------------------
    # adaptive morphology
    # -------------------------

    kernel_size = max(
        3,
        int(w * close_ratio)
    )

    # zawsze nieparzysty
    if kernel_size % 2 == 0:
        kernel_size += 1


    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            kernel_size,
            kernel_size
        )
    )


    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=1
    )


    if return_type == "edges":
        return edges


    # -------------------------
    # Hough
    # -------------------------

    min_line_length = int(
        w * min_line_ratio
    )

    threshold = int(
        w * hough_threshold_ratio
    )


    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi/180,
        threshold=threshold,
        minLineLength=min_line_length,
        maxLineGap=kernel_size * 3
    )


    if lines is None:
        return np.empty(
            (0,4),
            dtype=np.int32
        )


    return lines.reshape(-1,4)