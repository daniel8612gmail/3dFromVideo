from pathlib import Path

import cv2
import numpy as np

def save_lsd_debug(img, lines, nfa, output_path):
    """
    Zapisuje segmenty LSD pokolorowane wg nfa.

    lines:
        Nx4 [x1,y1,x2,y2]

    nfa:
        wynik LSD nfa, Nx1 lub Nx
    """

    if len(img.shape) == 2:
        debug = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    else:
        debug = img.copy()

    lines = lines.reshape(-1, 4)
    nfa = np.array(nfa).reshape(-1)

    # normalizacja nfa do 0..1
    # odcinamy skrajności
    nfa_min = np.percentile(nfa, 5)
    nfa_max = np.percentile(nfa, 95)

    for line, score in zip(lines.astype(int), nfa):

        x1, y1, x2, y2 = line

        t = (score - nfa_min) / max(nfa_max - nfa_min, 1e-6)
        t = np.clip(t, 0, 1)

        # słabe: czerwone
        # mocne: zielone
        color = (
            int(255 * (1 - t)),  # B
            int(255 * t),        # G
            0                    # R
        )

        cv2.line(
            debug,
            (x1, y1),
            (x2, y2),
            color,
            2,
            cv2.LINE_AA
        )

    cv2.imwrite(output_path, debug)


def save_debug_contours(path, image_shape, contours):
    debug = np.zeros(
        image_shape,
        dtype=np.uint8
    )

    cv2.drawContours(
        debug,
        contours,
        -1,
        255,
        1
    )
    #print(f"Saving debug contours to: {path}")
    cv2.imwrite(
        str(path),
        debug
    )


def save_debug_lines(path, image_shape, lines):
    debug = np.zeros(
        image_shape,
        dtype=np.uint8
    )

    if lines is not None:
        for line in lines:

            if len(line.shape) == 2:
                x1, y1, x2, y2 = line[0]
            else:
                x1, y1, x2, y2 = line

            cv2.line(
                debug,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                255,
                1
            )

    #print(f"Saving debug lines to: {path}")

    cv2.imwrite(
        str(path),
        debug
    )
    
def save_debug_mask(path, mask):
    """
    Zapis maski w formie czytelnej dla człowieka
    """

    path = Path(path)

    # normalizacja do 0-255
    if mask.dtype != "uint8":
        mask = mask.astype("uint8")

    cv2.imwrite(
        str(path),
        mask
    )
    
def save_debug_mask_overlay(
        image,
        mask,
        path
):

    if len(image.shape) == 2:
        image = cv2.cvtColor(
            image,
            cv2.COLOR_GRAY2BGR
        )


    if image.shape[:2] != mask.shape[:2]:
        raise ValueError(
            f"Image {image.shape} != mask {mask.shape}"
        )


    overlay = image.copy()


    color = np.zeros_like(image)
    color[:,:,1] = 255


    alpha = 0.35


    idx = mask > 0


    overlay[idx] = (
        image[idx] * (1-alpha)
        +
        color[idx] * alpha
    )


    cv2.imwrite(
        str(path),
        overlay
    )
    
def draw_lines_debug(
        image,
        lines
):

    debug = image.copy()


    for i,line in enumerate(lines):

        x1,y1,x2,y2 = line


        cv2.line(
            debug,
            (x1,y1),
            (x2,y2),
            (0,255,0),
            2
        )


        cv2.putText(
            debug,
            str(i),
            (x1,y1),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0,0,255),
            1
        )


    return debug