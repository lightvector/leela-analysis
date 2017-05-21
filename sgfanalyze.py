#!/usr/bin/python
import os, sys
import optparse
import hashlib
import pickle
import traceback
from sgftools import gotools, leela, annotations, progressbar, sgflib

RESTART_COUNT=1

def graph_winrates(winrates, color, outp_fn):
    import matplotlib as mpl
    mpl.use('Agg')
    import matplotlib.pyplot as plt

    X = []
    Y = []
    for move_num in sorted(winrates.keys()):
        pl, wr = winrates[move_num]

        if pl != color:
            wr = 1. - wr
        X.append(move_num)
        Y.append(wr)

    plt.figure(1)
    plt.axhline(0.5, 0, max(winrates.keys()), linestyle='--', color='0.7')
    plt.plot(X, Y, color='k', marker='+')
    plt.xlim(0, max(winrates.keys()))
    plt.ylim(0, 1)
    plt.xlabel("Move Number", fontsize=28)
    plt.ylabel("Win Rate", fontsize=28)
    plt.savefig(outp_fn, dpi=200, format='pdf', bbox_inches='tight')

def retry_analysis(fn):
    global RESTART_COUNT
    def wrapped(*args, **kwargs):
        for i in xrange(RESTART_COUNT+1):
            try:
                return fn(*args, **kwargs)
            except Exception, e:
                if i+1 == RESTART_COUNT+1:
                    raise
                print >>sys.stderr, "Error in leela, retrying analysis..."
    return wrapped

@retry_analysis
def do_analyze(leela, verbosity):
    ckpt_hash = 'analyze_' + leela.history_hash()
    ckpt_fn = os.path.join(base_dir, ckpt_hash)
    if verbosity > 2:
        print >>sys.stderr, "Looking for checkpoint file:", ckpt_fn

    if os.path.exists(ckpt_fn):
        if verbosity > 1:
            print >>sys.stderr, "Loading checkpoint file:", ckpt_fn
        with open(ckpt_fn, 'r') as ckpt_file:
            stats, move_list = pickle.load(ckpt_file)
    else:
        leela.reset()
        leela.goto_position()
        stats, move_list = leela.analyze()
        with open(ckpt_fn, 'w') as ckpt_file:
            pickle.dump((stats, move_list), ckpt_file)

    return stats, move_list

