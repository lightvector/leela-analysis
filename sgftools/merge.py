import optparse
import gotools
import sgflib
import sys

def next_move(c):
    for item in c.node:
        if item.name == 'W':
            return item.data[0]
        if item.name == 'B':
            return item.data[0]


def add_source_info(cnode, source_fn):
    if 'C' in cnode:
        c_prop = cnode['C']
        c_prop[0] += "\n" + source_fn

    cnode.addProperty(
        cnode.makeProperty( 'C', [source_fn] ) )

def merge_linear(c_source, c_dest, source_fn):
    if len(c_source.children)==0: return

    c_source.next(0)
    cnode = c_source.node.copy()
    add_source_info(cnode, source_fn)
    c_dest.appendNode(cnode)
    c_dest.next(0)

    merge_linear(c_source, c_dest, source_fn)

    c_source.previous()
    c_dest.previous()


def merge_trees(c_source, c_dest, source_fn):
    if len(c_source.children)==0: return

    c_source.next(0)
    source_move = next_move(c_source)

    found=False
    for j in xrange(len(c_dest.children)):
        c_dest.next(j)
        dest_move = next_move(c_dest)

        if source_move == dest_move:
            add_source_info(c_dest.node, source_fn)
            merge_trees(c_source, c_dest, source_fn)
            found=True
            break
        c_dest.previous()

    if not found:
        cnode = c_source.node.copy()
        add_source_info(cnode, source_fn)
        c_dest.appendNode(cnode)
        c_dest.next(len(c_dest.children)-1)

        merge_linear(c_source, c_dest, source_fn)
        c_dest.previous()

    c_source.previous()

if __name__=='__main__':
    parser = optparse.OptionParser("%prog [options] <sgf file 1> <sgf file 2> ...")
    parser.add_option('-s', '--size', dest='board_size', default=19, type='int',
                      help="Set the board size, default=19")
    options, args = parser.parse_args()

    merged_sgf = sgflib.SGFParser( "(;PB[Black]PW[White]SZ[%d]FF[4]GM[1]CA[UTF-8])" % (options.board_size) ).parse()

    for sgf_fn in args:
        print >>sys.stderr, sgf_fn
        sgf = gotools.import_sgf(sgf_fn)
        merge_trees( sgf.cursor(), merged_sgf.cursor(), sgf_fn )

    print merged_sgf
