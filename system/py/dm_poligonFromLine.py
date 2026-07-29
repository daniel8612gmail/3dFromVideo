import math
import numpy as np
import cv2


def line_length(line):
    (x1,y1),(x2,y2)=line
    return math.hypot(
        x2-x1,
        y2-y1
    )


def distance_point_to_line(p, line):
    """
    Odległość punktu od odcinka
    """
    p=np.array(p,float)
    a=np.array(line[0],float)
    b=np.array(line[1],float)

    ab=b-a

    if np.dot(ab,ab)==0:
        return np.linalg.norm(p-a)

    t=np.dot(p-a,ab)/np.dot(ab,ab)
    t=max(0,min(1,t))

    closest=a+t*ab

    return np.linalg.norm(p-closest)



def lines_intersect(l1,l2):

    a=np.array(l1[0])
    b=np.array(l1[1])

    c=np.array(l2[0])
    d=np.array(l2[1])


def cross(v, w):
    return v[0] * w[1] - v[1] * w[0]


    r=b-a
    s=d-c

    denom=cross(r,s)

    if abs(denom)<1e-8:
        return False


    t=cross(c-a,s)/denom
    u=cross(c-a,r)/denom


    return (
        0<=t<=1 and
        0<=u<=1
    )



def lines_touch(l1,l2,threshold=10):

    pts=[
        l1[0],
        l1[1],
        l2[0],
        l2[1]
    ]

    for p in pts:

        if (
            distance_point_to_line(
                p,
                l1
            )
            <
            threshold
            and
            distance_point_to_line(
                p,
                l2
            )
            <
            threshold
        ):
            return True

    return False



def find_next_line(
        current,
        lines,
        used,
        touch_distance=10
):

    candidates=[]

    for i,line in enumerate(lines):

        if i in used:
            continue


        if (
            lines_intersect(
                current,
                line
            )
            or
            lines_touch(
                current,
                line,
                touch_distance
            )
        ):

            candidates.append(
                (
                    line_length(line),
                    i,
                    line
                )
            )


    if not candidates:
        return None


    # najdłuższa pasująca
    candidates.sort(
        reverse=True,
        key=lambda x:x[0]
    )

    return candidates[0][1], candidates[0][2]



def build_polygon_from_lines(lines):

    if not lines:
        return []


    # najdłuższa jako start
    start_id=max(
        range(len(lines)),
        key=lambda i:line_length(lines[i])
    )


    polygon=[]

    used=set()


    current_id=start_id
    current=lines[current_id]


    start=current


    used.add(current_id)

    polygon.append(
        current[0]
    )

    polygon.append(
        current[1]
    )


    while True:

        nxt=find_next_line(
            current,
            lines,
            used
        )


        # koniec
        if nxt is None:
            break


        idx,line=nxt


        # powrót do początku
        if idx==start_id:
            break


        used.add(idx)


        # wybierz punkt połączenia
        if (
            np.linalg.norm(
                np.array(polygon[-1])
                -
                np.array(line[0])
            )
            >
            np.linalg.norm(
                np.array(polygon[-1])
                -
                np.array(line[1])
            )
        ):
            line=(line[1],line[0])


        polygon.append(
            line[1]
        )


        current=line


    # zamknięcie
    if polygon[-1]!=polygon[0]:
        polygon.append(
            polygon[0]
        )


    return polygon








def draw_polygon_result(
        img,
        polygon,
        output_path
):
    """
    Rysuje polygon na zdjęciu.

    polygon:
        [
          (x1,y1),
          (x2,y2),
          ...
        ]
    """

   
    if img is None:
        raise Exception(
            "Nie można otworzyć obrazu"
        )


    if len(polygon) < 2:
        raise Exception(
            "Za mało punktów polygonu"
        )


    pts = np.array(
        polygon,
        dtype=np.int32
    )


    # rysowanie obwodu
    cv2.polylines(
        img,
        [pts],
        isClosed=True,
        color=(0,0,255),
        thickness=5
    )


    # zaznacz wierzchołki
    for i,p in enumerate(polygon):

        x,y = map(int,p)

        cv2.circle(
            img,
            (x,y),
            8,
            (0,255,0),
            -1
        )

        cv2.putText(
            img,
            str(i),
            (x+10,y-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255,255,0),
            2
        )


    cv2.imwrite(
        output_path,
        img
    )

    print(
        "Zapisano:",
        output_path
    )