from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import black


filename = "szachownica_A4.pdf"

# A4 poziomo
page_size = landscape(A4)

c = canvas.Canvas(
    filename,
    pagesize=page_size
)


# parametry planszy
square = 35 * mm

cols = 7   # liczba pól poziomo
rows = 5   # liczba pól pionowo


page_w, page_h = page_size


board_w = cols * square
board_h = rows * square


# wyśrodkowanie
x0 = (page_w - board_w) / 2
y0 = (page_h - board_h) / 2


for row in range(rows):
    for col in range(cols):

        if (row + col) % 2 == 0:

            c.setFillColor(black)

            c.rect(
                x0 + col * square,
                y0 + row * square,
                square,
                square,
                fill=1,
                stroke=0
            )


# ramka kontrolna planszy
c.setStrokeColor(black)
c.rect(
    x0,
    y0,
    board_w,
    board_h,
    fill=0,
    stroke=0
)


c.save()

print("Utworzono:", filename)