# move_list is from a call to do_analyze
# Iteratively expands a tree of moves by expanding on the leaf with the highest "probability of reaching".
def do_variations(C, leela, stats, move_list, nodes_per_variation, board_size, game_move, verbosity):
    if 'bookmoves' in stats or len(move_list) <= 0:
        return

    rootcolor = leela.whoseturn()
    leaves = []
    tree = { "children": [], "is_root": True, "history": [], "explored": False, "prob": 1.0, "stats": stats, "move_list": move_list, "color": rootcolor }

    def expand(node, stats, move_list):
        assert node["color"] in ['white', 'black']
        def child_prob_raw(i,move):
            if node["color"] == rootcolor:
                return move["visits"] ** 1.0
            else:
                return (move["policy_prob"] + move["visits"]) / 2.0
        probsum = 0.0
        for (i,move) in enumerate(move_list):
            probsum += child_prob_raw(i,move)
        def child_prob(i,move):
            return child_prob_raw(i,move) / probsum

        for (i,move) in enumerate(move_list):
            #Don't expand on the actual game line as a variation!
            if node["is_root"] and move == game_move:
                node["children"].append(None)
                continue
            subhistory = node["history"][:]
            subhistory.append(move["pos"])
            prob = node["prob"] * child_prob(i,move)
            clr = "white" if node["color"] == "black" else "black"
            child = { "children": [], "is_root": False, "history": subhistory, "explored": False, "prob": prob, "stats": {}, "move_list": [], "color": clr }
            node["children"].append(child)
            leaves.append(child)

        node["stats"] = stats
        node["move_list"] = move_list
        node["explored"] = True

        for i in range(len(leaves)):
            if leaves[i] is node:
                del leaves[i]
                break

    def search(node):
        for mv in node["history"]:
            leela.add_move(leela.whoseturn(),mv)
        stats, move_list = do_analyze(leela,verbosity)
        expand(node,stats,move_list)

        for mv in node["history"]:
            leela.pop_move()

    expand(tree,stats,move_list)
    for i in range(nodes_per_variation):
        if len(leaves) > 0:
            node = max(leaves,key=(lambda n: n["prob"]))
            search(node)

    def advance(C, color, mv):
        foundChildIdx = None
        clr = 'W' if color =='white' else 'B'
        for j in range(len(C.children)):
            if clr in C.children[j].keys() and C.children[j][clr].data[0] == mv:
                foundChildIdx = j
        if foundChildIdx is not None:
            C.next(foundChildIdx)
        else:
            nnode = sgflib.Node()
            nnode.addProperty(nnode.makeProperty(clr,[mv]))
            C.appendNode(nnode)
            C.next(len(C.children)-1)

    def record(node):
        if not node["is_root"]:
            annotations.annotate_sgf(C, annotations.format_winrate(node["stats"],node["move_list"],board_size), [], [])
            move_list_to_display = []
            # Only display info for the principal variation or for lines that have been explored.
            for i in range(len(node["children"])):
                child = node["children"][i]
                if i == 0 or (child is not None and child["explored"]):
                    move_list_to_display.append(node["move_list"][i])
            (analysis_comment, lb_values, tr_values) = annotations.format_analysis(node["stats"],move_list_to_display,None)
            annotations.annotate_sgf(C, analysis_comment, lb_values, tr_values)

        for i in range(len(node["children"])):
            child = node["children"][i]
            if child is not None:
                if child["explored"]:
                    advance(C, node["color"], child["history"][-1])
                    record(child)
                    C.previous()
                # Only show variations for the principal line, to prevent info overload
                elif i == 0:
                    pv = node["move_list"][i]["pv"]
                    c = node["color"]
                    num_to_show = min(len(pv), max(1, len(pv) * 2 / 3 - 1))
                    for k in range(num_to_show):
                        advance(C, c, pv[k])
                        c = 'black' if c =='white' else 'white'
                    for k in range(num_to_show):
                        C.previous()

    record(tree)


def calculate_tasks_left(sgf, start_m, end_n):
    C = sgf.cursor()
    move_num = 0
    analyze_tasks = 0
    variations_tasks = 0
    while not C.atEnd:
        C.next()

        analysis_mode = None
        if move_num >= options.analyze_start and move_num <= options.analyze_end:
            analysis_mode='analyze'

        if 'C' in C.node.keys():
            if 'variations' in C.node['C'].data[0]:
                analysis_mode='variations'
            elif 'analyze' in C.node['C'].data[0]:
                analysis_mode='analyze'

        if analysis_mode=='analyze':
            analyze_tasks += 1
        elif analysis_mode=='variations':
            analyze_tasks += 1
            variations_tasks += 1

        move_num += 1
    return (analyze_tasks,variations_tasks)

