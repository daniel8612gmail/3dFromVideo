# dm_line_groups.py

import numpy as np
import math


# ==========================================================
# Narzędzia
# ==========================================================

def angle_diff(a, b):

    d = abs(a - b)

    return min(
        d,
        180 - d
    )



def line_projection_range(line, angle):

    """
    Rzut końców odcinka na kierunek linii.
    """

    theta = math.radians(angle)

    dx = math.cos(theta)
    dy = math.sin(theta)

    x1,y1,x2,y2 = line


    p1 = x1*dx + y1*dy
    p2 = x2*dx + y2*dy


    return (
        min(p1,p2),
        max(p1,p2)
    )



def overlap_ratio(a1,a2,b1,b2):

    """
    Pokrycie dwóch przedziałów.
    """

    inter = max(
        0,
        min(a2,b2)-max(a1,b1)
    )


    length = max(
        a2-a1,
        b2-b1
    )


    if length <= 0:
        return 0


    return inter/length



# ==========================================================
# Grupowanie linii LSD
# ==========================================================

def group_parallel_lines(
        data,
        angle_thr=3,
        rho_thr=20,
        overlap_thr=0.15
):

    """
    Grupowanie po:

        - kącie
        - rho
        - położeniu wzdłuż linii

    """

    indexes = np.where(
        data["active"]
    )[0]


    groups=[]


    for idx in indexes:


        angle=data["angle"][idx]
        rho=data["rho"][idx]

        line=data["lines"][idx]


        r1,r2 = line_projection_range(
            line,
            angle
        )


        assigned=False


        for g in groups:


            if angle_diff(
                angle,
                g["angle"]
            ) > angle_thr:
                continue


            if abs(
                rho-g["rho"]
            ) > rho_thr:
                continue



            ov = overlap_ratio(
                r1,
                r2,
                g["pmin"],
                g["pmax"]
            )


            if ov < overlap_thr:
                continue



            g["indexes"].append(
                idx
            )


            ids=np.array(
                g["indexes"]
            )


            g["angle"]=float(
                np.average(
                    data["angle"][ids],
                    weights=data["weight"][ids]
                )
            )


            g["rho"]=float(
                np.average(
                    data["rho"][ids],
                    weights=data["weight"][ids]
                )
            )


            g["pmin"]=min(
                g["pmin"],
                r1
            )


            g["pmax"]=max(
                g["pmax"],
                r2
            )


            g["score"]=float(
                np.sum(
                    data["weight"][ids]
                )
            )


            assigned=True

            break



        if not assigned:

            groups.append(
                {
                    "indexes":[idx],

                    "angle":
                        float(angle),

                    "rho":
                        float(rho),

                    "pmin":
                        r1,

                    "pmax":
                        r2,

                    "score":
                        float(
                            data["weight"][idx]
                        )
                }
            )


    return groups



# ==========================================================
# Scalanie grupy do jednej krawędzi
# ==========================================================

def merge_group_segments(
        data,
        group
):

    ids=np.array(
        group["indexes"]
    )


    angle=group["angle"]

    theta=math.radians(angle)


    dx=math.cos(theta)
    dy=math.sin(theta)


    #
    # punkt bazowy z rho
    #

    nx=math.sin(theta)
    ny=-math.cos(theta)


    x0=group["rho"]*nx
    y0=group["rho"]*ny



    p1=group["pmin"]
    p2=group["pmax"]



    x1=x0 + dx*p1
    y1=y0 + dy*p1


    x2=x0 + dx*p2
    y2=y0 + dy*p2



    return np.array(
        [
            x1,
            y1,
            x2,
            y2
        ],
        dtype=np.float32
    )



# ==========================================================
# Budowa finalnych krawędzi
# ==========================================================

def build_edges(
        data,
        groups,
        min_support=2
):

    edges=[]


    for g in groups:


        if len(g["indexes"]) < min_support:
            continue



        line = merge_group_segments(
            data,
            g
        )


        edges.append(
            {
                "line":line,

                "angle":
                    g["angle"],

                "rho":
                    g["rho"],

                "score":
                    g["score"],

                "support":
                    len(g["indexes"])
            }
        )


    edges.sort(
        key=lambda x:
            x["score"],
        reverse=True
    )


    return edges



# ==========================================================
# Debug
# ==========================================================

def print_edges(edges, limit=20):

    for i,e in enumerate(edges[:limit]):

        x1,y1,x2,y2=e["line"]

        print(
            i,
            "angle=",
            round(e["angle"],2),
            "support=",
            e["support"],
            "score=",
            round(e["score"]),
            "line=",
            (
                round(x1),
                round(y1),
                round(x2),
                round(y2)
            )
        )