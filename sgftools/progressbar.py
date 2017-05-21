import sys
import datetime

class ProgressBar(object):

    def __init__(self, min_value = 0, max_value = 100, width = 50, frequency=1, stream=sys.stderr):
        self.max_value = max_value
        self.min_value = min_value
        self.value = min_value

        self.message = None
        self.width = width
        self.stream = stream
        self.update_cnt = 0
        self.frequency=frequency

    def start(self):
        self.start_time = datetime.datetime.now()
        self.stream.write( "\n" )
        self.update(0)

    def estimate_time(self, percent):
        if percent == 0:
            return "Est..."

        n = datetime.datetime.now()
        delta = n - self.start_time
        ts = delta.total_seconds()
        tt = ts / percent
        tr = tt - ts

        H = int(tr / 3600)
        tr -= H * 3600
        M = int(tr / 60)
        tr -= M * 60
        S = int(tr)

        time_remaining = "%d:%02d:%02d" % ( H, M, S )
        return time_remaining

    def elapsed_time(self):

        n = datetime.datetime.now()
        delta = n - self.start_time

        ts = delta.total_seconds()

        H = int(ts / 3600)
        ts -= H * 3600
        M = int(ts / 60)
        ts -= M * 60
        S = int(ts)

        time_elapsed = "%d:%02d:%02d" % ( H, M, S )
        return time_elapsed

    def update_max(self, value):
        self.max_value = value
        self.update(self.value)

    def update(self, value):
        self.value = value

        D = float(self.max_value - self.min_value)
        if D == 0:
            percent = 1.0
        else:
            percent = float(self.value - self.min_value) / D
        bar_cnt = int( self.width * percent )

        bar_str = "=" * bar_cnt
        bar_str += " " * (self.width - bar_cnt)

        percent_str = "%0.2f" % (100.0 * percent)
        time_remaining = self.estimate_time(percent)

        if self.update_cnt % self.frequency == 0:
            if self.message is None:
                self.stream.write( "\r|%s| %6s%% | %s | %d / %d" % (bar_str, percent_str, time_remaining, value, self.max_value) )
            else:
                self.stream.write( "\r|%s| %6s%% | %s | %d / %d | %s" % (bar_str, percent_str, time_remaining, value, self.max_value, self.message) )
        self.update_cnt += 1

    def set_message(self, message):
        self.message = message

    def increment(self, step=1):
        self.update( self.value + step )

    def finish(self):
        self.update(self.max_value)
        bar_str = "=" * self.width
        time_remaining = self.elapsed_time()
        self.stream.write( "\r|%s| 100.00%% | Done. | Elapsed Time: %s                                             \n" % (bar_str, time_remaining) )
