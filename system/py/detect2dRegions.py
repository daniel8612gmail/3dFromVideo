import cv2
import numpy as np
from skimage.segmentation import slic
from skimage.color import rgb2lab
from skimage.measure import regionprops
import json
from pathlib import Path


def detect_texture_regions(
        image_path,
        output_dir,
        n_segments=300,
        compactness=20,
        min_area=500
):

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    img = cv2.imread(str(image_path))

    if img is None:
        raise Exception("Nie można otworzyć obrazu")

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    h, w = rgb.shape[:2]


    # ==========================
    # 1. SLIC superpixels
    # ==========================

    labels = slic(
        rgb,
        n_segments=n_segments,
        compactness=compactness,
        start_label=0
    )


    regions = []

    lab = rgb2lab(rgb)


    # ==========================
    # 2. Parametry regionów
    # ==========================

    for r in regionprops(labels + 1):

        area = r.area

        if area < min_area:
            continue


        coords = r.coords

        pixels = lab[
            coords[:,0],
            coords[:,1]
        ]


        mean_color = pixels.mean(axis=0)
        texture = pixels.std()


        regions.append(
            {
                "id": int(r.label),
                "area": int(area),
                "center": [
                    float(r.centroid[1]),
                    float(r.centroid[0])
                ],
                "mean_lab": [
                    float(x)
                    for x in mean_color
                ],
                "texture": float(texture),
                "bbox":[
                    int(r.bbox[1]),
                    int(r.bbox[0]),
                    int(r.bbox[3]),
                    int(r.bbox[2])
                ]
            }
        )


    # sortowanie od największych

    regions.sort(
        key=lambda x:x["area"],
        reverse=True
    )


    # ==========================
    # 3. Rysowanie
    # ==========================

    result = img.copy()

    rng=np.random.default_rng(1)


    for i,r in enumerate(regions[:50]):

        color = rng.integers(
            0,255,3
        ).tolist()

        mask = (
            labels ==
            r["id"]-1
        )


        result[mask] = (
            0.5*result[mask]
            +
            0.5*np.array(color)
        )


        ys,xs=np.where(mask)

        if len(xs):

            cv2.putText(
                result,
                f"{i+1}:{r['area']}",
                (
                    int(xs.mean()),
                    int(ys.mean())
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255,255,255),
                2
            )


            contours,_=cv2.findContours(
                mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            cv2.drawContours(
                result,
                contours,
                -1,
                (0,0,0),
                2
            )


    # ==========================
    # zapis
    # ==========================

    cv2.imwrite(
        str(output_dir/"texture_regions.png"),
        result
    )


    with open(
        output_dir/"texture_regions.json",
        "w",
        encoding="utf8"
    ) as f:

        json.dump(
            {
                "image_size":[w,h],
                "regions":regions
            },
            f,
            indent=2
        )


    print(
        f"Wykryto {len(regions)} regionów"
    )

    print(
        "Największe:"
    )

    for r in regions[:10]:
        print(
            r["id"],
            r["area"],
            "texture=",
            round(r["texture"],2)
        )















def texture_segmentation(image_path, out):

    img=cv2.imread(image_path)

    lab=cv2.cvtColor(
        img,
        cv2.COLOR_BGR2LAB
    )


    # lokalne odchylenie tekstury
    mean=cv2.blur(
        lab.astype(np.float32),
        (21,21)
    )

    sqmean=cv2.blur(
        lab.astype(np.float32)**2,
        (21,21)
    )

    variance=np.sqrt(
        sqmean-mean**2
    )


    texture=np.mean(
        variance,
        axis=2
    )


    # niska tekstura = powierzchnia
    mask=np.zeros_like(texture,dtype=np.uint8)

    mask[texture<8]=255


    # czyszczenie
    kernel=cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (15,15)
    )

    mask=cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    mask=cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        kernel
    )


    contours,_=cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )


    result=img.copy()


    for c in contours:

        area=cv2.contourArea(c)

        if area>1000:

            cv2.drawContours(
                result,
                [c],
                -1,
                (0,255,0),
                3
            )

            x,y,w,h=cv2.boundingRect(c)

            cv2.putText(
                result,
                str(int(area)),
                (x,y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0,0,255),
                2
            )


    cv2.imwrite(
        out,
        result
    )
    
    
    










def detect_gimp_like_edges(
        image_path,
        output_path,
        sp=40,
        sr=30,
        canny_low=40,
        canny_high=120
):
    """
    Wykrywanie krawędzi podobne do GIMP:
    MeanShift + Canny

    image_path  - wejściowe zdjęcie
    output_path - zapis wyniku PNG/JPG

    sp - wielkość obszaru wygładzania
    sr - tolerancja koloru
    """

    img = cv2.imread(image_path)

    if img is None:
        raise Exception(
            f"Nie można otworzyć {image_path}"
        )


    # 1. Wygładzenie zachowujące granice
    filtered = cv2.pyrMeanShiftFiltering(
        img,
        sp=sp,
        sr=sr
    )


    # 2. Szarość
    gray = cv2.cvtColor(
        filtered,
        cv2.COLOR_BGR2GRAY
    )


    # 3. Krawędzie
    edges = cv2.Canny(
        gray,
        canny_low,
        canny_high
    )


    # 4. Narysowanie krawędzi na oryginale
    result = img.copy()

    result[edges > 0] = (
        0, 
        0,
        255
    )


    # 5. Zapis dodatkowych obrazów

    cv2.imwrite(
        output_path,
        result
    )

    cv2.imwrite(
        output_path.replace(
            ".png",
            "_filtered.png"
        ),
        filtered
    )

    cv2.imwrite(
        output_path.replace(
            ".png",
            "_edges.png"
        ),
        edges
    )


    print(
        "Zapisano:",
        output_path
    )



if __name__=="__main__":

    # detect_texture_regions(
    #     "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001.jpg",
    #     "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001",
    #     n_segments=500,
    #     compactness=30,
    #     min_area=1000
    # )
    
    # texture_segmentation(
    #     "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001.jpg",
    #     "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001\\texture_result2.png",
    # )
    
    
    detect_gimp_like_edges(
        "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001.jpg",
        "D:\\GIT\\3dFromVideo\\users\\user_000001\\devices\\device_000001\\videos\\demo_video_FHD\\frames\\frame_0001\\detect_gimp_like_edges.png",
        sp=50,
        sr=40
    )