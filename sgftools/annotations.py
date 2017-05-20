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

    if 'bookmoves' in stats:
        comment = "Considered %d/%d bookmoves\n" % (stats['bookmoves'], stats['positions'])
        comment += "Stats for %s to play\n" % (color)
        comment += "====================\n"

        sorted_moves = sorted(move_list.keys(), key=lambda k: move_list[k]['visits'], reverse=True)
        comment += "Chosen move:    %s\n" % ( abet[sorted_moves.index( stats['chosen'] )] )

        for L, mv in zip(abet, sorted_moves):
            vtext = "Visits: %d" % (move_list[mv]['visits'])
            comment += "%s -> %20s  WinRate: %.4f\n" % (L, vtext, move_list[mv]['W'])

    else:
        comment = "Visited %d nodes\n\n" % (stats['visits'])
        comment += "Stats for %s to play\n" % (color)
        comment += "====================\n"
    #    comment += "MC Winrate:   %.4f\n" % (stats['mc_winrate'])
    #    comment += "Value Net:    %.4f\n" % (stats['nn_winrate'])
    #    comment += "Game Result:  %s\n" % (stats['margin'])

        sorted_moves = sorted(move_list.keys(), key=lambda k: move_list[k]['visits'], reverse=True)
        comment += "Best winrate: %.4f\n" % (stats['winrate'])
        comment += "Best move:    %s\n" % ( abet[sorted_moves.index(stats['best'])] )

        for L, mv in zip(abet, sorted_moves):
            vtext = "Visits: %d" % (move_list[mv]['visits'])
            comment += "%s -> %20s  WinRate: %.4f\n" % (L, vtext, move_list[mv]['W'])

    if cnode.has_key('C'):
        cnode['C'].data[0] = comment
    else:
        cnode.addProperty( cnode.makeProperty( 'C', [comment] ) )

    LB_values = ["%s:%s" % (mv,L) for L, mv in zip(abet, sorted_moves)]
    if len(LB_values) > 0:
        cnode.addProperty( cnode.makeProperty( 'LB', LB_values ) )
