import os
import sys
import re
import time
import fcntl
import hashlib
from subprocess import Popen, PIPE, STDOUT

def set_non_blocking(fd):
    """
    Set the file description of the given file descriptor to
    non-blocking.
    """
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    flags = flags | os.O_NONBLOCK
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)

def check_stream(fd):
    try:
        return fd.read()
    except IOError:
        pass
    return ""

class CLI(object):
    def __init__(self, board_size=19, eval_limit=None, executable='leela_090_macOS_opencl',
                 verbosity=0):
        self.history=[]
        self.eval_limit=eval_limit
        self.executable = executable
        self.verbosity = verbosity
        self.board_size = board_size

    def convert_position(self, pos):
        abet = 'abcdefghijklmnopqrstuvwxyz'
        mapped = 'abcdefghjklmnopqrstuvwxyz'
        pos = '%s%d' % (mapped[abet.index(pos[0])], self.board_size-abet.index(pos[1]))
        return pos

    def parse_position(self, pos):
        abet = 'abcdefghijklmnopqrstuvwxyz'
        mapped = 'abcdefghjklmnopqrstuvwxyz'

        X = mapped.index(pos[0].lower())
        Y = self.board_size-int(pos[1:])

        return "%s%s" % (abet[X], abet[Y])

    def history_hash(self):
        H = hashlib.md5()
        for cmd in self.history:
            _, c, p = cmd.split()
            H.update(c[0] + p)
        return H.hexdigest()

    def add_move(self, color, pos):
        if pos == '' or pos =='tt':
            pos = 'pass'
        else:
            pos = self.convert_position(pos)
        cmd = "play %s %s" % (color, pos)
        self.history.append(cmd)

    def pop_move(self):
        self.history.pop()

    def clear_history(self):
        self.history = []

    def whoseturn(self):
        if len(self.history) == 0 or 'white' in self.history[-1]:
            return 'black'
        return 'white'

    def parse_status_update(self, message):
        status_regex = r'Nodes: ([0-9]+), Win: ([0-9]+\.[0-9]+)\% \(MC:[0-9]+\.[0-9]+\%\/VN:[0-9]+\.[0-9]+\%\), PV:(( [A-Z][0-9]+)+)'

        M = re.match(status_regex, message)
        if M is not None:
            visits = int(M.group(1))
            winrate = self.to_fraction(M.group(2))
            seq = M.group(3)
            seq = [self.parse_position(p) for p in seq.split()]

            return {'visits': visits, 'winrate': winrate, 'seq': seq}
        return {}

    def start(self):
        xargs = []
        if self.eval_limit is not None:
            xargs = ['--playouts', str(self.eval_limit)]

        p = Popen([self.executable, '--gtp', '--noponder'] + xargs, stdout=PIPE, stdin=PIPE, stderr=PIPE)
        set_non_blocking(p.stdout)
        set_non_blocking(p.stderr)
        self.p = p

        time.sleep(5)
        p.stdin.write('boardsize %d\n' % (self.board_size))
        time.sleep(1)
        check_stream(p.stderr)
        check_stream(p.stdout)

    def stop(self):
        p = self.p
        p.stdin.write('exit\n')
        try: 
            p.terminate()
        except OSError:
            pass
        check_stream(p.stderr)
        check_stream(p.stdout)

    def playmove(self, pos):
        p = self.p
        color = self.whoseturn()
        cmd = 'play %s %s' % (color, pos)
        p.stdin.write(cmd)
        self.history.append(cmd)
        time.sleep(0.1)
        check_stream(p.stdout)
        check_stream(p.stderr)

    def reset(self):
        p = self.p
        p.stdin.write('clear_board\n')
        time.sleep(0.1)
        check_stream(p.stdout)
        check_stream(p.stderr)

    def boardstate(self):
        p = self.p
        p.stdin.write("showboard\n")
        time.sleep(1)
        check_stream(p.stdout)
        return check_stream(p.stderr)

    def goto_position(self):
        p = self.p
        for cmd in self.history:
            p.stdin.write(cmd+"\n")
        time.sleep(1)
        check_stream(p.stderr)
        check_stream(p.stdout)

    def analyze(self):
        p = self.p
        if self.verbosity > 1:
            print >>sys.stderr, "Analyzing state:"
            print >>sys.stderr, self.whoseturn(), "to play"
            print >>sys.stderr, self.boardstate()

        cmd = "genmove %s\n" % (self.whoseturn())
        p.stdin.write(cmd)

        updated = 0
        stderr = []
        stdout = []
        finished_regex = '= [A-Z][0-9]+'

        if self.verbosity > 0:
            print >>sys.stderr, ""
        while updated < 30:
            O = check_stream(p.stdout)
            stdout.append(O)

            L = check_stream(p.stderr)
            stderr.append(L)

            D = self.parse_status_update(L)
            if 'visits' in D:
                if self.verbosity > 0:
                    print >>sys.stderr, "\rVisited %d positions" % (D['visits']),
                updated = 0
            updated += 1
            if self.verbosity > 0:
                print >>sys.stderr, ""

            if re.search(finished_regex, ''.join(stdout)) is not None:
                break
            time.sleep(1)

        if self.verbosity > 1:
            print >>sys.stderr, ""

        p.stdin.write("\n")
        time.sleep(1)

        stderr = ''.join(stderr) + check_stream(p.stderr)
        stdout = ''.join(stdout) + check_stream(p.stdout)

        stats, move_list = self.parse(stdout, stderr)
        if self.verbosity > 0:
            print >>sys.stderr, "Chosen move: %s" % (stats['chosen'])
            if 'best' in stats:
                print >>sys.stderr, "Best move: %s" % (stats['best'])
                print >>sys.stderr, "Winrate: %f" % (stats['winrate'])
                print >>sys.stderr, "Visits: %d" % (stats['visits'])

        return stats, move_list

    def to_fraction(self, v):
        v = v.strip()
        mul=1
        if v.startswith('-'):
            mul=-1
            v = v[1:]

        W, D = v.split('.')
        if len(W) == 1:
            W = "0" + W
        return mul * float('0.' + ''.join([W,D]))

    def parse(self, stdout, stderr):
        if self.verbosity > 2:
            print >>sys.stderr, "STDOUT"
            print >>sys.stderr, stdout
            print >>sys.stderr, "STDERR"
            print >>sys.stderr, stderr


        status_regex = r'MC winrate=([0-9]+\.[0-9]+), NN eval=([0-9]+\.[0-9]+), score=([BW]\+[0-9]+\.[0-9]+)'
        move_regex = r'^([A-Z][0-9]+) -> +([0-9]+) \(W: +(\-?[0-9]+\.[0-9]+)\%\) \(U: +(\-?[0-9]+\.[0-9]+)\%\) \(V: +([0-9]+\.[0-9]+)\%: +([0-9]+)\) \(N: +([0-9]+\.[0-9]+)\%\) PV: (.*)$'
        best_regex = r'([0-9]+) visits, score (\-?[0-9]+\.[0-9]+)\% \(from \-?[0-9]+\.[0-9]+\%\) PV: (.*)'
        summary_regex = r'([0-9]+) visits, ([0-9]+) nodes(?:, ([0-9]+) playouts)(?:, ([0-9]+) p/s)'
        bookmove_regex = r'([0-9]+) book moves, ([0-9]+) total positions'

        summary = {}
        move_list = {}

        finished_regex = r'= ([A-Z][0-9]+)'
        M = re.search(finished_regex, stdout)
        if M is not None:
            summary['chosen'] = self.parse_position(M.group(1))

        finished=False
        summarized=False
        for line in stderr.split('\n'):
            line = line.strip()
            if line.startswith('================'):
                finished=True

            M = re.match(bookmove_regex, line)
            if M is not None:
                summary['bookmoves'] = int(M.group(1))
                summary['positions'] = int(M.group(2))

            if not finished:
                M = re.match(status_regex, line)
                if M is not None:
                    summary['mc_winrate'] = float(M.group(1))
                    summary['nn_winrate'] = float(M.group(2))
                    summary['margin'] = M.group(3)

                M = re.match(move_regex, line)
                if M is not None:
                    start = self.parse_position(M.group(1))
                    visits = int(M.group(2))
                    W = self.to_fraction(M.group(3))
                    U = self.to_fraction(M.group(4))
                    Vp = self.to_fraction(M.group(5))
                    Vn = int(M.group(6))
                    N = self.to_fraction(M.group(7))
                    seq = M.group(8)
                    seq = [self.parse_position(p) for p in seq.split()]

                    move_list[start] = {'visits': visits,
                                        'W': W, 'U': U, 'Vp': Vp, 'Vn': Vn,
                                        'N': N, 'seq': seq}
            elif not summarized:
                M = re.match(best_regex, line)
                if M is not None:
                    summary['best'] = self.parse_position(M.group(3).split()[0])
                    summary['winrate'] = self.to_fraction(M.group(2))

                M = re.match(summary_regex, line)
                if M is not None:
                    summary['visits'] = int(M.group(1))
                    summarized=True

        if 'bookmoves' in summary and len(move_list)==0:
            move_list[summary['chosen']] = {'visits': 0, 'W': 0}
        else:
            required_keys = ['mc_winrate', 'nn_winrate', 'margin', 'best',
                             'winrate', 'visits']
            for k in required_keys:
                if k not in summary:
                    print >>sys.stderr, "WARNING: analysis summary missing data %s" % (k)

        return summary, move_list
