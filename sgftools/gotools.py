import sys
import sgflib
#import numpy as np

class Pattern(object):
    def __init__( self, boardstate, area=None ):
        mapping = {None: 0, 'b': 1, 'w': 2}
        self.seedstate = np.array([[mapping[item] for item in col] for col in boardstate])
        self.SZ = self.seedstate.shape[0]

        if area is None:
            self.seedarea = np.ones(self.seedstate.shape)
        else:
            x1,y1 = self.get_coords(area[0:2])
            x2,y2 = self.get_coords(area[2:4])

            self.seedarea = \
                np.array( [[1 if (x1 <= j <= x2) and (y1 <= i <= y2) else 0 \
                            for i in xrange(self.SZ)] \
                            for j in xrange(self.SZ)] )

        self._states = [self.seedstate,
                          np.rot90( self.seedstate, 1),
                          np.rot90( self.seedstate, 2),
                          np.rot90( self.seedstate, 3),
                          np.flipud( self.seedstate ),
                          np.flipud( np.rot90( self.seedstate, 1 ) ),
                          np.flipud( np.rot90( self.seedstate, 2 ) ),
                          np.flipud( np.rot90( self.seedstate, 3 ) )]
        self._areas = [self.seedarea,
                          np.rot90( self.seedarea, 1),
                          np.rot90( self.seedarea, 2),
                          np.rot90( self.seedarea, 3),
                          np.flipud( self.seedarea ),
                          np.flipud( np.rot90( self.seedarea, 1 ) ),
                          np.flipud( np.rot90( self.seedarea, 2 ) ),
                          np.flipud( np.rot90( self.seedarea, 3 ) )]

    def assert_matches_seed_state(self, goban):
        if self.SZ != goban.SZ:
            raise Exception("Incompatible pattern sizes: %d != %d" (self.SZ, goban.SZ))

        S, A = self.seedstate, self.seedarea
        S2 = goban.pattern()
        sel_area = np.logical_not( A == 1 )
        match = S == S2

        if not np.all(np.logical_or( match, sel_area )):
            raise AssertionError("Seed state not matched:\n" + str(self) + "\n" + str(goban))

    def get_coords( self, pos ):
        x = ord(pos[0])-97
        y = ord(pos[1])-97

        return x,y

    def print_pattern(self, states, area):
        state_map = {0: ".", 1: "b", 2: "w"}
        p_rep = "+" + "-" * (2*self.SZ+1) + "+\n"
        for j in xrange(0, self.SZ):
            p_rep += "|"
            for i in xrange(0, self.SZ):
                state = states[i, j]
                use = area[i, j]
                p_rep += " " + (state_map[state] if use == 1 else "*")
            p_rep += " |\n"
        p_rep += "+" + "-" * (2*self.SZ+1) + "+"
        return p_rep

    def __str__(self):
        return self.print_pattern( self.seedstate, self.seedarea )

    def __repr__(self):
        return self.print_pattern( self.seedstate, self.seedarea )
#        p_rep = ""
#        for state, area in zip(self._states, self._areas):
#            p_rep += self.print_pattern( state, area ) + "\n"
#        return p_rep

    def __eq__(self, goban):
        if self.SZ != goban.SZ:
            raise Exception("Incompatible pattern sizes: %d != %d" (self.SZ, goban.SZ))

        S2 = goban.pattern()
        for S, A in zip(self._states, self._areas):
            sel_area = np.logical_not( A == 1 )
            match = S == S2

            if np.all(np.logical_or( match, sel_area )):
                return True
        return False

    def align(self, goban):
        if self.SZ != goban.SZ:
            raise Exception("Incompatible pattern sizes: %d != %d" (self.SZ, goban.SZ))

        S2 = goban.pattern()
        for i, S1, A1 in zip(range(8), self._states, self._areas):
            sel_area = np.logical_not( A1 == 1 )
            match = S1 == S2

            if np.all(np.logical_or( match, sel_area )):
                alignment = i
#                print >>sys.stderr, alignment
#                print >>sys.stderr, self.print_pattern(S1, A1)
#                print >>sys.stderr, goban
                break

        if alignment < 4:
            return ['rot90'] * alignment
        else:
            return ['fliplr'] + ['rot90'] * (alignment-4)

