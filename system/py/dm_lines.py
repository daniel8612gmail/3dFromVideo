import numpy as np


# ==========================================================
# Przygotowanie danych LSD
# ==========================================================

def prepare_lsd(lines, widths, prec, nfa):
    """
    Jednorazowa konwersja wyniku LSD do struktury roboczej.

    Wejście:
        lines  Nx1x4
        widths Nx1
        prec   Nx1
        nfa    Nx1

    Wynik:
        słownik z gotowymi cechami
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
        dx*dx +
        dy*dy
    )


    angle = np.degrees(
        np.arctan2(dy,dx)
    )

    angle[angle < 0] += 180


    #
    # środek
    #

    cx = (x1+x2)*0.5
    cy = (y1+y2)*0.5



    #
    # normalna linii
    #

    theta = np.radians(angle)


    nx = np.sin(theta)
    ny = -np.cos(theta)


    rho = (
        nx*cx +
        ny*cy
    )



    widths = widths.reshape(-1)
    prec = prec.reshape(-1)
    nfa = nfa.reshape(-1)



    #
    # stabilna jakość LSD
    #

    nfa_norm = (
        nfa -
        np.min(nfa)
    )

    nfa_norm /= (
        np.max(nfa_norm)
        +1e-9
    )


    quality = 1.0 - nfa_norm



    #
    # waga końcowa
    #

    weight = (
        length *
        (widths+1) *
        (quality+0.01)
        /
        (prec+0.01)
    )



    return {

        "lines":lines,

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

        "nx":nx,
        "ny":ny,

        "rho":rho,

        "width":widths,
        "precision":prec,
        "nfa":nfa,

        "quality":quality,
        "weight":weight,

        "active":
            np.ones(
                len(lines),
                dtype=bool
            ),

        "id":
            np.arange(
                len(lines)
            )
    }



# ==========================================================
# Filtr aktywnych linii
# ==========================================================

def activate_filter(
        data,
        min_length=15
):
    """
    Nie kopiuje danych.
    Tylko ustawia maskę aktywnych linii.
    """

    data["active"] = (
        data["length"]
        >=
        min_length
    )

    return data



# ==========================================================
# Dominujące kierunki
# ==========================================================

def dominant_directions(
        data,
        top_k=6,
        bins=180
):

    mask = data["active"]


    angles = data["angle"][mask]
    weights = data["weight"][mask]


    histogram = np.zeros(
        bins,
        dtype=np.float64
    )


    ids = (
        angles *
        bins /
        180
    ).astype(np.int32)


    ids=np.clip(
        ids,
        0,
        bins-1
    )


    np.add.at(
        histogram,
        ids,
        weights
    )



    #
    # wygładzenie
    #

    kernel=np.array(
        [
            0.05,
            0.15,
            0.60,
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



    peaks=[]


    for i in range(bins):

        if (
            histogram[i]
            >
            histogram[(i-1)%bins]
            and
            histogram[i]
            >
            histogram[(i+1)%bins]
        ):

            peaks.append(
                (
                    histogram[i],
                    i*180/bins
                )
            )


    peaks.sort(
        reverse=True
    )


    result=[]


    full_angles=data["angle"]


    for score,angle in peaks[:top_k]:

        diff=np.abs(
            ((full_angles-angle+90)%180)-90
        )


        idx=np.where(
            (
                diff < 1.5
            )
            &
            mask
        )[0]


        result.append(
            {
                "angle":
                    float(angle),

                "score":
                    float(score),

                "indexes":
                    idx,

                "count":
                    len(idx)
            }
        )


    return result



# ==========================================================
# Pobranie linii kierunku
# ==========================================================

def get_direction_lines(
        data,
        direction
):

    return data["lines"][
        direction["indexes"]
    ]



# ==========================================================
# Statystyka
# ==========================================================

def print_directions(
        directions
):

    for i,d in enumerate(directions):

        print(
            f"{i}: "
            f"angle={d['angle']:.2f} "
            f"lines={d['count']} "
            f"score={d['score']:.1f}"
        )