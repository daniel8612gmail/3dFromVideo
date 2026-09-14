import argparse
from pathlib import Path

import cv2
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument(
"-i",
required=True,
help="Path to input directory"
)
args = parser.parse_args()

INPUT_DIR = Path(args.i)

IMAGE_EXTENSIONS = {
".jpg",
".jpeg",
".png",
".webp"
}

COMPARE_WIDTH = 320
COMPARE_HEIGHT = 180


MIN_CHANGE = 0.055

LARGE_CHANGE = 0.25

ORB_FEATURES = 1800

ORB_RATIO = 0.75

MIN_GOOD_MATCHES = 35

MIN_INLIERS = 15

MIN_INLIER_RATIO = 0.25

MIN_BLUR = 80.0

EXTREME_LOW = 10.0
EXTREME_HIGH = 245.0

MIN_STD = 7.0

MAX_CONSECUTIVE_REMOVALS = 100

CHECKPOINT = 100

def resize_small(gray):
    return cv2.resize(
    gray,
    (COMPARE_WIDTH, COMPARE_HEIGHT),
    interpolation=cv2.INTER_AREA
    )

def image_change(a, b):
    """
    Bardzo szybki pomiar różnicy.

    0.0 = praktycznie identyczne
    1.0 = całkowicie różne
    """

    a = resize_small(a)
    b = resize_small(b)

    diff = cv2.absdiff(a, b)

    return float(diff.mean()) / 255.0

def blur_score(gray):
    return float(
    cv2.Laplacian(
    gray,
    cv2.CV_64F
    ).var()
    )

def is_bad_frame(gray):
    """
    Wykrywa klatki, na których tracking może być niemożliwy.

    Nie usuwamy ich automatycznie.
    Są traktowane jako potencjalne oślepienie.
    """

    mean = float(gray.mean())
    std = float(gray.std())

    if mean <= EXTREME_LOW:
        return True

    if mean >= EXTREME_HIGH:
        return True

    if std <= MIN_STD:
        return True

    return False

def get_features(gray, orb):
    return orb.detectAndCompute(
    gray,
    None
    )

def geometric_matches(
kp1,
des1,
kp2,
des2,
matcher
):
    """
    ORB + Lowe ratio + RANSAC.

    Zwraca:
        good_matches
        inliers
        inlier_ratio
    """

    if des1 is None or des2 is None:
        return 0, 0, 0.0

    if len(des1) < 2 or len(des2) < 2:
        return 0, 0, 0.0

    matches = matcher.knnMatch(
        des1,
        des2,
        k=2
    )

    good = []

    for pair in matches:

        if len(pair) != 2:
            continue

        m, n = pair

        if m.distance < ORB_RATIO * n.distance:
            good.append(m)

    if len(good) < 8:
        return len(good), 0, 0.0

    pts1 = np.float32([
        kp1[m.queryIdx].pt
        for m in good
    ]).reshape(-1, 1, 2)

    pts2 = np.float32([
        kp2[m.trainIdx].pt
        for m in good
    ]).reshape(-1, 1, 2)

    try:

        _, mask = cv2.findHomography(
            pts1,
            pts2,
            cv2.RANSAC,
            5.0
        )

    except cv2.error:

        return len(good), 0, 0.0

    if mask is None:
        return len(good), 0, 0.0

    inliers = int(
        mask.ravel().sum()
    )

    ratio = (
        inliers /
        max(len(good), 1)
    )

    return (
        len(good),
        inliers,
        ratio
    )

