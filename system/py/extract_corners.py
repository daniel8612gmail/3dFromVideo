import numpy as np
import json
import math
import cv2


# -------------------------
# odległość punktów
# -------------------------

def point_distance(a,b):

    return math.hypot(
        a[0]-b[0],
        a[1]-b[1]
    )


# -------------------------
# kąt linii
# -------------------------

def line_angle(line):

    x1,y1,x2,y2=line

    angle=math.degrees(
        math.atan2(
            y2-y1,
            x2-x1
        )
    )

    if angle < 0:
        angle+=180

    return angle



# -------------------------
# czy linie mają różny kierunek
# -------------------------

def angle_difference(a,b):

    d=abs(a-b)

    return min(
        d,
        180-d
    )



# -------------------------
# przecięcie dwóch odcinków
# -------------------------

def intersection(l1,l2):

    x1,y1,x2,y2=l1
    x3,y3,x4,y4=l2


    den=(
        (x1-x2)*(y3-y4)
        -
        (y1-y2)*(x3-x4)
    )


    if abs(den)<1e-8:
        return None


    px=(
        (x1*y2-y1*x2)*(x3-x4)
        -
        (x1-x2)*(x3*y4-y3*x4)
    )/den


    py=(
        (x1*y2-y1*x2)*(y3-y4)
        -
        (y1-y2)*(x3*y4-y3*x4)
    )/den


    return [
        px,
        py
    ]



# -------------------------
# sprawdzenie czy punkt
# leży blisko końca linii
# -------------------------

def near_endpoint(point,line,max_dist=40):

    x1,y1,x2,y2=line

    d1=point_distance(
        point,
        (x1,y1)
    )

    d2=point_distance(
        point,
        (x2,y2)
    )


    return min(d1,d2)<max_dist



# -------------------------
# wykrywanie narożników
# -------------------------

def detect_corners(
    lines,
    max_endpoint_distance=50,
    min_angle=20
):

    corners=[]


    for i in range(len(lines)):

        l1=lines[i]

        a1=line_angle(l1)


        for j in range(
            i+1,
            len(lines)
        ):

            l2=lines[j]


            a2=line_angle(l2)


            # prawie równoległe
            if angle_difference(a1,a2)<min_angle:
                continue


            p=intersection(
                l1,
                l2
            )


            if p is None:
                continue


            # najważniejszy filtr
            if (
                near_endpoint(p,l1,max_endpoint_distance)
                and
                near_endpoint(p,l2,max_endpoint_distance)
            ):

                corners.append(
                    {
                    "point":[
                        round(p[0],2),
                        round(p[1],2)
                    ],

                    "lines":[
                        i,
                        j
                    ],

                    "angle":round(
                        angle_difference(a1,a2),
                        2
                    )
                    }
                )


    return corners



# -------------------------
# scalanie bliskich narożników
# -------------------------

def merge_corners(
    corners,
    distance=30
):

    result=[]


    for c in corners:

        p=c["point"]

        found=False


        for r in result:

            if point_distance(
                p,
                r["point"]
            ) < distance:

                r["points"].append(p)

                found=True
                break


        if not found:

            result.append(
                {
                "point":p,
                "points":[p],
                "lines":[
                    c["lines"]
                ]
                }
            )


    # średnia położenia

    for r in result:

        pts=r["points"]

        r["point"]=[
            round(
                sum(p[0] for p in pts)/len(pts),
                2
            ),
            round(
                sum(p[1] for p in pts)/len(pts),
                2
            )
        ]


        del r["points"]


    return result



# -------------------------
# główna funkcja
# -------------------------

def extract_corners(lines):

    if lines is None:
        return []


    lines=np.asarray(lines)

    lines=lines.reshape(-1,4)


    corners=detect_corners(
        lines
    )


    corners=merge_corners(
        corners
    )


    return {
        "line_count":len(lines),
        "corner_count":len(corners),
        "lines":lines.tolist(),
        "corners":corners
    }