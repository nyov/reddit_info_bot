from __future__ import absolute_import, unicode_literals

import logging
import signal

logger = logging.getLogger(__name__)

signal_names = {}
for signame in dir(signal):
    if signame.startswith("SIG"):
        signum = getattr(signal, signame)
        if isinstance(signum, int):
            signal_names[signum] = signame

def install_signal_handler(signal, function):
    signal.signal(signal, function)

# signal handler functions

terminating = False

def sig_int(signal_number, stack_frame):
    global terminating
    if terminating:
        sig_term(signal_number, stack_frame)
    logger.info('Received {sig!s}, shutting down (send again to force)'
                .format(sig=signal_names[signal_number]))
    terminating = True

def sig_term(signal_number, stack_frame):
    # shutdown is considered abnormal in this case
    # and exit-code is non-zero
    exc = SystemExit("Terminating on {sig!s}"
                     .format(sig=signal_names[signal_number]))
    raise exc

# signal to handler mapping
# (set up handled by python-daemon)

signal_map = {
    signal.SIGINT : sig_int,
    signal.SIGTERM: sig_term,
    signal.SIGHUP : sig_term,
}
if hasattr(signal, "SIGBREAK"):
    # windows (not that we care)
    signal_map.update({
        signal.SIGBREAK: sig_term,
    })

def running():
    # to be checked by main loop
    return not terminating
