"""Bounded cleanup of an experiment-owned process session only."""
import os
import signal
import time


def stop_group(pgid):
    if pgid <= 1 or pgid == os.getpgrp():
        raise ValueError('Refusing to terminate the controller process group')
    sent = False
    try:
        os.killpg(pgid, signal.SIGTERM)
        sent = True
    except ProcessLookupError:
        return {'pgid': pgid, 'signal_sent': False}
    time.sleep(0.5)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return {'pgid': pgid, 'signal_sent': sent}