def main():
    print(INPUT_DIR)
    files = sorted(
        p for p in INPUT_DIR.iterdir()
        if (
            p.is_file()
            and p.suffix.lower()
            in IMAGE_EXTENSIONS
        )
    )

    if not files:

        print("Brak zdjec w katalogu.")
        return

    orb = cv2.ORB_create(
        nfeatures=ORB_FEATURES
    )

    matcher = cv2.BFMatcher(
        cv2.NORM_HAMMING
    )

    # --------------------------------------------------------
    # OSTATNIA ZACHOWANA KLATKA
    # --------------------------------------------------------

    reference_gray = None
    reference_kp = None
    reference_des = None
    reference_path = None

    # --------------------------------------------------------
    # STATYSTYKI
    # --------------------------------------------------------

    selected = 0
    removed = 0
    errors = 0

    consecutive_removals = 0

    # --------------------------------------------------------
    # PRZEJŚCIE PO KLATKACH
    # --------------------------------------------------------

    for index, path in enumerate(files):

        img = cv2.imread(
            str(path),
            cv2.IMREAD_GRAYSCALE
        )

        if img is None:

            print(
                f"[ERROR]  {path.name}"
            )

            errors += 1
            continue

        # ====================================================
        # PIERWSZA KLATKA
        # ====================================================

        if reference_gray is None:

            kp, des = get_features(
                img,
                orb
            )

            reference_gray = img
            reference_kp = kp
            reference_des = des
            reference_path = path

            selected += 1
            consecutive_removals = 0

            print(
                f"[KEEP]   {path.name:30} "
                f"FIRST "
                f"features={len(kp)}"
            )

            continue

        # ====================================================
        # CHECKPOINT
        # ====================================================
        #
        # To zabezpiecza przed sytuacją, w której algorytm
        # z jakiegoś powodu przez bardzo długi czas uważa
        # kolejne klatki za podobne.
        #
        # Checkpoint jest wykonywany przed kosztownym ORB.
        # ====================================================

        checkpoint = (
            CHECKPOINT > 0
            and index > 0
            and index % CHECKPOINT == 0
        )

        forced = (
            consecutive_removals
            >= MAX_CONSECUTIVE_REMOVALS
        )

        if checkpoint or forced:

            kp, des = get_features(
                img,
                orb
            )

            if forced:

                reason = (
                    f"FORCED AFTER "
                    f"{consecutive_removals} REMOVALS"
                )

            else:

                reason = "CHECKPOINT"

            print(
                f"[KEEP]   {path.name:30} "
                f"{reason} "
                f"features={len(kp)}"
            )

            reference_gray = img
            reference_kp = kp
            reference_des = des
            reference_path = path

            selected += 1
            consecutive_removals = 0

            continue

        # ====================================================
        # SZYBKI TEST ZMIANY
        # ====================================================

        change = image_change(
            reference_gray,
            img
        )

        # ====================================================
        # BARDZO MAŁA ZMIANA
        # ====================================================
        #
        # Nie uruchamiamy ORB.
        # To jest najczęstszy przypadek w filmie i właśnie
        # tutaj oszczędzamy najwięcej czasu.
        # ====================================================

        if change < MIN_CHANGE:

            print(
                f"[REMOVE] {path.name:30} "
                f"change={change:.3f} "
                f"SIMILAR "
                f"[{consecutive_removals + 1}/"
                f"{MAX_CONSECUTIVE_REMOVALS}]"
            )

            path.unlink()

            removed += 1
            consecutive_removals += 1

            continue

        # ====================================================
        # JAKOŚĆ KLATKI
        # ====================================================

        blur = blur_score(img)
        bad = is_bad_frame(img)

        # ----------------------------------------------------
        # OŚLEPIENIE / BIAŁA KLATKA
        # ----------------------------------------------------
        #
        # Nie ustawiamy jej jako reference.
        #
        # Jeżeli jest wyraźnie inna od reference, zachowujemy
        # ją, bo może być istotna dla późniejszego odzyskania
        # trackingu.
        # ----------------------------------------------------

        if bad:

            print(
                f"[KEEP]   {path.name:30} "
                f"BLINDING / LOW INFORMATION "
                f"change={change:.3f}"
            )

            selected += 1
            consecutive_removals = 0

            # WAŻNE:
            # nie zastępujemy nią reference.
            #
            # Następna normalna klatka będzie nadal porównywana
            # z ostatnią dobrą klatką.

            continue

        # ====================================================
        # ROZMYCIE
        # ====================================================

        if blur < MIN_BLUR:

            print(
                f"[REMOVE] {path.name:30} "
                f"blur={blur:.1f} "
                f"change={change:.3f} "
                f"BLUR"
            )

            path.unlink()

            removed += 1
            consecutive_removals += 1

            continue

        # ====================================================
        # DUŻA ZMIANA
        # ====================================================
        #
        # Nie zachowujemy automatycznie.
        #
        # Duża różnica może być np.:
        #   - przejazdem przez szybę,
        #   - oślepieniem,
        #   - zmianą ekspozycji,
        #   - gwałtownym ruchem.
        #
        # Dlatego nadal sprawdzamy ORB/RANSAC.
        # ====================================================

        kp, des = get_features(
            img,
            orb
        )

        good, inliers, ratio = geometric_matches(
            reference_kp,
            reference_des,
            kp,
            des,
            matcher
        )

        # ====================================================
        # DOBRA GEOMETRIA
        # ====================================================

        geometry_ok = (
            good >= MIN_GOOD_MATCHES
            and inliers >= MIN_INLIERS
            and ratio >= MIN_INLIER_RATIO
        )

        # ====================================================
        # KAMERA PRAWDOPODOBNIE SIĘ PRZEMIEŚCIŁA
        # ====================================================

        if geometry_ok:

            print(
                f"[KEEP]   {path.name:30} "
                f"change={change:.3f} "
                f"matches={good} "
                f"inliers={inliers} "
                f"ratio={ratio:.2f}"
            )

            reference_gray = img
            reference_kp = kp
            reference_des = des
            reference_path = path

            selected += 1
            consecutive_removals = 0

            continue

        # ====================================================
        # BARDZO DUŻA ZMIANA + BRAK GEOMETRII
        # ====================================================
        #
        # To może być:
        #   - oślepienie,
        #   - szybki obrót,
        #   - zasłonięcie,
        #   - wejście w nowy obszar.
        #
        # Nie wyrzucamy od razu.
        #
        # Jeżeli zmiana jest naprawdę duża, zachowujemy klatkę
        # jako potencjalny punkt przejścia.
        # ====================================================

        if change >= LARGE_CHANGE:

            print(
                f"[KEEP]   {path.name:30} "
                f"NEW VIEW / RECOVERY "
                f"change={change:.3f} "
                f"matches={good} "
                f"inliers={inliers}"
            )

            reference_gray = img
            reference_kp = kp
            reference_des = des
            reference_path = path

            selected += 1
            consecutive_removals = 0

            continue

        # ====================================================
        # KIEPSKI KANDYDAT
        # ====================================================

        print(
            f"[REMOVE] {path.name:30} "
            f"change={change:.3f} "
            f"matches={good} "
            f"inliers={inliers} "
            f"ratio={ratio:.2f} "
            f"WEAK"
        )

        path.unlink()

        removed += 1
        consecutive_removals += 1

    # ========================================================
    # PODSUMOWANIE
    # ========================================================

    print()
    print("=" * 70)
    print(
        f"Wszystkich klatek : {len(files)}"
    )
    print(
        f"Pozostawionych     : {selected}"
    )
    print(
        f"Usuniętych         : {removed}"
    )
    print(
        f"Błędów             : {errors}"
    )
    print("=" * 70)

if __name__ == "__main__":
    main()