class Goban(object):
    def __init__( self, sgf ):
        self.sgf = sgf
        self.init_board_state()

    def init_board_state( self ):
        c = self.sgf.cursor()

        self.SZ = 19

        for k in c.node.keys():
            v = c.node[k]
            if v.name == 'SZ':
                self.SZ = int( v[0] )

        self.boardstate = [ ]
        for i in xrange(0, self.SZ):
            self.boardstate.append( list() )
            for j in xrange(0, self.SZ):
                self.boardstate[i].append( None )

    def area_occupied(self, x1, y1, x2, y2):
        return any([self.boardstate[i][j] is not None \
                    for i in xrange(x1, x2) \
                    for j in xrange(y1, y2)])

    def pattern( self ):
        mapping = {None: 0, 'b': 1, 'w': 2}
        return np.array([[mapping[item] for item in col] for col in self.boardstate])

    def __repr__(self):
        state_map = {None: ".", 'b': "b", 'w': "w"}
        p_rep = "+" + "-" * (2*self.SZ+1) + "+\n"
        for j in xrange(0, self.SZ):
            p_rep += "|"
            for i in xrange(0, self.SZ):
                state = self.boardstate[i][j]
                p_rep += " " + (state_map[state])
            p_rep += " |\n"
        p_rep += "+" + "-" * (2*self.SZ+1) + "+"
        return p_rep

    def copy( self ):
        g = Goban( self.sgf )
        for i in xrange(0, self.SZ):
            for j in xrange(0, self.SZ):
                g.boardstate[i][j] = self.boardstate[i][j]
        return g

    def __str__( self ):
        return self.__repr__()

    def node_has_move( self, node ):
        for k in node.keys():
            v = node[k]
            if v.name in ['W','B']:
                return True
        return False

    def perform( self, node ):

        move = None
        color = None
        for k in node.keys():
            v = node[k]

            if v.name == 'AB':
                for p in v:
                    x,y = self.get_coords( p )
                    self.boardstate[x][y] = 'b'

            if v.name == 'AW':
                for p in v:
                    x,y = self.get_coords( p )
                    self.boardstate[x][y] = 'w'

            if v.name == 'B':
                if not is_pass( v[0] ) and not is_tenuki( v[0] ):
                    x,y = self.get_coords( v[0] )
                    self.boardstate[x][y] = 'b'
                    move = x,y
                    color = 'b'
                else:
                    move = None
                    color = 'b'

            if v.name == 'W':
                if not is_pass( v[0] ) and not is_tenuki( v[0] ):
                    x,y = self.get_coords( v[0] )
                    self.boardstate[x][y] = 'w'
                    move = x,y
                    color = 'w'
                else:
                    move = None
                    color = 'w'

        killed = 0
        if move is not None:
            killed = self.process_dead_stones( move, color )

        return killed

    def get_adjacent( self, x, y ):
        positions = []
        if x > 0:
            positions.append( (x-1, y) )
        if x+1 < self.SZ:
            positions.append( (x+1, y) )
        if y > 0:
            positions.append( (x, y-1) )
        if y+1 < self.SZ:
            positions.append( (x, y+1) )

        return positions


    def process_dead_stones( self, lastMove, color ):
        x, y = lastMove
        killed = 0
        opposing = 'w'
        if opposing == color:
            opposing = 'b'

        for pos in self.get_adjacent( x, y ):
            grp, c = self.get_group( pos )

            if c == opposing and self.get_liberties( grp ) == 0:
                self.kill_group( grp )
                killed += len( grp )

        return killed

    def get_liberties( self, grp ):
        liberties = 0
        for x, y, c in grp:
            for pos in self.get_adjacent( x, y ):
                i, j = pos
                if self.boardstate[i][j] == None:
                    liberties+=1
        return liberties

    def kill_group( self, grp ):
        for x, y, c in grp:
            self.boardstate[x][y] = None


    def get_group( self, pos, g=None, color=None, visited=None ):
        x, y = pos
        if color == None:
            color = self.boardstate[x][y]
        if visited == None:
            visited = set()
        if g == None:
            g = list()

        if color is None:
            return [], None

        visited.add( pos )
        g.append((x, y, color))

        for adj in self.get_adjacent( x, y ):
            if adj not in visited and self.boardstate[adj[0]][adj[1]] == color:
                self.get_group( adj, g, color, visited )

        return g, color


    def get_coords( self, pos ):
        x = ord(pos[0])-97
        y = ord(pos[1])-97

        if x < 0 or x >= self.SZ or y < 0 or y >= self.SZ:
            raise ValueError("Invalid board coordinate: ('%s': %d, %d)" % (pos, x, y))

        return x, y


def split_continuations( sgf ):
    c = sgf.cursor()
    goban = Goban( sgf )
    navigate_splits( c, goban )

