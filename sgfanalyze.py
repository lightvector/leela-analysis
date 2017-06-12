#!/usr/bin/env python2
import os, sys
import argparse
import hashlib
import pickle
import traceback
import math
from sgftools import gotools, leela, annotations, progressbar, sgflib

# Stdev of bell curve whose cdf we take to be the "real" probability given Leela's winrate
DEFAULT_STDEV = 0.22

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

#Also returns the move played, if any, else None
def add_moves_to_leela(C,leela):
    this_move = None
    if 'W' in C.node.keys():
        this_move = C.node['W'].data[0]
        leela.add_move('white', this_move)
    if 'B' in C.node.keys():
        this_move = C.node['B'].data[0]
        leela.add_move('black', this_move)
    # SGF commands to add black or white stones, often used for setting up handicap and such
    if 'AB' in C.node.keys():
        for move in C.node['AB'].data:
            leela.add_move('black', move)
    if 'AW' in C.node.keys():
        for move in C.node['AW'].data:
            leela.add_move('white', move)
    return this_move

# Make a function that applies a transform to the winrate that stretches out the middle range and squashes the extreme ranges,
# to make it a more linear function and suppress Leela's suggestions in won/lost games.
# Currently, the CDF of the probability distribution from 0 to 1 given by x^k * (1-x)^k, where k is set to be the value such that
# the stdev of the distribution is stdev.
def winrate_transformer(stdev, verbosity):
  def logfactorial(x):
    return math.lgamma(x+1)
  # Variance of the distribution =
  # = The integral from 0 to 1 of (x-0.5)^2 x^k (1-x)^k dx
  # = (via integration by parts)  (k+2)!k! / (2k+3)! - (k+1)!k! / (2k+2)! + (1/4) * k!^2 / (2k+1)!
  #
  # Normalize probability by dividing by the integral from 0 to 1 of x^k (1-x)^k dx :
  # k!^2 / (2k+1)!
  # And we get:
  # (k+1)(k+2) / (2k+2) / (2k+3) - (k+1) / (2k+2) + (1/4)
  def variance(k):
    k = float(k)
    return (k+1) * (k+2) / (2*k+2) / (2*k+3) - (k+1) / (2*k+2) + 0.25
  # Perform binary search to find the appropriate k
  def find_k(lower,upper):
    while True:
      mid = 0.5 * (lower + upper)
      if mid == lower or mid == upper or lower >= upper:
        return mid
      var = variance(mid)
      if var < stdev * stdev:
        upper = mid
      else:
        lower = mid

  if stdev * stdev <= 1e-10:
    raise ValueError("Stdev too small, please choose a more reasonable value")

  # Repeated doubling to find an upper bound big enough
  upper = 1
  while variance(upper) > stdev * stdev:
    upper = upper * 2

  k = find_k(0,upper)

  if verbosity > 2:
      print >>sys.stderr, "Using k=%f, stdev=%f" % (k,math.sqrt(variance(k)))

  def unnormpdf(x):
    if x <= 0 or x >= 1 or 1-x <= 0:
      return 0
    a = math.log(x)
    b = math.log(1-x)
    logprob = a * k + b * k
    # Constant scaling so we don't overflow floats with crazy values
    logprob = logprob - 2 * k * math.log(0.5)
    return math.exp(logprob)

  #Precompute a big array to approximate the CDF
  n = 100000
  lookup = [ unnormpdf(float(x)/float(n)) for x in range(n+1) ]
  cum = 0
  for i in range(n+1):
    cum += lookup[i]
    lookup[i] = cum
  for i in range(n+1):
    lookup[i] = lookup[i] / lookup[n]

  def cdf(x):
    i = int(math.floor(x * n))
    if i >= n or i < 0:
      return x
    excess = x * n - i
    return lookup[i] + excess * (lookup[i+1] - lookup[i])

  return (lambda x: cdf(x))


