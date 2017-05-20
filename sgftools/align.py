import numpy as np
import optparse
import gotools
import sys
import re

class Transform(object):
    def __init__(self, sgf, SZ):
        self.SZ = SZ
        self.C = sgf.cursor()

        self.coord_map = dict(zip(range(26), 'abcdefghijklmnopqrstuvwxyz'))
        positions = np.array([[(i, j) for j in xrange(self.SZ)] for i in xrange(self.SZ)])
        mapped_rot90 = np.rot90( positions, 1 )

        self.rot90_mapping = {}
        for j in xrange(self.SZ):
            for i in xrange(self.SZ):
                i2,j2 = mapped_rot90[i,j]
                self.rot90_mapping[i,j] = (i2,j2)

    def get_letters( self, coords ):
        x, y = coords
        return self.coord_map[x] + self.coord_map[y]

    def get_coords( self, pos ):
        x = ord(pos[0])-97
        y = ord(pos[1])-97

        return x,y

    def apply_rot90(self, pos):
        coords = self.get_coords(pos)
        return self.get_letters( self.rot90_mapping[coords] )

    def apply_fliplr(self, pos):
        x, y = self.get_coords(pos)
        x = self.SZ - (x+1)
        return self.get_letters( (x, y) )

    def apply_tree(self, op):
        for item in self.C.node:
            for i in xrange(len(item.data)):
                D = item.data[i]
                if re.match('^[a-z][a-z]$', D):
                    item.data[i] = op(D)
                elif re.match('^[a-z][a-z]:.*$', D):
                    pos, label = D.split(':')
                    item.data[i] = "%s:%s" % (op(pos), label)

        for i in xrange(0, len( self.C.children )):
            self.C.next( i )
            self.apply_tree(op)
            self.C.previous()

    def rot90(self):
        self.apply_tree(self.apply_rot90)

    def fliplr(self):
        self.apply_tree(self.apply_fliplr)


def iter_game(sgf):
    goban = gotools.Goban( sgf )
    c = sgf.cursor()
    goban.perform( c.node )
    while len(c.children) > 0:
        c.next( 0 )
        goban.perform( c.node )
        yield goban

def apply_alignment(size, sgf, ops):
    nsgf = sgf # Should copy sgf
    for op in ops:
        if op == 'rot90':
            Transform(nsgf, size).rot90()
        elif op == 'fliplr':
            Transform(nsgf, size).fliplr()
    return nsgf

def align_by_pattern( pattern, sgf ):
    for state in iter_game(sgf):
        if pattern == state:
            ops = pattern.align( state )
            nsgf = apply_alignment(state.SZ, sgf, ops)
            return nsgf, (state, ops)
    raise Exception ("No matching state found")

def align_by_quadrant( sgf ):
    raise NotImplementedError()

if __name__=='__main__':
    parser = optparse.OptionParser("%prog [options] <sgf file>", 
                                   epilog="Default behavior: Align the first move to the top right, white moves to left")

    parser.add_option('-p', '--pattern', dest='pattern_file', 
                      help="Specify a pattern file for alignments")
    parser.add_option('-a', '--area', dest='pattern_area', default='aass',
                      help="Specify an area of the pattern file to match on")

    options, args = parser.parse_args()
    sgf = gotools.import_sgf(args[0])

    if options.pattern_file:
        pattern_sgf = gotools.import_sgf( options.pattern_file )
        pattern_area = options.pattern_area

        p_goban = gotools.Goban( pattern_sgf )
        p_goban.perform( pattern_sgf.cursor().node )
        pattern = gotools.Pattern( p_goban.boardstate, pattern_area )
        nsgf, _ = align_by_pattern( pattern, sgf )
        print nsgf
    else:
        nsgf = align_by_quadrant( sgf )
        print nsgf
