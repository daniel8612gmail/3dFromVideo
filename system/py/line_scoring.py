def build_scored_lines(
    line_sets,
    similarity_func
):
    """
    line_sets:
        [
            {
                "lines": [[x1,y1,x2,y2], ...],
                "score": 50
            },
            ...
        ]

    similarity_func(line1,line2)->bool

    return:
        [
            {
                "line": line,
                "score": score
            }
        ]
    """

    # od największego prawdopodobieństwa
    line_sets = sorted(
        line_sets,
        key=lambda x: x["score"],
        reverse=True
    )


    result = []


    # zapamiętanie wykorzystanych linii
    used = [
        set() for _ in line_sets
    ]


    # -------------------------------------------------
    # ETAP 1
    # szukanie potwierdzeń między zbiorami
    # -------------------------------------------------

    for i, high_set in enumerate(line_sets):

        for high_line in high_set["lines"]:

            for j in range(i + 1, len(line_sets)):

                low_set = line_sets[j]

                for low_index, low_line in enumerate(low_set["lines"]):

                    if low_index in used[j]:
                        continue


                    if similarity_func(
                        high_line,
                        low_line
                    ):

                        # przenosimy linię z niższego score

                        result.append(
                            {
                                "line": low_line,
                                "score": low_set["score"]
                            }
                        )


                        used[j].add(low_index)



    # -------------------------------------------------
    # ETAP 2
    # pozostałe linie dodajemy lub wzmacniamy
    # -------------------------------------------------

    for set_id, line_set in enumerate(line_sets):

        score = line_set["score"]


        for line_id, line in enumerate(line_set["lines"]):

            if line_id in used[set_id]:
                continue


            found = False


            for result_line in result:

                if similarity_func(
                    line,
                    result_line["line"]
                ):

                    result_line["score"] += score

                    found = True
                    break


            if not found:

                result.append(
                    {
                        "line": line,
                        "score": score
                    }
                )


    return result










import math


def point_distance(p1, p2):
    return math.hypot(
        p1[0]-p2[0],
        p1[1]-p2[1]
    )


def line_length(line):
    x1,y1,x2,y2 = line

    return math.hypot(
        x2-x1,
        y2-y1
    )


def line_center(line):
    x1,y1,x2,y2 = line

    return (
        (x1+x2)/2,
        (y1+y2)/2
    )


def line_similarity(
    line1,
    line2,
    center_threshold=50,
    endpoint_threshold=30,
    length_ratio_threshold=0.4
):

    # środek
    c1 = line_center(line1)
    c2 = line_center(line2)

    if point_distance(c1,c2) > center_threshold:
        return False


    # długość
    l1 = line_length(line1)
    l2 = line_length(line2)

    if l1 == 0 or l2 == 0:
        return False


    if abs(l1-l2) / max(l1,l2) > length_ratio_threshold:
        return False


    # końce
    x1,y1,x2,y2 = line1
    a1,b1,a2,b2 = line2


    normal = (
        point_distance((x1,y1),(a1,b1)) +
        point_distance((x2,y2),(a2,b2))
    )

    reversed = (
        point_distance((x1,y1),(a2,b2)) +
        point_distance((x2,y2),(a1,b1))
    )


    return min(normal,reversed) < endpoint_threshold














import cv2


def draw_top_score_lines(
    image,
    scored_lines,
    output_path,
    count=1000
):
    """
    Rysuje linie posortowane według score.

    scored_lines:
    [
        {
            "line": [x1,y1,x2,y2],
            "score": score
        }
    ]
    """

    # sortowanie malejąco po score
    sorted_lines = sorted(
        scored_lines,
        key=lambda x: x["score"],
        reverse=True
    )


    debug = image.copy()


    for item in sorted_lines[:count]:

        x1, y1, x2, y2 = item["line"]
        score = item["score"]


        cv2.line(
            debug,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            (0, 255, 0),
            2
        )


        # opcjonalny napis score
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)

        cv2.putText(
            debug,
            str(score),
            (cx, cy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA
        )


    cv2.imwrite(
        output_path,
        debug
    )


    print(
        f"Saved {min(count, len(sorted_lines))} lines: {output_path}"
    )