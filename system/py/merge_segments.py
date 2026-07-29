import numpy as np
import math


def segment_angle(seg):
    x1, y1, x2, y2 = seg
    a = math.degrees(math.atan2(y2-y1, x2-x1))
    return a % 180


def segment_length(seg):
    x1, y1, x2, y2 = seg
    return math.hypot(x2-x1, y2-y1)


def segment_center(seg):
    x1, y1, x2, y2 = seg
    return (
        (x1+x2)/2,
        (y1+y2)/2
    )


def is_duplicate(a, b,
                 angle_thr=2,
                 dist_thr=6,
                 length_ratio=0.2):

    aa = segment_angle(a)
    ab = segment_angle(b)

    da = abs(aa-ab)
    da = min(da, 180-da)

    if da > angle_thr:
        return False

    ax, ay = segment_center(a)
    bx, by = segment_center(b)

    dist = math.hypot(ax-bx, ay-by)

    if dist > dist_thr:
        return False

    la = segment_length(a)
    lb = segment_length(b)

    ratio = abs(la-lb)/max(la,lb)

    if ratio > length_ratio:
        return False

    return True


def merge_lsd_results(
        lsd_results,
        angle_thr=2,
        dist_thr=6):

    """
    lsd_results:
        lista:
        [
          (lines,widths,prec,nfa),
          (lines,widths,prec,nfa),
          ...
        ]

    zwraca:
        (lines,widths,prec,nfa)
    """

    segments = []

    for lines, widths, prec, nfa in lsd_results:

        if lines is None:
            continue

        lines = lines.reshape(-1,4)
        nfa = np.array(nfa).reshape(-1)

        if widths is None:
            widths = np.zeros(len(lines))

        if prec is None:
            prec = np.zeros(len(lines))

        for i, seg in enumerate(lines):

            segments.append({
                "line": seg,
                "width": widths[i],
                "prec": prec[i],
                "nfa": nfa[i]
            })


    # sortujemy: najlepsze najpierw
    segments.sort(
        key=lambda x: x["nfa"],
        reverse=True
    )


    result=[]


    for item in segments:

        duplicate=False

        for saved in result:

            if is_duplicate(
                item["line"],
                saved["line"],
                angle_thr,
                dist_thr
            ):
                duplicate=True
                break


        if not duplicate:
            result.append(item)


    lines_out=np.array(
        [x["line"] for x in result],
        dtype=np.float32
    )

    widths_out=np.array(
        [x["width"] for x in result]
    )

    prec_out=np.array(
        [x["prec"] for x in result]
    )

    nfa_out=np.array(
        [x["nfa"] for x in result]
    )


    # odtwarzamy format OpenCV
    lines_out = lines_out.reshape(-1,1,4)

    return (
        lines_out,
        widths_out,
        prec_out,
        nfa_out
    )