def retry_analysis(fn):
    global RESTART_COUNT
    def wrapped(*args, **kwargs):
        for i in xrange(RESTART_COUNT+1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if i+1 == RESTART_COUNT+1:
                    raise
                print >>sys.stderr, "Error in leela, retrying analysis..."
    return wrapped

@retry_analysis
def do_analyze(leela, base_dir, verbosity):
    ckpt_hash = 'analyze_' + leela.history_hash() + "_" + str(leela.seconds_per_search) + "sec"
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
def do_variations(C, leela, stats, move_list, nodes_per_variation, board_size, game_move, base_dir, verbosity):
    if 'bookmoves' in stats or len(move_list) <= 0:
        return

    rootcolor = leela.whoseturn()
    leaves = []
    tree = { "children": [], "is_root": True, "history": [], "explored": False, "prob": 1.0, "stats": stats, "move_list": move_list, "color": rootcolor }

    def expand(node, stats, move_list):
        assert node["color"] in ['white', 'black']
        def child_prob_raw(i,move):
            # possible for book moves
            if "is_book" in move:
                return 1.0
            elif node["color"] == rootcolor:
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
            if node["is_root"] and move["pos"] == game_move:
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
        stats, move_list = do_analyze(leela,base_dir,verbosity)
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
                if child is not None and (i == 0 or child["explored"]):
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


def calculate_tasks_left(sgf, start_m, end_n, comment_requests_analyze, comment_requests_variations):
    C = sgf.cursor()
    move_num = 0
    analyze_tasks = 0
    variations_tasks = 0
    while not C.atEnd:
        C.next()

        analysis_mode = None
        if move_num >= args.analyze_start and move_num <= args.analyze_end:
            analysis_mode='analyze'
        if move_num in comment_requests_analyze or (move_num-1) in comment_requests_analyze or (move_num-1) in comment_requests_variations:
            analysis_mode='analyze'
        if move_num in comment_requests_variations:
            analysis_mode='variations'

        if analysis_mode=='analyze':
            analyze_tasks += 1
        elif analysis_mode=='variations':
            analyze_tasks += 1
            variations_tasks += 1

        move_num += 1
    return (analyze_tasks,variations_tasks)

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    required = parser.add_argument_group('required named arguments')
    parser.add_argument('--start', dest='analyze_start', default=0, type=int, metavar="MOVENUM",
                        help="Analyze game starting at this move (default=0)")
    parser.add_argument('--stop', dest='analyze_end', default=1000, type=int, metavar="MOVENUM",
                        help="Analyze game stopping at this move (default=1000)")

    parser.add_argument('--analyze-thresh', dest='analyze_threshold', default=0.030, type=float, metavar="T",
                        help="Display analysis on moves losing approx at least this much win rate when the game is close (default=0.03)")
    parser.add_argument('--var-thresh', dest='variations_threshold', default=0.030, type=float, metavar="T",
                        help="Explore variations on moves losing approx at least this much win rate when the game is close (default=0.03)")

    parser.add_argument('--secs-per-search', dest='seconds_per_search', default=10, type=float, metavar="S",
                        help="How many seconds to use per search (default=10)")
    parser.add_argument('--nodes-per-var', dest='nodes_per_variation', default=8, type=int, metavar="N",
                        help="How many nodes to explore with leela in each variation tree (default=8)")
    parser.add_argument('--win-graph', dest='win_graph', metavar="PDF",
                        help="Output pdf graph of win rate to this file, must have matplotlib installed")
    parser.add_argument('-v','--verbosity', default=0, type=int, metavar="V",
                        help="Set the verbosity level, 0: progress only, 1: progress+status, 2: progress+status+state")
    required.add_argument('--leela', dest='executable', required=True, metavar="CMD",
                        help="Command to run Leela executable")
    parser.add_argument('--cache', dest='ckpt_dir', metavar="DIR",
                        default=os.path.expanduser('~/.leela_checkpoints'),
                        help="Set a directory to cache partially complete analyses, default ~/.leela_checkpoints")
    parser.add_argument('--restarts', default=2, type=int, metavar="N",
                        help="If leela crashes, retry the analysis step this many times before reporting a failure")
    parser.add_argument('--wipe-comments', dest='wipe_comments', action='store_true',
                        help="Remove existing comments from the main line of the SGF file")
    parser.add_argument('--skip-white', dest='skip_white', action='store_true',
                        help="Do not display analysis or explore variations for white mistakes")
    parser.add_argument('--skip-black', dest='skip_black', action='store_true',
                        help="Do not display analysis or explore variations for black mistakes")
    parser.add_argument("SGF_FILE", help="SGF file to analyze")

    args = parser.parse_args()
    sgf_fn = args.SGF_FILE
    if not os.path.exists(sgf_fn):
        parser.error("No such file: %s" % (sgf_fn))
    sgf = gotools.import_sgf(sgf_fn)

    RESTART_COUNT = args.restarts

    if not os.path.exists( args.ckpt_dir ):
        os.mkdir( args.ckpt_dir )
    base_hash = hashlib.md5( os.path.abspath(sgf_fn) ).hexdigest()
    base_dir = os.path.join(args.ckpt_dir, base_hash)
    if not os.path.exists( base_dir ):
        os.mkdir( base_dir )
    if args.verbosity > 1:
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

    if args.wipe_comments:
        C = sgf.cursor()
        cnode = C.node
        if cnode.has_key('C'):
            cnode['C'].data[0] = ""
        while not C.atEnd:
            C.next()
            cnode = C.node
            if cnode.has_key('C'):
                cnode['C'].data[0] = ""

    C = sgf.cursor()
    is_handicap_game = False
    handicap_stone_count = 0
    if 'HA' in C.node.keys() and int(C.node['HA'].data[0]) > 1:
        is_handicap_game = True
        handicap_stone_count = int(C.node['HA'].data[0])

    is_japanese_rules = False
    if 'RU' in C.node.keys():
        rules = C.node['RU'].data[0].lower()
        is_japanese_rules = (rules == 'jp' or rules == 'japanese' or rules == 'japan')

    komi = 7.5
    if 'KM' in C.node.keys():
        komi = float(C.node['KM'].data[0])
        if is_handicap_game and is_japanese_rules:
            old_komi = komi
            komi = old_komi + handicap_stone_count
            print >>sys.stderr, "Adjusting komi from %f to %f in converting Japanese rules with %d handicap to Chinese rules" % (old_komi,komi,handicap_stone_count)

    else:
        if is_handicap_game:
            komi = 0.5
        print >>sys.stderr, "Warning: Komi not specified, assuming %f" % (komi)

    (analyze_tasks_initial,variations_tasks_initial) = calculate_tasks_left(sgf, args.analyze_start, args.analyze_end, comment_requests_analyze, comment_requests_variations)
    variations_task_probability = 1.0 / (1.0 + args.variations_threshold * 100.0)
    analyze_tasks_initial_done = 0
    variations_tasks = variations_tasks_initial
    variations_tasks_done = 0
    def approx_tasks_done():
        return (
            analyze_tasks_initial_done +
            (variations_tasks_done  * args.nodes_per_variation)
        )
    def approx_tasks_max():
        return (
            (analyze_tasks_initial - analyze_tasks_initial_done) *
            (1 + variations_task_probability * args.nodes_per_variation) +
            analyze_tasks_initial_done +
            (variations_tasks * args.nodes_per_variation)
        )

    transform_winrate = winrate_transformer(DEFAULT_STDEV, args.verbosity)
    analyze_threshold = transform_winrate(0.5 + 0.5 * args.analyze_threshold) - transform_winrate(0.5 - 0.5 * args.analyze_threshold)
    variations_threshold = transform_winrate(0.5 + 0.5 * args.variations_threshold) - transform_winrate(0.5 - 0.5 * args.variations_threshold)
    print >>sys.stderr, "Executing approx %.0f analysis steps" % (approx_tasks_max())

    pb = progressbar.ProgressBar(max_value=approx_tasks_max())
    pb.start()
    def refresh_pb():
        pb.update(approx_tasks_done(), approx_tasks_max())

    leela = leela.CLI(board_size=board_size,
                      executable=args.executable,
                      is_handicap_game=is_handicap_game,
                      komi=komi,
                      seconds_per_search=args.seconds_per_search,
                      verbosity=args.verbosity)

    collected_winrates = {}
    collected_best_moves = {}
    collected_best_move_winrates = {}
    needs_variations = {}

    try:
        move_num = -1
        C = sgf.cursor()
        prev_stats = {}
        prev_move_list = []
        has_prev = False

        leela.start()
        add_moves_to_leela(C,leela)
        while not C.atEnd:
            C.next()
            move_num += 1
            this_move = add_moves_to_leela(C,leela)
            current_player = leela.whoseturn()
            prev_player = "white" if current_player == "black" else "black"
            if ((move_num >= args.analyze_start and move_num <= args.analyze_end) or
                (move_num in comment_requests_analyze) or
                ((move_num-1) in comment_requests_analyze) or
                (move_num in comment_requests_variations) or
                ((move_num-1) in comment_requests_variations)):
                stats, move_list = do_analyze(leela,base_dir,args.verbosity)

                if 'winrate' in stats and stats['visits'] > 100:
                    collected_winrates[move_num] = (current_player, stats['winrate'])
                if len(move_list) > 0 and 'winrate' in move_list[0]:
                    collected_best_moves[move_num] = move_list[0]['pos']
                    collected_best_move_winrates[move_num] = move_list[0]['winrate']

                delta = 0.0
                transdelta = 0.0
                if 'winrate' in stats and (move_num-1) in collected_best_moves:
                    if(this_move != collected_best_moves[move_num-1]):
                       delta = stats['winrate'] - collected_best_move_winrates[move_num-1]
                       delta = min(0.0, (-delta if leela.whoseturn() == "black" else delta))
                       transdelta = transform_winrate(stats['winrate']) - transform_winrate(collected_best_move_winrates[move_num-1])
                       transdelta = min(0.0, (-transdelta if leela.whoseturn() == "black" else transdelta))

                    if transdelta <= -analyze_threshold:
                        (delta_comment,delta_lb_values) = annotations.format_delta_info(delta,transdelta,stats,this_move,board_size)
                        annotations.annotate_sgf(C, delta_comment, delta_lb_values, [])

                if has_prev and (transdelta <= -variations_threshold or (move_num-1) in comment_requests_variations):
                    if not (args.skip_white and prev_player == "white") and not (args.skip_black and prev_player == "black"):
                        needs_variations[move_num-1] = (prev_stats,prev_move_list)
                        if (move_num-1) not in comment_requests_variations:
                            variations_tasks += 1

                annotations.annotate_sgf(C, annotations.format_winrate(stats,move_list,board_size), [], [])

                if has_prev and ((move_num-1) in comment_requests_analyze or (move_num-1) in comment_requests_variations or transdelta <= -analyze_threshold):
                    if not (args.skip_white and prev_player == "white") and not (args.skip_black and prev_player == "black"):
                        (analysis_comment, lb_values, tr_values) = annotations.format_analysis(prev_stats, prev_move_list, this_move)
                        C.previous()
                        annotations.annotate_sgf(C, analysis_comment, lb_values, tr_values)
                        C.next()

                prev_stats = stats
                prev_move_list = move_list
                has_prev = True

                analyze_tasks_initial_done += 1
                refresh_pb()
            else:
                prev_stats = {}
                prev_move_list = []
                has_prev = False

        leela.stop()
        leela.clear_history()

        # Now fill in variations for everything we need
        move_num = -1
        C = sgf.cursor()
        leela.start()
        add_moves_to_leela(C,leela)
        while not C.atEnd:
            C.next()
            move_num += 1
            add_moves_to_leela(C,leela)

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

            do_variations(C, leela, stats, move_list, args.nodes_per_variation, board_size, next_game_move, base_dir, args.verbosity)
            variations_tasks_done += 1
            refresh_pb()

    except:
        traceback.print_exc()
        print >>sys.stderr, "Failure, reporting partial results...\n"
    finally:
        leela.stop()

    if args.win_graph:
        graph_winrates(collected_winrates, "black", args.win_graph)

    pb.finish()
    print sgf
