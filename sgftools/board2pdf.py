#!/usr/bin/python
# print a go board using reportlab

import os
import sys
from reportlab.lib.units import inch
from reportlab.lib.colors import black, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pickle
import textwrap
import math

unit = .3 * inch
coordinates = True

def get_position(x, y, crop):
    x_p = inch + (x - crop[0]) * unit
    y_p = inch + (y - crop[1]) * unit
    return x_p, y_p

def getLines(text, width):
    lines = []
    for block in text.split('\n'):
        for line in textwrap.wrap(block, width):
            lines.append(line)
    return lines

def drawComment(c, text, crop):
    TEXTWIDTH = 50
    FONTSIZE = 22
    LINEHEIGHT = 0.3
    x_pos, _ = get_position( (crop[2] + crop[0]) / 2, 0, crop )


    lines = getLines(text, TEXTWIDTH)
    if len(lines) > 12:
        LINEHEIGHT = 0.25
        TEXTWIDTH = 65
        FONTSIZE = 18
        lines = getLines(text, TEXTWIDTH)
    if len(lines) > 15:
        LINEHEIGHT = 0.20
        TEXTWIDTH = 80
        FONTSIZE = 14
        lines = getLines(text, TEXTWIDTH)

    c.saveState()
    c.setFont('Helvetica', FONTSIZE)
    c.setFillColor(black)
    c.setStrokeColor(black)

    for i, line in enumerate(lines):
        c.drawCentredString( x_pos, 0.25*inch - i*LINEHEIGHT*inch, line )

    c.restoreState()

def drawFooter(c, s):
    c.saveState()
    c.setFont('Helvetica', 8)
    c.setFillColor(black)
    c.setStrokeColor(black)
    c.drawString( 0*inch, -3.3*inch, s )

    c.restoreState()

def triangle( x, y, r, c ):
    p = c.beginPath()

    p.moveTo(x, y + r)
    p.lineTo(x + r * math.sqrt(3) / 2, y - r / 2)
    p.lineTo(x - r * math.sqrt(3) / 2, y - r / 2)
    p.lineTo(x, y + r)

    return p

def drawMarkup(c, markup, stones, crop):
    c.saveState()
    c.setFont('Helvetica', 16)

    cr = 0.3*unit
    tr = 0.35*unit
    rr = 0.25*unit
    br = 0.4*unit

    for x,y in markup:
        strokecolor = black
        x_p, y_p = get_position(x, y, crop)
        c.setFillAlpha(1.0)

        if (x,y) not in stones:
            c.setFillColor(white)
            c.setStrokeColor(white)
            c.circle(x_p, y_p, br, 1, 1)
        elif stones[(x,y)] == 'b':
            strokecolor = white

        c.setFillColor(strokecolor)
        c.setStrokeColor(strokecolor)

        m = markup[(x,y)]
        if m == '#':
            c.setFillAlpha(0.0)
            c.rect( x_p - rr, y_p - rr, 2*rr, 2*rr, stroke=1, fill=0 )
        elif m == '^':
            c.setFillAlpha(0.0)
            p = triangle( x_p, y_p, tr, c )
            c.drawPath( p, stroke=1, fill=0 )
        elif m == '0':
            c.setFillAlpha(0.0)
            c.circle(x_p, y_p, cr, stroke=1, fill=0)
        else:
            c.drawCentredString(x_p, y_p - 0.23*unit, m)

    c.restoreState()

def drawStones(c, stones, crop):
    lw = 0.01 * inch
    sw = 0.47 * unit

    c.saveState()
    c.setLineWidth(lw)

    for x,y in stones:
        color = stones[(x,y)]
        get_position(x, y, crop)

        if color == 'b':
            fillcolor = black
        if color == 'w':
            fillcolor = white

        c.setStrokeColor(black)
        c.setFillColor(fillcolor)

        x_pos, y_pos = get_position(x, y, crop)

        c.circle(x_pos, y_pos, sw, 1, 1)

    c.restoreState()

