import sys
import gotools
import traceback
import pickle

def to_bool( inp ):
    if inp.lower() == "true":
        return True
    if inp.lower() == "false":
        return False
    raise ValueError("Not a valid boolean value: %s" % (str(inp)))

def contains_any( haystack, *needles ):
    for n in needles:
        if n in haystack:
            return True
    return False

def flip_problem( problem ):
    nstones = {}
    nmarkup = {}
    for x, y in problem['stones']:
        nx = x
        ny = problem['size'] - y - 1
        nstones[(nx, ny)] = problem['stones'][(x,y)]

    for x, y in problem['markup']:
        nx = x
        ny = problem['size'] - y - 1
        nmarkup[(nx, ny)] = problem['markup'][(x,y)]

    problem['stones'] = nstones
    problem['markup'] = nmarkup

def crop_problem( problem, margins ):
    crop = [ 100, 100, -100, -100 ]

    all_positions = set([(x,y) for x,y in problem['stones']]) | \
                    set([(x,y) for x,y in problem['markup']])


    for x, y in all_positions:
        if x < 4:
            crop[0] = 0
        if x > problem['size'] - 5:
            crop[2] = problem['size']

        if y < 4:
            crop[1] = 0
        if y > problem['size'] - 5:
            crop[3] = problem['size']

        if crop[0] > x - margins:
            crop[0] = x - margins
        if crop[1] > y - margins:
            crop[1] = y - margins

        if crop[2] <= x+margins:
            crop[2] = x + 1 + margins
        if crop[3] <= y+margins:
            crop[3] = y + 1 + margins

    if crop[0] < 0:
        crop[0] = 0
    if crop[1] < 0:
        crop[1] = 0
    if crop[2] > problem['size']:
        crop[2] = problem['size']
    if crop[3] > problem['size']:
        crop[3] = problem['size']

    problem['crop'] = crop

def make_problem( c, goban, move_num, add_move_label ):
    problem = {'text':"", 'stones':{}, 'markup':{}, 'size':int(goban.SZ)}
    clabel = 0
    default_labels = "ABCDEFGHIJKLMNOP"

    x = 0
    for column in goban.boardstate:
        y = 0
        for v in column:
            if v is not None:
                problem['stones'][(x,y)] = v
            y += 1
        x += 1

    for k in c.node.keys():
        v = c.node[k]

        if (v.name == 'W' or v.name == 'B') and add_move_label:
            for pos in v:
                if gotools.is_pass( pos ) or gotools.is_tenuki( pos ):
                    continue
                x, y = goban.get_coords( pos )
                problem['markup'][(x, y)] = str(move_num)

        if v.name == 'C':
            problem['text'] = v[0]
        if v.name == 'TR':
            for pos in v:
                x,y = goban.get_coords( pos )
                problem['markup'][(x,y)] = '^'
        if v.name == 'SQ':
            for pos in v:
                x,y = goban.get_coords( pos )
                problem['markup'][(x,y)] = '#'
        if v.name == 'CR':
            for pos in v:
                x,y = goban.get_coords( pos )
                problem['markup'][(x,y)] = '0'
        if v.name == 'L':
            for pos in v:
                x,y = goban.get_coords( pos )
                problem['markup'][(x,y)] = default_labels[clabel]
                clabel+=1
        if v.name == 'LB':
            for lb in v:
                pos, label = lb.split(':')
                x,y = goban.get_coords( pos )
                problem['markup'][(x,y)] = label

    return problem


def get_problem_states( c, goban, move_num=0, add_move_label=False ):
    problems = []
    goban.perform( c.node )
    if goban.node_has_move( c.node ):
        move_num += 1

    for k in c.node.keys():
        v = c.node[k]

        if v.name == 'C':
            if contains_any(v[0], 'problem:', 'Problem:', 'problem\:', 'Problem\:'):
                problems.append( make_problem( c, goban, move_num, add_move_label ) )

    for i in xrange(0, len( c.children )):
        c.next( i )
        problems += get_problem_states( c, goban.copy(), move_num, add_move_label )
        c.previous()

    return problems

def main( args ):
    export_prefix = args[0]
    margins = int(args[1])
    flip_vertical = to_bool(args[2])
    add_last_number = to_bool(args[3])

    pnum = 1
    for sgf_fn in args[4:]:
        try:
            print >>sys.stderr, sgf_fn
            sgf = gotools.import_sgf(sgf_fn)

            goban = gotools.Goban( sgf )
            problems = get_problem_states( sgf.cursor(), goban, add_move_label=add_last_number)

            for p in problems:
                fn = "%s.%03d.pyp" % (export_prefix, pnum)

                if flip_vertical:
                    flip_problem( p )
                crop_problem( p, margins )
                p['source'] = sgf_fn

                with open(fn, 'w') as probfile:
                    pickle.dump( p, probfile )
                pnum+=1
        except Exception, e:
            sys.stderr.write("Error processing '%s'\n" % (sgf_fn))
            traceback.print_exc()

if __name__=='__main__':
    main(sys.argv[1:])
