# dm_lines.py

import numpy as np
import math


# =====================================================
# Przygotowanie danych LSD
# =====================================================

def prepare_lsd(lines, widths, prec, nfa):
    """
    Przygotowanie struktury danych z wyniku LSD.

    Wszystkie kosztowne obliczenia wykonywane tylko raz.
    """

    if lines is None:
        return None


    lines = lines.reshape(-1,4).astype(np.float32)


    x1 = lines[:,0]
    y1 = lines[:,1]
    x2 = lines[:,2]
    y2 = lines[:,3]


    dx = x2-x1
    dy = y2-y1


    length = np.sqrt(
        dx*dx + dy*dy
    )


    angle = np.degrees(
        np.arctan2(dy,dx)
    )

    angle[angle < 0] += 180



    cx = (x1+x2)*0.5
    cy = (y1+y2)*0.5



    widths = widths.reshape(-1)
    prec   = prec.reshape(-1)
    nfa    = nfa.reshape(-1)



    #
    # jakość LSD
    #
    # nfa:
    # małe = lepsze
    #

    quality = np.exp(
        -np.maximum(nfa,0)
    )

    quality += 1e-6



    #
    # końcowa waga linii
    #

    weight = (
        length
        *
        widths
        *
        quality
        /
        (prec+1e-6)
    )


    return {

        "lines": lines,

        "x1":x1,
        "y1":y1,
        "x2":x2,
        "y2":y2,

        "dx":dx,
        "dy":dy,

        "length":length,

        "angle":angle,

        "cx":cx,
        "cy":cy,

        "width":widths,
        "precision":prec,
        "nfa":nfa,

        "quality":quality,

        "weight":weight,

        "count":len(lines)
    }



# =====================================================
# Filtr linii
# =====================================================

def filter_lines(data,
                 min_length=15,
                 min_quality=None):

    if data is None:
        return None


    mask = data["length"] >= min_length


    if min_quality is not None:
        mask &= (
            data["quality"]
            >= min_quality
        )


    result={}


    for k,v in data.items():

        if isinstance(v,np.ndarray):
            result[k]=v[mask]

        else:
            result[k]=v


    result["count"] = len(
        result["lines"]
    )


    return result



# =====================================================
# Dominujące kierunki
# =====================================================

def dominant_directions(
        data,
        top_k=6,
        angle_bins=180):

    """
    Znajduje główne kierunki linii.

    Zwraca listę:

    [
      {
       angle,
       score,
       indexes
      }
    ]

    """

    angles=data["angle"]
    weights=data["weight"]


    histogram=np.zeros(
        angle_bins,
        dtype=np.float64
    )


    bins=(
        angles
        *
        angle_bins
        /
        180
    ).astype(np.int32)


    bins=np.clip(
        bins,
        0,
        angle_bins-1
    )


    np.add.at(
        histogram,
        bins,
        weights
    )


    #
    # wygładzenie
    #

    kernel=np.array(
        [
            0.05,
            0.15,
            0.6,
            0.15,
            0.05
        ]
    )


    histogram=np.convolve(
        np.r_[
            histogram[-2:],
            histogram,
            histogram[:2]
        ],
        kernel,
        mode="same"
    )[2:-2]



    #
    # lokalne maksima
    #

    peaks=[]


    for i in range(angle_bins):

        if (
            histogram[i]
            >
            histogram[(i-1)%angle_bins]
            and
            histogram[i]
            >
            histogram[(i+1)%angle_bins]
        ):

            peaks.append(
                (
                    histogram[i],
                    i*180/angle_bins
                )
            )


    peaks.sort(
        reverse=True
    )



    result=[]


    for score,angle in peaks[:top_k]:


        delta=np.abs(
            ((angles-angle+90)%180)-90
        )


        indexes=np.where(
            delta < 1.5
        )[0]


        result.append(
            {
                "angle":float(angle),
                "score":float(score),
                "indexes":indexes,
                "count":len(indexes)
            }
        )


    return result



# =====================================================
# Pobranie linii dla kierunku
# =====================================================

def get_direction_lines(
        data,
        direction):

    return data["lines"][
        direction["indexes"]
    ]



# =====================================================
# Kąt między liniami
# =====================================================

def angle_difference(a,b):

    d=abs(a-b)

    return min(
        d,
        180-d
    )



# =====================================================
# Centrum grupy
# =====================================================

def group_center(
        data,
        indexes):

    return (
        float(
            np.mean(
                data["cx"][indexes]
            )
        ),
        float(
            np.mean(
                data["cy"][indexes]
            )
        )
    )



# =====================================================
# Debug
# =====================================================

def print_dominant(directions):

    for i,d in enumerate(directions):

        print(
            f"{i}: "
            f"angle={d['angle']:.2f} "
            f"lines={d['count']} "
            f"score={d['score']:.1f}"
        )