if __name__=='__main__':
    parser = optparse.OptionParser()
    parser.add_option('-m', '--starting-at-m', dest='analyze_start', default=0, type=int,
                      help="Analyze game starting at move M (default=0)", metavar="M")
    parser.add_option('-n', '--ending-at-n', dest='analyze_end', default=1000, type=int,
                      help="Analyze game ending at move N (default=1000)", metavar="N")

    parser.add_option('', '--analyze-threshold', dest='delta_sensitivity', default=0.02, type=float,
                      help="Display analysis on moves losing at least this much win rate (default=0.02)")
    parser.add_option('', '--variations-threshold', dest='delta_sensitivity2', default=0.05, type=float,
                      help="Explore variations on moves losing at least this much win rate (default=0.05)")

    parser.add_option('', '--seconds-per-search', dest='seconds_per_search', default=10, type=float,
                      help="How many seconds to use per search (default=10)")
    parser.add_option('', '--nodes-per-variation', dest='nodes_per_variation', default=6, type=int,
                      help="How many searches to use exploring each variation tree (default=6)")

    parser.add_option('-g', '--win-graph', dest='win_graph',
                      help="Graph the win rate of the selected player (Requires a move range with -m and -n)")

    parser.add_option('-v', '--verbosity', default=0, type=int,
                      help="Set the verbosity level, 0: progress only, 1: progress+status, 2: progress+status+state")
    parser.add_option('-x', '--executable', default='leela_090_macOS_opencl',
                      help="Set the default executable name for the leela command line engine")
    parser.add_option('-c', '--checkpoint-directory', dest='ckpt_dir',
                      default=os.path.expanduser('~/.leela_checkpoints'),
                      help="Set a directory to store partially complete analyses")
    parser.add_option('-r', '--restarts', default=2, type=int,
                      help="If leela crashes, retry the analysis step this many times before reporting a failure")

    options, args = parser.parse_args()
    sgf_fn = args[0]
    if not os.path.exists(sgf_fn):
        parser.error("No such file: %s" % (sgf_fn))
    sgf = gotools.import_sgf(sgf_fn)

    RESTART_COUNT = options.restarts

    if not os.path.exists( options.ckpt_dir ):
        os.mkdir( options.ckpt_dir )
    base_hash = hashlib.md5( os.path.abspath(sgf_fn) ).hexdigest()
    base_dir = os.path.join(options.ckpt_dir, base_hash)
    if not os.path.exists( base_dir ):
        os.mkdir( base_dir )
    if options.verbosity > 1:
        print >>sys.stderr, "Checkpoint dir:", base_dir

    comment_requests_analyze = {}
    comment_requests_variations = {}

    C = sgf.cursor()
    if 'SZ' in C.node.keys():
        board_size = int(C.node['SZ'].data[0])
    else:
        board_size = 19

    move_num = -1
    C = sgf.cursor()
    while not C.atEnd:
        C.next()
        move_num += 1
        if 'C' in C.node.keys():
            if 'analyze' in C.node['C'].data[0]:
                comment_requests_analyze[move_num] = True
            if 'variations' in C.node['C'].data[0]:
                comment_requests_variations[move_num] = True

    #Clean out existing comments
    C = sgf.cursor()
    cnode = C.node
    if cnode.has_key('C'):
        cnode['C'].data[0] = ""
    while not C.atEnd:
        C.next()
        cnode = C.node
        if cnode.has_key('C'):
            cnode['C'].data[0] = ""

    (analyze_tasks_initial,variations_tasks_initial) = calculate_tasks_left(sgf, options.analyze_start, options.analyze_end)
    variations_task_probability = 1.0 / (1.0 + options.delta_sensitivity2 * 50.0)
    analyze_tasks_initial_done = 0
    variations_tasks = 0
    variations_tasks_done = 0
    def approx_tasks_done():
        return (
            analyze_tasks_initial_done +
            (variations_tasks_done  * options.nodes_per_variation)
        )
    def approx_tasks_max():
        return (
            (analyze_tasks_initial - analyze_tasks_initial_done) *
            (1 + variations_task_probability * options.nodes_per_variation) +
            analyze_tasks_initial_done +
            (variations_tasks * options.nodes_per_variation)
        )

    print >>sys.stderr, "Executing approx %.0f analysis steps" % (approx_tasks_max())

    pb = progressbar.ProgressBar(max_value=approx_tasks_max())
    pb.start()
    def refresh_pb():
        pb.update_max(approx_tasks_max())
        pb.update(approx_tasks_done())

    leela = leela.CLI(board_size=board_size,
                      executable=options.executable,
                      seconds_per_search=options.seconds_per_search,
                      verbosity=options.verbosity)

    collected_winrates = {}
    collected_best_moves = {}
    collected_best_move_winrates = {}
    needs_variations = {}

    try:
        move_num = -1
        C = sgf.cursor()
        prev_stats = {}
        prev_move_list = []

        leela.start()
        while not C.atEnd:
            C.next()
            move_num += 1

            this_move = ""
            if 'W' in C.node.keys():
                this_move = C.node['W'].data[0]
                leela.add_move('white', this_move)
            if 'B' in C.node.keys():
                this_move = C.node['B'].data[0]
                leela.add_move('black', this_move)

            current_player = leela.whoseturn()
            if ((move_num >= options.analyze_start and move_num <= options.analyze_end) or
                (move_num in comment_requests_analyze) or
                (move_num in comment_requests_variations)):
                stats, move_list = do_analyze(leela,options.verbosity)

                if 'winrate' in stats and stats['visits'] > 100:
                    collected_winrates[move_num] = (current_player, stats['winrate'])
                if len(move_list) > 0 and 'winrate' in move_list[0]:
                    collected_best_moves[move_num] = move_list[0]['pos']
                    collected_best_move_winrates[move_num] = move_list[0]['winrate']

                delta = 0.0
                if (move_num-1) in collected_best_moves:
                    if(this_move != collected_best_moves[move_num-1]):
                       delta = stats['winrate'] - collected_best_move_winrates[move_num-1]
                       delta = min(0.0, (-delta if leela.whoseturn() == "black" else delta))

                if delta <= -options.delta_sensitivity:
                    (delta_comment,delta_lb_values) = annotations.format_delta_info(delta,stats,this_move)
                    annotations.annotate_sgf(C, delta_comment, delta_lb_values, [])

                if delta <= -options.delta_sensitivity2 or move_num in comment_requests_variations:
                   needs_variations[move_num-1] = (prev_stats,prev_move_list)
                   if move_num not in comment_requests_variations:
                       variations_tasks += 1

                annotations.annotate_sgf(C, annotations.format_winrate(stats,move_list,board_size), [], [])

                if (move_num-1) in comment_requests_analyze or delta <= -options.delta_sensitivity:
                    (analysis_comment, lb_values, tr_values) = annotations.format_analysis(prev_stats, prev_move_list, this_move)
                    C.previous()
                    annotations.annotate_sgf(C, analysis_comment, lb_values, tr_values)
                    C.next()

                prev_stats = stats
                prev_move_list = move_list

                analyze_tasks_initial_done += 1
                refresh_pb()

        leela.stop()
        leela.clear_history()

        # Now fill in variations for everything we need
        move_num = -1
        C = sgf.cursor()
        leela.start()
        while not C.atEnd:
            C.next()
            move_num += 1
            if 'W' in C.node.keys():
                this_move = C.node['W'].data[0]
                leela.add_move('white', this_move)
            if 'B' in C.node.keys():
                this_move = C.node['B'].data[0]
                leela.add_move('black', this_move)

            if move_num not in needs_variations:
                continue
            stats,move_list = needs_variations[move_num]
            next_game_move = None
            if not C.atEnd:
                C.next()
                if 'W' in C.node.keys():
                    next_game_move = C.node['W'].data[0]
                if 'B' in C.node.keys():
                    next_game_move = C.node['B'].data[0]
                C.previous()

            do_variations(C, leela, stats, move_list, options.nodes_per_variation, board_size, next_game_move, options.verbosity)
            variations_tasks_done += 1

    except:
        traceback.print_exc()
        print >>sys.stderr, "Failure, reporting partial results...\n"
    finally:
        leela.stop()

    if options.win_graph:
        graph_winrates(collected_winrates, "black", options.win_graph)

    pb.finish()
    print sgf
