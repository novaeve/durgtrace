"""Verify that a task's GPU-style child retaining lease FDs is terminated on exit."""
from pathlib import Path
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from process_cleanup import stop_group


class CleanupTests(unittest.TestCase):
    def test_private_group_releases_inherited_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            code = ('import fcntl,os,subprocess,sys,time; '
                    'f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX); '
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],pass_fds=[f.fileno()]); '
                    'open(sys.argv[2],"w").write(str(p.pid)); time.sleep(60)')
            proc = subprocess.Popen([sys.executable, '-c', code, str(folder / 'lease'), str(folder / 'child.pid')],
                                     start_new_session=True)
            try:
                deadline = time.time() + 5
                while not (folder / 'child.pid').exists() and time.time() < deadline:
                    time.sleep(0.05)
                self.assertTrue((folder / 'child.pid').exists())
                with (folder / 'lease').open('a') as lock:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                stop_group(proc.pid)
                proc.wait(timeout=5)
                with (folder / 'lease').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                stop_group(proc.pid)
                proc.wait(timeout=5)

    def test_controller_group_is_protected(self):
        with self.assertRaises(ValueError):
            stop_group(os.getpgrp())
        with self.assertRaises(ValueError):
            stop_group(1)


if __name__ == '__main__':
    unittest.main()
