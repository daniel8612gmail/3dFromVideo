import cv2
import numpy as np
from debugging import save_debug_contours, save_debug_lines, save_lsd_debug
from merge_lines_fast import merge_lines
from adoptive_smooth import adaptive_smooth_edges
from line_scoring import build_scored_lines, line_similarity, draw_top_score_lines
from merge_segments import merge_lsd_results
from dm_poligonFromLine import build_polygon_from_lines, draw_polygon_result
from dm_lines import *

def GenerateLineSet(edges_array, thresholds):
    line_sets = []
    h, w = edges_array[0].shape
    min_line_length = int(min(h, w) * 0.03)
    max_line_gap = int(min(h, w) * 0.01)
    for channel_id, edges in enumerate(edges_array):
        for threshold, score in thresholds:
            print(f"Thresholds: {threshold}, min_line_length: {min_line_length}, max_line_gap: {max_line_gap}")
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=threshold,
                minLineLength=min_line_length,
                maxLineGap=max_line_gap
            )
            if lines is None:
                print("Brak lini")
                continue
            print(" Liczba lini:", len(lines))
            line_sets.append({
                "lines": lines,
                "score": score
            })  
    return line_sets

def convertLineFormat(lines):
    converted_lines = []
    for l in lines:
        # print("line: ", l)
        x1, y1, x2, y2 = l
        converted_lines.append(
            (
                (float(x1), float(y1)),
                (float(x2), float(y2))
            )
        )
    return converted_lines

def edgedetection(img, obj_id, geometry_dir):    
    obj_dir = (geometry_dir / f"object_{obj_id:03d}")
    obj_dir.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR = obj_dir
    img_ch = cv2.split(img)
    lsd_results=[]
    
    # Edges
    img_b, img_g, img_r = cv2.split(img)
    edges_r = cv2.Canny(img_r,50,150)
    edges_g = cv2.Canny(img_g,50,150)
    edges_b = cv2.Canny(img_b,50,150)
    edges_array = [edges_b, edges_g, edges_r]
    edges_rgb = cv2.merge((edges_b, edges_g, edges_r))
    cv2.imwrite(DEBUG_DIR / "edges_rgb.png", edges_rgb)

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # gray for test    
    img_ch = [img_gray]

    
    #========================================
    # For RGB Segment detection
    for i, img_i in enumerate(img_ch, start=1): # testowo tylko 1 janał
        gray_img = img_i
        lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_ADV)
        lsd_res = lsd.detect(gray_img)
        lines, widths, prec, nfa = lsd_res
        if lines is None:
            print(f"Brak linii dla kanału {i}")
            continue
        linesFormated = convertLineFormat(lines)
        polygon = build_polygon_from_lines(linesFormated)

        draw_polygon_result(
            gray_img,
            polygon,
            DEBUG_DIR / f"02.{i}poligons.jpg"
        )
        
        lsd_results.append(lsd_res)
        if lines is not None:
            if lines.ndim == 3:
                segments = lines[:, 0, :]
            else:
                segments = lines
            save_lsd_debug(
                gray_img,
                segments,
                nfa,
                DEBUG_DIR / f"01.{i}debug_lsd_segments.png"
            )
    lsd_res = merge_lsd_results(
        lsd_results,
        angle_thr=2,
        dist_thr=6
    )   
    lines,widths,prec,nfa = lsd_res
    if lines.ndim == 3:
        segments = lines[:, 0, :]
    else:
        segments = lines
    save_lsd_debug(
                    img_ch[0],
                    segments,
                    nfa,
                    DEBUG_DIR / f"01.debug_lsd_segments.png"
                )
    
    lsd_data = prepare_lsd(
        lines,
        widths,
        prec,
        nfa
    )


    lsd_data = filter_lines(
        lsd_data,
        min_length=15
    )


    dominant = dominant_directions(
        lsd_data,
        top_k=6
    )


    print_dominant(dominant)
    # geometry = process_lines(segments)    
    # print(len(geometry["groups"]))
    # print(len(geometry["corners"]))
    
    # # save_geometry(
    # #     obj_dir / "geometry.json",
    # #     geometry
    # # )
    # image = img.copy()
    # debug = draw_geometry(image, geometry)
    # cv2.imwrite(
    #     obj_dir / "geometry_debug1.png",
    #     debug
    # ) 
    # debug2 = draw_geometry_lines(
    #     image.shape,
    #     geometry
    # )
    # cv2.imwrite(
    #     obj_dir / "geometry_debug2.png",
    #     debug2
    # )
    
    # debug2 = draw_geometry_intersections(
    #     image.shape,
    #     geometry
    # )
    # cv2.imwrite(
    #     obj_dir / "geometry_intersections.png",
    #     debug2
    # )
    
    
    return
    #========================================
    # line detection    
    
    img_b, img_g, img_r = cv2.split(img)
    edges_r = cv2.Canny(img_r,50,150)
    edges_g = cv2.Canny(img_g,50,150)
    edges_b = cv2.Canny(img_b,50,150)
    edges_array = [edges_b, edges_g, edges_r]
    edges_rgb = cv2.merge((edges_b, edges_g, edges_r))
    cv2.imwrite(DEBUG_DIR / "edges_rgb.png", edges_rgb)
    edge_pixels = 5000
    print("edge_pixels:", edge_pixels)
    thresholds = [
        (int(edge_pixels * 0.06), 50),
        (int(edge_pixels * 0.04), 40),
        (int(edge_pixels * 0.03), 30),
        (int(edge_pixels * 0.02), 20),
        (int(edge_pixels * 0.01), 15),
    ]
    line_sets = GenerateLineSet(edges_array, thresholds)
    for i, lines in enumerate(line_sets, start=1):
        save_debug_lines(obj_dir / f"01.01.{lines["score"]}.{i}.lines.png", edges_r.shape, lines["lines"])
        print(f"Was lines: {len(lines["lines"])}")
        lines["lines"] = merge_lines(
            lines["lines"],
            angle_threshold=2,
            distance_threshold=6,
            gap_threshold=20,
            angle_bin=10,
            max_length=8000
        )
        print(f"Score: {lines["score"]} Merged to: {len(lines["lines"])}")
        save_debug_lines(obj_dir / f"01.01.{lines["score"]}.{i}.lines_merged.png", edges_r.shape, lines["lines"])
        
        
    print(f"Scoring...")
    result_lines = build_scored_lines(
        line_sets,
        line_similarity
    )
    # for l in result:
    #     print(
    #         l["line"],
    #         l["score"]
    #     )
    
    draw_top_score_lines(
        img,
        result_lines,
        obj_dir / "debug_scored_lines.png",
        1000
    )
                
        
        
        
        
    
