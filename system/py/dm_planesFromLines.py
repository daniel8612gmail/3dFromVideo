

from debugging import save_lsd_debug
from dm_lines import activate_filter, dominant_directions, prepare_lsd, print_directions


def planes_from_lines(lsd_res, img, DEBUG_DIR):
    lines,widths,prec,nfa = lsd_res
    img_ch = img.copy()
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


    lsd_data = activate_filter(
        lsd_data,
        min_length=15
    )


    dominant = dominant_directions(
        lsd_data,
        top_k=6
    )


    print_directions(dominant)