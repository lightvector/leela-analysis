#!/usr/bin/python
import os, sys
import optparse
import hashlib
import pickle
import traceback
from sgftools import gotools, leela, annotations, progressbar

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
def do_analyze(C, leela, pb):
    leela.reset()
    leela.goto_position()
    stats, move_list = leela.analyze()
    pb.increment()
    return stats, move_list

# @retry_analysis
# def do_variations(C, leela, pb):
#     leela.reset()
#     leela.goto_position()
#     stats, move_list = leela.analyze()
#     pb.increment()

#     sorted_moves = sorted(move_list.keys(), key=lambda k: move_list[k]['visits'], reverse=True)
#     sequences = [ explore_branch(leela, mv, options.depth, pb) for mv in sorted_moves[:options.num_branches] ]

#     return stats, move_list, sequences

def explore_branch(leela, mv, depth, pb):
    seq = []

    for i in xrange(depth):
        color = leela.whoseturn()
        leela.add_move(color, mv)

        leela.reset()
        leela.goto_position()
        stats, move_list = leela.analyze()

        pb.increment()
        seq.append( (color, mv, stats, move_list) )
        mv = stats['chosen']

    for i in xrange(depth):
        leela.pop_move()

    return seq

def calculate_task_size(sgf, start_m, end_n):
    C = sgf.cursor()
    move_num=0
    steps=0
    while not C.atEnd:
        C.next()

        analysis_mode = None
        if move_num >= options.analyze_start and move_num < options.analyze_end:
            analysis_mode='analyze'

        if 'C' in C.node.keys():
            if 'variations' in C.node['C'].data[0]:
                analysis_mode='variations'
            elif 'analyze' in C.node['C'].data[0]:
                analysis_mode='analyze'

        if analysis_mode=='analyze':
            steps+=1
        elif analysis_mode=='variations':
            steps+=10

        move_num+=1
    return steps

if __name__=='__main__':
    parser = optparse.OptionParser()
    parser.add_option('-m', '--starting-at-m', dest='analyze_start', default=0, type=int,
                      help="Analyze game starting at move M (default=0)", metavar="M")
    parser.add_option('-n', '--ending-at-n', dest='analyze_end', default=1000, type=int,
                      help="Analyze game ending at move N (default=1000)", metavar="N")
    parser.add_option('', '--analyze-threshold', dest='delta_sensitivity', default=0.02, type=float,
                      help="Display analysis on moves losing at least this much win rate (default=0.02)")
    parser.add_option('', '--variations-threshold', dest='delta_sensitivity2', default=0.05, type=float,
                      help="Display variations on moves losing at least this much win rate (default=0.05)")

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
        SZ = int(C.node['SZ'].data[0])
    else:
        SZ = 19

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
    while not C.atEnd:
        C.next()
        cnode = C.node
        if cnode.has_key('C'):
            cnode['C'].data[0] = ""

    task_size=calculate_task_size(sgf, options.analyze_start, options.analyze_end)
    print >>sys.stderr, "Executing %d analysis steps" % (task_size)
    pb = progressbar.ProgressBar(max_value=task_size)
    pb.start()

    leela = leela.CLI(board_size=SZ,
                          executable=options.executable,
                          verbosity=options.verbosity)

    collected_winrates = {}
    collected_best_moves = {}
    collected_best_move_winrates = {}

    try:
        move_num = -1
        C = sgf.cursor()
        prev_analysis_comment = ""
        prev_lb_values = []

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
            if (move_num >= options.analyze_start and move_num <= options.analyze_end) or (move_num in comment_requests_analyze):
                ckpt_hash = 'analyze_' + leela.history_hash()
                ckpt_fn = os.path.join(base_dir, ckpt_hash)
                if options.verbosity > 2:
                    print >>sys.stderr, "Looking for checkpoint file:", ckpt_fn
                if os.path.exists(ckpt_fn):
                    if options.verbosity > 1:
                        print >>sys.stderr, "Loading checkpoint file:", ckpt_fn
                    with open(ckpt_fn, 'r') as ckpt_file:
                        stats, move_list = pickle.load(ckpt_file)
                        pb.increment()
                else:
                    stats, move_list = do_analyze(C, leela, pb)

                with open(ckpt_fn, 'w') as ckpt_file:
                    pickle.dump((stats, move_list), ckpt_file)

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

                if(delta <= -options.delta_sensitivity):
                    (delta_comment,delta_lb_values) = annotations.format_delta_info(delta,stats,this_move)
                    annotations.annotate_sgf(C, delta_comment, delta_lb_values)


                annotations.annotate_sgf(C, annotations.format_winrate(stats,move_list,SZ), [])

                if (move_num-1) in comment_requests_analyze or delta <= -options.delta_sensitivity:
                    C.previous()
                    annotations.annotate_sgf(C, prev_analysis_comment, prev_lb_values)
                    C.next()

                (analysis_comment, lb_values) = annotations.format_analysis(stats, move_list)
                prev_analysis_comment = analysis_comment
                prev_lb_values = lb_values

            # if analysis_mode=='variations':
            #     ckpt_hash = ('analyze_%d_%d_' + leela.history_hash()) % (options.num_branches, options.depth)
            #     ckpt_fn = os.path.join(base_dir, ckpt_hash)
            #     if options.verbosity > 2:
            #         print >>sys.stderr, "Looking for checkpoint file:", ckpt_fn
            #     if os.path.exists(ckpt_fn):
            #         if options.verbosity > 1:
            #             print >>sys.stderr, "Loading checkpoint file:", ckpt_fn
            #         with open(ckpt_fn, 'r') as ckpt_file:
            #             stats, move_list, sequences = pickle.load(ckpt_file)
            #         pb.increment( 1+sum(len(seq) for seq in sequences) )
            #     else:
            #         stats, move_list, sequences = do_analyze(C, leela, pb)

            #     if 'winrate' in stats and stats['visits'] > 1000:
            #         collected_winrates[move_num] = (current_player, stats['winrate'])

            #     annotations.format_analysis(C, leela.whoseturn(), stats, move_list)
            #     for seq in sequences:
            #         annotations.format_variation(C, seq)

            #     with open(ckpt_fn, 'w') as ckpt_file:
            #         pickle.dump((stats, move_list, sequences), ckpt_file)

    except:
        print >>sys.stderr, "Failure in leela, reporting partial results...\n"
        traceback.print_exc()
    finally:
        leela.stop()

    if options.win_graph:
        graph_winrates(collected_winrates, "black", options.win_graph)

    pb.finish()
    print sgf
