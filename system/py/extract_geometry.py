import numpy as np
import json
import math
import cv2
import random


# ----------------------------
# Podstawowa geometria
# ----------------------------

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



def line_center(line):
    x1,y1,x2,y2 = line

    return (
        (x1+x2)/2,
        (y1+y2)/2
    )



# ----------------------------
# Grupowanie linii
# ----------------------------

def group_lines(
    lines,
    angle_threshold=8,
    distance_threshold=50
):

    groups=[]


    for line in lines:

        angle=line_angle(line)

        cx,cy=line_center(line)

        found=False


        for g in groups:

            da=abs(
                angle-g["angle"]
            )

            da=min(
                da,
                180-da
            )


            gx,gy=g["center"]

            dist=math.hypot(
                cx-gx,
                cy-gy
            )


            if (
                da < angle_threshold
                and dist < distance_threshold
            ):

                g["lines"].append(
                    line.tolist()
                )


                n=len(g["lines"])


                angles=[
                    line_angle(l)
                    for l in g["lines"]
                ]


                centers=[
                    line_center(l)
                    for l in g["lines"]
                ]


                g["angle"]=sum(
                    angles
                )/n


                g["center"]=(
                    sum(c[0] for c in centers)/n,
                    sum(c[1] for c in centers)/n
                )


                found=True
                break


        if not found:

            groups.append(
                {
                    "angle":angle,
                    "center":(cx,cy),
                    "lines":[
                        line.tolist()
                    ]
                }
            )


    return groups



# ----------------------------
# Przecięcie linii
# ----------------------------

def intersection(a,b):

    x1,y1,x2,y2=a
    x3,y3,x4,y4=b


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
        round(px,2),
        round(py,2)
    ]



# ----------------------------
# Szukanie narożników
# ----------------------------

def find_corners(groups):

    corners=[]


    for i in range(len(groups)):

        for j in range(i+1,len(groups)):

            a=groups[i]
            b=groups[j]


            diff=abs(
                a["angle"]-
                b["angle"]
            )

            diff=min(
                diff,
                180-diff
            )


            # linie prawie równoległe
            if diff < 15:
                continue


            for l1 in a["lines"]:

                for l2 in b["lines"]:

                    p=intersection(
                        l1,
                        l2
                    )

                    if p:

                        corners.append(
                            {
                            "point":p,
                            "groups":[
                                i,j
                            ]
                            }
                        )


    return corners



# ----------------------------
# Główna funkcja
# ----------------------------

def process_lines(lines):

    if lines is None or len(lines) == 0:
        return {
            "line_count": 0,
            "group_count": 0,
            "groups": [],
            "corners": []
        }

    # HoughLinesP zwraca (N,1,4)
    lines = np.asarray(lines).reshape(-1, 4)

    groups = group_lines(lines)

    corners = find_corners(groups)

    return {
        "line_count": len(lines),
        "group_count": len(groups),
        "groups": groups,
        "corners": corners
    }
    
    
def save_geometry(path, geometry):
    print("geometry: ", geometry)
    with open(path, "w", encoding="utf8") as f:
        json.dump(
            geometry,
            f,
            indent=2
        )

def save_lines(lines, npy_path, json_path):
    if lines is None:
        data = np.empty((0,4), dtype=np.int32)
    else:
        data = lines.reshape(-1,4)
    np.save(
        npy_path,
        data
    )
    json_data = []
    for x1,y1,x2,y2 in data:
        json_data.append({
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2)
        })
    with open(json_path,"w") as f:
        json.dump(
            json_data,
            f,
            indent=2
        )
        
def save_lines_min(lines, npy_path, json_path):
    if lines is None:
        data = np.empty((0, 4), dtype=np.int32)
    else:
        data = lines.reshape(-1, 4).astype(np.int32)
        #print("Linia:", lines[1])
    np.save(npy_path, data)

    with open(json_path, "w") as f:
        json.dump(
            data.tolist(),
            f,
            separators=(",", ":")   # bez spacji
        )
        
def draw_geometry(img, geometry):
    print("img type: ", type(img))
    print(img.dtype)
    print(img.shape)
    # ---------- oryginalne linie ----------
    for group in geometry["groups"]:

        color = (
            random.randint(50,255),
            random.randint(50,255),
            random.randint(50,255)
        )

        group["debug_color"] = color

        for line in group["lines"]:

            x1,y1,x2,y2 = map(int, line)

            cv2.line(
                img,
                (x1,y1),
                (x2,y2),
                color,
                2,
                cv2.LINE_AA
            )
    # ---------- środki grup ----------
    for gid,group in enumerate(geometry["groups"]):

        cx,cy = group["center"]

        cx=int(cx)
        cy=int(cy)

        cv2.circle(
            img,
            (cx,cy),
            6,
            (0,255,255),
            -1
        )

        cv2.putText(
            img,
            str(gid),
            (cx+8,cy-8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255,255,255),
            2
        )
    # ---------- narożniki ----------
    for cid,corner in enumerate(geometry["corners"]):

        x,y = corner["point"]

        x=int(round(x))
        y=int(round(y))

        cv2.drawMarker(
            img,
            (x,y),
            (0,0,255),
            cv2.MARKER_CROSS,
            18,
            2
        )

        cv2.putText(
            img,
            str(cid),
            (x+6,y+6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0,0,255),
            1
        )


    return img

def draw_geometry_lines(image_shape, geometry):

    h, w = image_shape[:2]

    img = np.zeros((h, w, 3), dtype=np.uint8)

    rng = random.Random(1234)

    for gid, group in enumerate(geometry["groups"]):

        color = (
            rng.randint(80,255),
            rng.randint(80,255),
            rng.randint(80,255)
        )

        for line in group["lines"]:

            x1,y1,x2,y2 = map(int,line)

            cv2.line(
                img,
                (x1,y1),
                (x2,y2),
                color,
                2,
                cv2.LINE_AA
            )

        cx,cy = group["center"]

        cx=int(cx)
        cy=int(cy)

        cv2.circle(
            img,
            (cx,cy),
            5,
            (0,255,255),
            -1
        )

        cv2.putText(
            img,
            str(gid),
            (cx+6,cy-6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255,255,255),
            1,
            cv2.LINE_AA
        )

    return img

def point_on_segment(px, py, line, eps=5):

    x1,y1,x2,y2 = line

    return (
        min(x1,x2)-eps <= px <= max(x1,x2)+eps
        and
        min(y1,y2)-eps <= py <= max(y1,y2)+eps
    )



def draw_geometry_intersections(image_shape, geometry):

    h,w = image_shape[:2]

    img = np.zeros((h,w,3),dtype=np.uint8)


    #
    # wszystkie linie
    #

    for group in geometry["groups"]:

        for line in group["lines"]:

            x1,y1,x2,y2 = map(int,line)

            cv2.line(
                img,
                (x1,y1),
                (x2,y2),
                (120,120,120),
                1,
                cv2.LINE_AA
            )


    #
    # narożniki
    #

    for corner in geometry["corners"]:

        px,py = corner["point"]

        g1,g2 = corner["groups"]

        good=False

        for l1 in geometry["groups"][g1]["lines"]:

            for l2 in geometry["groups"][g2]["lines"]:

                if (
                    point_on_segment(px,py,l1)
                    and
                    point_on_segment(px,py,l2)
                ):
                    good=True
                    break

            if good:
                break


        color = (
            (0,255,0)
            if good
            else
            (0,0,255)
        )


        cv2.circle(
            img,
            (
                int(px),
                int(py)
            ),
            5,
            color,
            -1
        )


    return img