def navigate_splits( c, goban ):
    k = goban.perform( c.node )
    pos, color = get_capture_move( c )

    if k > 0:
        player = "Black"
        if color == 'w': player = "White"

        n = sgflib.Node([ sgflib.Property( 'LB', ['%s:A' % ( pos )] ),
                          sgflib.Property( 'C', ['%s captures at A, see variation for continuation' % ( player )] ) ])
        c.pushNode( n )

    i = 0
    while i < len( c.children ):
        c.next( i )
        navigate_splits( c, goban.copy() )
        c.previous()
        i += 1

def get_capture_move( c ):
    pos, color = None, None
    for k in c.node.keys():
        v = c.node[k]
        if v.name == 'B':
            pos = v[0]
            color = 'b'
        if v.name == 'W':
            pos = v[0]
            color = 'w'

    return pos, color

def add_numberings( sgf ):
    c = sgf.cursor()
    number_endpoints( c, {} )

def is_pass( p ):
    return p == '' or p == '``'

def is_tenuki( p ):
    return p == 'tt'

def clean_sgf( sgf ):
    c = sgf.cursor()
    clean_node( c )

def clean_node( cursor ):
    pass_repl = ""
    for k in cursor.node.keys():
        v = cursor.node[k]
        if v.name == 'B':
            p = v[0]
            if is_pass(p):
                pass_repl = 'B'
        if v.name == 'W':
            p = v[0]
            if is_pass(p):
                pass_repl = 'W'

    if pass_repl != "":
        p = get_property( cursor.node, pass_repl )
        p[0] = ''

    for i in xrange(0, len( cursor.children )):
        cursor.next( i )
        clean_node( cursor )
        cursor.previous()

def number_endpoints( cursor, moves, num=1 ):
    hasMove = False
    for k in cursor.node.keys():
        v = cursor.node[k]
        if v.name == 'B':
            p = v[0]
            if not is_pass(p):
                moves[p] = num
            hasMove = True
        if v.name == 'W':
            p = v[0]
            if not is_pass(p):
                moves[p] = num
            hasMove = True

    for i in xrange(0, len( cursor.children )):
        cursor.next( i )
        number_endpoints( cursor, moves.copy(), num+1 if hasMove else num )
        cursor.previous()

    if len( cursor.children ) == 0:
        for pos in moves:
            add_label( cursor.node, pos, moves[pos] )

def get_property( node, tag ):
    for prop in node:
        if prop.name == tag:
            return prop

def add_or_extend_property( node, tag, vals ):
    prop = get_property(node, tag)
    if prop != None:
        for v in vals:
            prop.append( v )
    else:
        prop = sgflib.Property(tag, vals)
        node.addProperty( prop )

def add_label( node, pos, lbl, overwrite=False ):
    prop = get_property( node, 'LB' )

    lbl_template = "%s:%s" % (pos, str( lbl ))

    if prop == None:
        prop = sgflib.Property( 'LB', [ lbl_template ])
        node.addProperty( prop )
    else:
        remove = []
        exists = False
        for i in xrange(0, len(prop)):
            v = prop[i]
            if v[:2] == pos and overwrite:
                prop[i] = lbl_template
                exists = True
            elif v[:2] == pos:
                exists = True
#                print "Not overwriting: " + v + " with: " + lbl_template

        if not exists:
            prop.append( lbl_template )

def get_crop( sgf ):
    positions = []

    positions += collect_positions( sgf.cursor() )

    x = []
    y = []
    for pos in positions:
        pos = pos.lower().strip()
        if pos == '``' or pos == '':
            continue
        x.append( ord( pos[0] ) - 96 )
        y.append( ord( pos[1] ) - 96 )

    minx, maxx = process_limits(x)
    miny, maxy = process_limits(y)

    return minx + miny + maxx + maxy


def process_limits(x):
    if min(x) <= 10 and max(x) <= 10:
        minx = 'a'
        maxx = 'j'
    elif min(x) >= 10 and max(x) >= 10:
        minx = 'j'
        maxx = 's'
    elif min(x) >= 4 and max(x) <= 16:
        minx = 'd'
        maxx = 'p'
    else:
        minx = 'a'
        maxx = 's'
    return minx, maxx


def collect_positions( cursor ):
    positions = []

    for k in cursor.node.keys():
        v = cursor.node[k]

        if v.name in ['AB', 'W', 'B', 'AW', 'SQ', 'TR', 'CR']:
            positions += [ p for p in v ]
        if v.name in ['LB']:
            positions += [ p.split(":")[0] for p in v ]

    for i in xrange(0, len( cursor.children )):
        cursor.next( i )
        positions += collect_positions( cursor )
        cursor.previous()

    return positions


def import_sgf( filename ):
    data = ""
    with open(filename, 'r') as ifile:
        for line in ifile:
            data += line

    parser = sgflib.SGFParser( data )
    return parser.parse()