def drawBoard(c, size, crop):
    c.translate(4.25*inch - inch - 0.5 * (crop[2]-crop[0]-1) * unit, 3.5*inch)

    lw = 0.01 * inch

    bd = 0.5 * unit
    bw = 0.03 * inch
    bm = 0.01 * inch
    dw = 0.05

    x_min = crop[0] - 0.5 if crop[0] > 0 else 0
    y_min = crop[1] - 0.5 if crop[1] > 0 else 0
    x_max = crop[2] - 0.5 if crop[2] < size else size-1
    y_max = crop[3] - 0.5 if crop[3] < size else size-1


    c.setLineWidth(lw)
    for x in xrange(crop[0], crop[2]):
        x_p1, y_p1 = get_position(x, y_min, crop)
        x_p2, y_p2 = get_position(x, y_max, crop)
        c.line( x_p1, y_p1, x_p2, y_p2 )

    for y in xrange(crop[1], crop[3]):
        x_p1, y_p1 = get_position(x_min, y, crop)
        x_p2, y_p2 = get_position(x_max, y, crop)
        c.line( x_p1, y_p1, x_p2, y_p2 )

    if crop[0] == 0:
        c.setLineWidth(bw)
        c.line( inch - bd, inch - bm - bd, inch - bd, inch + (crop[3] - crop[1] - 1) * unit + bm + bd )
    if crop[1] == 0:
        c.setLineWidth(bw)
        c.line( inch - bm - bd, inch - bd, inch + (crop[2] - crop[0] - 1) * unit + bm + bd, inch - bd )
    if crop[2] == size:
        c.setLineWidth(bw)
        c.line( inch + (crop[2] - crop[0] - 1) * unit + bd, inch - bm - bd, inch + (crop[2] - crop[0] - 1) * unit + bd, inch + (crop[3] - crop[1] - 1) * unit + bm + bd )
    if crop[3] == size:
        c.setLineWidth(bw)
        c.line( inch - bm - bd, inch + (crop[3] - crop[1] - 1) * unit + bd, inch + (crop[2] - crop[0] - 1) * unit + bm + bd, inch + (crop[3] - crop[1] - 1) * unit + bd )

    if size == 19:
        for i in range(3):
            for j in range(3):
                x = i*6 + 3
                y = j*6 + 3
                if x > crop[0] and x < crop[2] and y > crop[1] and y < crop[3]:
                    c.circle(inch + (x - crop[0]) * unit, inch + (y-crop[1]) * unit, dw * unit, 1, 1)
    elif size == 13:
        for i in range(3):
            for j in range(3):
                x = i*3 + 3
                y = j*3 + 3
                if x > crop[0] and x < crop[2] and y > crop[1] and y < crop[3]:
                    c.circle(inch + (x - crop[0]) * unit, inch + (y-crop[1]) * unit, dw * unit, 1, 1)
    elif size == 9:
        for i in range(2):
            for j in range(2):
                x = i*4 + 2
                y = j*4 + 2
                if x > crop[0] and x < crop[2] and y > crop[1] and y < crop[3]:
                    c.circle(inch + (x - crop[0]) * unit, inch + (y-crop[1]) * unit, dw * unit, 1, 1)
        x = 4
        y = 4
        if x > crop[0] and x < crop[2] and y > crop[1] and y < crop[3]:
            c.circle(inch + x * unit, inch + y * unit, dw * unit, 1, 1)
            c.circle(inch + (x - crop[0]) * unit, inch + (y-crop[1]) * unit, dw * unit, 1, 1)

    return c

if __name__ == '__main__':
    if len(sys.argv) <= 2:
        print >>sys.stderr, 'Usage: goboard.py POSITION OUTPUT.pdf'
        print >>sys.stderr, 'where POSITION is the name of a file containing a pickled go board position'

    with open(sys.argv[1], 'r') as pypfile:
        board = pickle.load( pypfile )

    print "Formatting: ", sys.argv[1], "to", sys.argv[2]

    c = canvas.Canvas( sys.argv[2], pagesize=letter )

    drawBoard( c, board['size'], board['crop'] )
    drawStones( c, board['stones'], board['crop'] )
    drawMarkup( c, board['markup'], board['stones'], board['crop'] )
    drawComment( c, board['text'], board['crop'] )
    drawFooter( c, board['source'] )

    c.showPage()
    c.save()

    # os.system('convert -density 400x400 %s.pdf -resize 17%% %s.png' % (sys.argv[1], sys.argv[1]))

