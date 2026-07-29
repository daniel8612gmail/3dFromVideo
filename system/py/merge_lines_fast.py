import math
import numpy as np
from collections import defaultdict


def line_angle(line):
    x1,y1,x2,y2 = line

    angle = math.degrees(
        math.atan2(
            y2-y1,
            x2-x1
        )
    )

    if angle < 0:
        angle += 180

    return angle



def angle_diff(a,b):

    d = abs(a-b)

    if d > 90:
        d = 180-d

    return d



def line_length(line):

    x1,y1,x2,y2=line

    return math.hypot(
        x2-x1,
        y2-y1
    )



def point_line_distance(point,line):

    x,y=point

    x1,y1,x2,y2=line


    den=math.hypot(
        y2-y1,
        x2-x1
    )

    if den==0:
        return 999999


    return abs(
        (y2-y1)*x -
        (x2-x1)*y +
        x2*y1 -
        y2*x1
    ) / den



def segment_gap(a,b):

    p=[
        np.array(a[:2]),
        np.array(a[2:]),
        np.array(b[:2]),
        np.array(b[2:])
    ]

    return min(
        np.linalg.norm(p[0]-p[2]),
        np.linalg.norm(p[0]-p[3]),
        np.linalg.norm(p[1]-p[2]),
        np.linalg.norm(p[1]-p[3])
    )



def merge_two(a,b):

    pts=np.array(
        [
            a[:2],
            a[2:],
            b[:2],
            b[2:]
        ],
        dtype=float
    )


    angle=math.radians(
        line_angle(a)
    )


    direction=np.array(
        [
            math.cos(angle),
            math.sin(angle)
        ]
    )


    proj=pts @ direction


    p1=pts[np.argmin(proj)]
    p2=pts[np.argmax(proj)]


    return [
        int(p1[0]),
        int(p1[1]),
        int(p2[0]),
        int(p2[1])
    ]



def can_merge(
    a,
    b,
    angle_a,
    angle_b,
    angle_threshold,
    distance_threshold,
    gap_threshold,
    max_length
):

    if angle_diff(
        angle_a,
        angle_b
    ) > angle_threshold:
        return False


    if segment_gap(
        a,b
    ) > gap_threshold:
        return False



    if min(
        point_line_distance(a[:2],b),
        point_line_distance(b[:2],a)
    ) > distance_threshold:

        return False



    merged=merge_two(a,b)


    if line_length(merged)>max_length:
        return False


    return True



def merge_lines(
    lines,
    angle_threshold=3,
    distance_threshold=8,
    gap_threshold=80,
    angle_bin=10,
    cell_size=150,
    max_length=5000
):

    """
    Szybkie łączenie linii.

    lines:
        wynik cv2.HoughLinesP

    """

    if lines is None:
        return np.empty((0,4),dtype=np.int32)


    # spłaszczenie HoughLinesP

    prepared=[]


    for l in lines:

        if len(l)==1:
            l=l[0]

        l=list(map(int,l))

        x1,y1,x2,y2=l


        angle=line_angle(l)

        cx=(x1+x2)/2
        cy=(y1+y2)/2


        prepared.append(
            {
                "line":l,
                "angle":angle,
                "cell":(
                    int(cx/cell_size),
                    int(cy/cell_size)
                )
            }
        )



    # indeks przestrzenny

    grid=defaultdict(list)


    for i,item in enumerate(prepared):

        key=(
            int(item["angle"]//angle_bin),
            item["cell"][0],
            item["cell"][1]
        )

        grid[key].append(i)



    used=set()

    result=[]



    # tylko lokalne porównania

    for key,indices in grid.items():

        if len(indices)<2:

            result.extend(
                [
                    prepared[i]["line"]
                    for i in indices
                ]
            )

            continue



        changed=True


        while changed:

            changed=False


            base=indices[0]


            for j in indices[1:]:

                if j in used:
                    continue


                a=prepared[base]
                b=prepared[j]


                if can_merge(
                    a["line"],
                    b["line"],
                    a["angle"],
                    b["angle"],
                    angle_threshold,
                    distance_threshold,
                    gap_threshold,
                    max_length
                ):

                    a["line"]=merge_two(
                        a["line"],
                        b["line"]
                    )

                    a["angle"]=line_angle(
                        a["line"]
                    )

                    used.add(j)

                    changed=True



        result.append(
            prepared[base]["line"]
        )


    return np.array(
        result,
        dtype=np.int32
    )