def edgedetection1(object_gray, obj_id, geometry_dir):
    obj_dir = (geometry_dir / f"object_{obj_id:03d}")
    obj_dir.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR = obj_dir
 # Canny tylko na obiekcie
    edges = cv2.Canny(object_gray,50,150)

    # dodatkowo ograniczenie krawędzi
    # dokładnie do maski
    #edges = cv2.bitwise_and(edges,mask)

    # Kontury
    contours, _ = cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)

    lines = adaptive_smooth_edges(
        object_gray,
        "lines"
    )
    save_debug_lines(obj_dir / "01.5.debug_edges_smooth.png", edges.shape, lines)


    exit()

    # Linie
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi/180,
        threshold=60,
        minLineLength=80,
        maxLineGap=20
    )

    
    # Katalog obiektu
    obj_dir = (geometry_dir / f"object_{obj_id:03d}")
    obj_dir.mkdir(parents=True, exist_ok=True)
    #print("Saving geometry for object:", obj_id, "in:", obj_dir)

    cv2.imwrite(
        str(DEBUG_DIR / "05_edges.png"),
        edges
    )

    # Zapis edges
    cv2.imwrite(str(obj_dir / "edges.png"), edges)
    # Zapis edges jako bitpacked npz
    edges_binary = edges > 0
    edges_packed = np.packbits(edges_binary)
    np.savez_compressed(
        obj_dir / "edges.npz",
        data=edges_packed,
        shape=edges.shape
    )

    # Zapis konturów
    contours_data = np.array(
        [
            c.reshape(-1, 2)
            for c in contours
        ],
        dtype=object
    )

    np.save(
        obj_dir / "contours.npy",
        contours_data,
        allow_pickle=True
    )
    
    # Zapis linii
    save_lines_min(
        lines,
        obj_dir / "lines.npy",
        obj_dir / "lines.json"
    )
    
    # Debug PNG linii
    save_debug_lines(
        obj_dir / "01.1.lines.png",
        edges.shape,
        lines
    )

    # Debug PNG linii
    save_debug_lines(
        obj_dir / "01.3.lines_merged.png",
        edges.shape,
        lines_merged
    )
    
    
    
    
    
    
    print("CORNERS")
    # geometry_corners = extract_corners(lines)
    
    # with open(
    #     obj_dir / "corners.json",
    #     "w"
    # ) as f:
    #     json.dump(
    #         geometry_corners,
    #         f,
    #         indent=2
    #     )

    # geometry = process_lines(lines)    
    # print(len(geometry["groups"]))
    # print(len(geometry["corners"]))
    
    # save_geometry(
    #     obj_dir / "geometry.json",
    #     geometry
    # )
    # image = object_gray.copy()
    # debug = draw_geometry(image, geometry)
    # cv2.imwrite(
    #     obj_dir / "geometry_debug1.png",
    #     debug
    # ) 
    # debug2 = draw_geometry_lines(
    #     edges.shape,
    #     geometry
    # )
    # cv2.imwrite(
    #     obj_dir / "geometry_debug2.png",
    #     debug2
    # )
    
    # debug2 = draw_geometry_intersections(
    #     edges.shape,
    #     geometry
    # )
    # cv2.imwrite(
    #     obj_dir / "geometry_intersections.png",
    #     debug2
    # )

    # Debug PNG konturów
    save_debug_contours(
        obj_dir / "contours.png",
        edges.shape,
        contours
    )

