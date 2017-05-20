from sgftools import sgflib

def insert_sequence(cursor, seq, data=None, callback=None):
    if data is None:
        data = [0]*len(seq)
    for (color, mv), elem in zip(seq, data):
        nnode = sgflib.Node()
        assert color in ['white', 'black']
        color = 'W' if color =='white' else 'B'
        nnode.addProperty( nnode.makeProperty(color, [mv]) )
        cursor.appendNode( nnode )
        cursor.next( len(cursor.children) - 1 )

        if callback is not None:
            if type(elem) in [list, tuple]:
                elem = list(elem)
            else:
                elem = [elem]
            callback( *tuple([cursor] + elem) )

    for i in xrange(len(seq)):
        cursor.previous()

def format_variation(cursor, seq):
    mv_seq = [(color, mv) for color, mv, _stats, _mv_list in seq]
    mv_data = [('black' if color == 'white' else 'white', stats, mv_list) for color, _mv, stats, mv_list in seq]
    insert_sequence(cursor, mv_seq, mv_data, format_analysis)

def format_analysis(cursor, color, stats, move_list):
    cnode = cursor.node
    abet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

    comment = ""
    if 'bookmoves' in stats:
        comment += "Book move: %s\n" % (abet[0])
        comment += "====================\n"
        comment += "Considered %d/%d bookmoves\n" % (stats['bookmoves'], stats['positions'])
        comment += "====================\n"
    else:
        comment += "Overall win%%: %.2f%%\n" % (stats['winrate'] * 100)
        comment += "Best move: %s\n" % ( abet[0] )
        comment += "====================\n"
        comment += "Visited %d nodes\n" % (stats['visits'])
        comment += "====================\n"

        for L, mv in zip(abet, move_list):
            comment += "%s -> Win%%: %.2f%% (%d visits) \n" % (L, mv['winrate'] * 100, mv['visits'])

    if cnode.has_key('C'):
        cnode['C'].data[0] = comment
    else:
        cnode.addProperty( cnode.makeProperty( 'C', [comment] ) )

    LB_values = ["%s:%s" % (mv['pos'],L) for L, mv in zip(abet, move_list)]
    if len(LB_values) > 0:
        cnode.addProperty( cnode.makeProperty( 'LB', LB_values ) )
