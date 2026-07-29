import cv2
import numpy as np


def detect_boundary_lines(
        edges,
        threshold=60,
        min_line_length=80,
        max_line_gap=20
):

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap
    )


    if lines is None:
        return np.empty(
            (0,4),
            dtype=np.int32
        )


    return lines.reshape(
        -1,
        4
    )