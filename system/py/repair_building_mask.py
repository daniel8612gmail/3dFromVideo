import cv2
import numpy as np

def repair_mask(
        mask,
        close_size=25,
        open_size=5,
        fill_holes=True
):

    mask = np.where(
        mask > 0,
        255,
        0
    ).astype(np.uint8)


    # zamykanie dziur
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            close_size,
            close_size
        )
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )


    # usuwanie drobnych elementów
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            open_size,
            open_size
        )
    )

    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel
    )


    if fill_holes:

        flood = mask.copy()

        h,w = mask.shape

        temp = np.zeros(
            (
                h+2,
                w+2
            ),
            np.uint8
        )

        cv2.floodFill(
            flood,
            temp,
            (0,0),
            255
        )

        flood_inv = cv2.bitwise_not(
            flood
        )

        mask = (
            mask |
            flood_inv
        )


    return mask