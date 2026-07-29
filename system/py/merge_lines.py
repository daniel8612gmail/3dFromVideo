import math
import numpy as np


def line_angle(line):
    """
    Kąt linii w stopniach 0-180
    """

    x1, y1, x2, y2 = line

    angle = math.degrees(
        math.atan2(
            y2 - y1,
            x2 - x1
        )
    )

    if angle < 0:
        angle += 180

    return angle



def angle_difference(a, b):
    """
    Różnica kątów linii.
    Uwzględnia kierunek 0 == 180.
    """

    diff = abs(a - b)

    if diff > 90:
        diff = 180 - diff

    return diff



def line_length(line):

    x1,y1,x2,y2 = line

    return math.hypot(
        x2-x1,
        y2-y1
    )



def point_line_distance(point, line):
    """
    Odległość punktu od nieskończonej prostej.
    """

    x,y = point

    x1,y1,x2,y2 = line


    numerator = abs(
        (y2-y1)*x -
        (x2-x1)*y +
        x2*y1 -
        y2*x1
    )


    denominator = math.hypot(
        y2-y1,
        x2-x1
    )


    if denominator == 0:
        return 999999


    return numerator / denominator



def segment_gap(line1,line2):
    """
    Minimalna odległość końców odcinków.
    """

    p1=np.array(line1[:2])
    p2=np.array(line1[2:])

    p3=np.array(line2[:2])
    p4=np.array(line2[2:])


    return min(
        np.linalg.norm(p1-p3),
        np.linalg.norm(p1-p4),
        np.linalg.norm(p2-p3),
        np.linalg.norm(p2-p4)
    )



def merge_two_lines(line1,line2):
    """
    Tworzy najdłuższy odcinek obejmujący oba.
    """

    points=np.array(
        [
            line1[:2],
            line1[2:],
            line2[:2],
            line2[2:]
        ],
        dtype=float
    )


    angle=math.radians(
        line_angle(line1)
    )


    direction=np.array(
        [
            math.cos(angle),
            math.sin(angle)
        ]
    )


    values=points @ direction


    p1=points[np.argmin(values)]
    p2=points[np.argmax(values)]


    return [
        int(round(p1[0])),
        int(round(p1[1])),
        int(round(p2[0])),
        int(round(p2[1]))
    ]



def can_merge(
    line1,
    line2,
    angle_threshold,
    distance_threshold,
    gap_threshold,
    max_length
):

    a1=line_angle(line1)
    a2=line_angle(line2)


    # kontrola kąta
    if angle_difference(a1,a2) > angle_threshold:
        return False



    # odległość między końcami
    if segment_gap(line1,line2) > gap_threshold:
        return False



    # czy leżą na tej samej prostej
    d1=point_line_distance(
        line1[:2],
        line2
    )

    d2=point_line_distance(
        line2[:2],
        line1
    )


    if min(d1,d2) > distance_threshold:
        return False



    merged=merge_two_lines(
        line1,
        line2
    )


    if line_length(merged)>max_length:
        return False


    return True




def merge_lines(
    lines,
    angle_threshold=3,
    distance_threshold=8,
    gap_threshold=80,
    angle_bin=10,
    max_length=5000
):
    """
    Łączenie podobnych linii.

    Parametry:
    
    angle_threshold:
        tolerancja kąta [stopnie]

    distance_threshold:
        odległość od tej samej prostej [px]

    gap_threshold:
        maksymalna przerwa między liniami [px]

    angle_bin:
        grupowanie kątów

    max_length:
        maksymalna długość wynikowej linii
    """


    if lines is None:
        return np.empty((0,4),dtype=np.int32)


    if len(lines)==0:
        return np.empty((0,4),dtype=np.int32)



    # cv2 zwraca [[x1,y1,x2,y2]]
    lines=[
        list(map(int,l[0] if np.array(l).ndim==2 else l))
        for l in lines
    ]



    # grupowanie kierunku

    groups={}


    for line in lines:

        angle=line_angle(line)

        key=int(round(angle/angle_bin))


        if key not in groups:
            groups[key]=[]


        groups[key].append(line)



    result=[]


    # łączenie w grupach

    for group in groups.values():

        changed=True


        while changed:

            changed=False

            merged=[]

            used=set()


            for i in range(len(group)):

                if i in used:
                    continue


                current=group[i]


                for j in range(i+1,len(group)):

                    if j in used:
                        continue


                    if can_merge(
                        current,
                        group[j],
                        angle_threshold,
                        distance_threshold,
                        gap_threshold,
                        max_length
                    ):

                        current=merge_two_lines(
                            current,
                            group[j]
                        )

                        used.add(j)
                        changed=True


                merged.append(current)
                used.add(i)



            group=merged



        result.extend(group)



    return np.array(
        result,
        dtype=np.int32
    )