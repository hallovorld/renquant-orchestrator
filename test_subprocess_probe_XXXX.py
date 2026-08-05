import subprocess, sys

def test_child_probe():
    code = "import os, urllib.request; from renquant_common import notify; print('env', os.environ.get('RENQUANT_NO_NOTIFY')); print('suppressed', notify.notifications_suppressed()); print('urlopen', getattr(urllib.request.urlopen, '__name__', type(urllib.request.urlopen).__name__))"
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True).stdout
    print(out)
