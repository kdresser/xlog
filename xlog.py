"""
xlog: A server for receiving and storing log messages from 
      clients via TCP/IP.
* Licensed under terms of MIT license (see LICENSE-MIT)
* Copyright (c) 2015 J. Kelly Dresser, kellydresser@gmail.com

Usage:
  xlog.py [--ini=<ini> --host=<host> --ippfx=<ippfx> --port=<port> --log_path=<log_path> --verbose=<verbose>]
  xlog.py (-h | --help | --version)

Options:
  -h --help              Show help.
  --version              Show version.
  --ini=<ini>            Optional ini pfn.
  --host=<host>          Host.
  --ippfx=<ippfx>        Host pfx (for shortening logging).
  --port=<port>          Port.
  --log_path=<log_path>  Flat-file log path.
  --verbose=<verbose>    True, 1 -> lines, not dots, to screen
"""

#> !P3!

#> 2v1
#> 2v2 : fix missing verbose output
#> 2v3 : minor upgrades
#> 2v4 : new logfile roller

###
### xlog: - A server for accepting and storing log messaged from 
###         TCP/IP-connected clients.
###       - Interleaved log messages are output to a flat file.
###       - Control params from xlog.ini (default) and argv[1].
###       - Uses a threaded socketserver from Python standard 
###         library.  File writing is done from a thread.
###         Ctrl-c will stop the server.
###       - An optional verbose flag will call the main() function
###         of a named module with each log record received.  
###         The usual action performed by it is to write log info
###         to the console.  Without this flag True, each log 
###         record is marked by a dot on the console.
###

###
### Client sends a json'd dict of KV's:
###
###   The keys that xlog uses when flatfiling a client tx:
###
###	    _ip : IP of logging server's client
###	    _ts	: UTC float, client's tx timestamp (or rx if none)
###	    _id	: SRC id (length 4, alphanumeric)
###           Identifies the client/app: major.
###	    _si	: SUB id (length 4, alphanumeric)
###           Identifies the client/app: minor.
###	    _el	: ERR level (length 1) (numeric, 0..5 usually)
###           Usually the Python level numbers, but *nix levels
###           could be represented by letters, e.g., 'a'..'g' 
###           for 0..7.
###	    _sl	: SUB level (length 1, alphanumeric)
###           An arbitrary flag column, to aid filtering xlog's 
###           flatfile.
###
###         (_id, _si, _el, _sl default to '_' chars)
###
###  All keys remain in the KV lump for downstreamers.
###

###
### The Python error levels (00..50 divided by 10):
###
###   0: NOTSET
###   1: DEBUG
###   2: INFO
###   3: WARNING
###   4: ERROR
###   5: CRITICAL
###   

###
### The message prefixes added by l_simple_logger methods:
###
###   NULL          __
###   DEBUG         ..
###   INFO          --
###   WARNING       >>
###   ERROR         **
###   CRITICAL      !!
###   EXTRA         ~~              (Probably a bad idea.)

### 
### The flatfile output from xlog:
###
### OLD version (implicitly FFV 0), using | delimiters.
###
###
###  Col   Len  Contents                           
###  ---   ---  -----------------------------------
###   01    15	UTCUT TimeStamp: server rx
###   16     |
###   17    15	UTCUT TimeStamp: client tx
###   32     |
###   33     4	SRC id: Client ID: Major
###   37     |
###   38     4	SUB id: Client ID: Minor
###   42     |
###   43     1	ERR level (0..5 usually)
###   44     |
###   45     1	SUB level: Custom
###   46     |
###   47    40	SHA1 of contents string
###   87     |
###   88   var	Contents string (json of dict)
###
### rrrrrrrrrrrrrrr|ttttttttttttttt|IIII|iiii|E|e|ssssssssssssssssssssssssssssssssssssssss|{...}
### ....:....1....:....2....:....3....:....4....:....5....:....6....:....7....:....8....:....9....:....A
###
### NEW version (explicitly FFV 1), using \t delimiters.
###
###  Col   Len  Contents                           
###  ---   ---  -----------------------------------
###   01     1  FlatFile Version ('1')
###   02     _
###   03    15	UTCUT TimeStamp: server rx
###   18     _
###   19    15	UTCUT TimeStamp: client tx
###   34     _
###   35     4	SRC id: Client ID: Major
###   39     _
###   40     4	SUB id: Client ID: Minor
###   44     _
###   45     1	ERR level (0..5 usually)
###   46     _
###   47     1	SUB level: Custom
###   48     _
###   49    40	SHA1 of contents string
###   89     _
###   90   var	Contents string (json of dict)
###
### 1_rrrrrrrrrrrrrrr_ttttttttttttttt_IIII_iiii_E_e_ssssssssssssssssssssssssssssssssssssssss_{...}
### ....:....1....:....2....:....3....:....4....:....5....:....6....:....7....:....8....:....9....:....A
###

import os, sys, stat, time, datetime, calendar
import shutil, collections, pickle, copy, json
import queue, threading, hashlib, importlib
from socketserver import BaseRequestHandler, TCPServer, ThreadingMixIn

gP2 = (sys.version_info[0] == 2)
gP3 = (sys.version_info[0] == 3)
assert gP3, 'requires Python 3'

gWIN = sys.platform.startswith('win')
gLIN = sys.platform.startswith('lin')

####################################################################################################

SQUAWKED = False                # To suppress chained exception messages.
def DOSQUAWK(errmsg, beeps=3):
    """For use in exception blocks."""
    global SQUAWKED
    if not SQUAWKED:
        _m.beeps(beeps)
        for em in errmsg.split('\n'):
            _sl.error(em)
        SQUAWKED = True

####################################################################################################

import l_dt as _dt              # Date, time helpers.
import l_misc as _m              

import l_screen_writer
_sw = l_screen_writer.ScreenWriter()             

import l_simple_logger 
_sl = l_simple_logger.SimpleLogger(screen_writer=_sw)

import l_args as _a             # INI + command line args.
ME = _a.get_args(__doc__, '0.1')

HOST     = _a.ARGS['--host']
IPPFX    = _a.ARGS['--ippfx']
PORT     = int(_a.ARGS['--port'])
LOG_PATH = _a.ARGS['--log_path']    # Can be null if VERBOSE.
HP = (HOST, PORT)
VERBOSE  = _a.x2bool(_a.ARGS.get('-v'), False) or \
           _a.x2bool(_a.ARGS.get('--verbose'), False)
if VERBOSE:
    VIEWER = _a.ARGS.get('--viewer')
    if not VIEWER:
        errmsg = 'no VIEWER module name'
        raise ValueError(errmsg)
    VM = importlib.import_module(VIEWER)
    _sl.info('imported %s -> %s' % (VIEWER, repr(VM)))
else:
    VIEWER = VM = None
    _sl.info('not VERBOSE')

ENCODING    = 'utf-8'             
ERRORS      = 'strict'

_ = '\t'    # Tab is the new | (separator for fields in prefix).
FFV = '1'   # Flatfile version (151101: Version added, _si added, '\t' instead of '|').

####################################################################################################

# TimeStamp, serialized.

TSLOCK = threading.Lock()

# TSLOCK...

CHK_UTC_TS = 0                      # UTC TS of last file roll check.
UTC_TS = None                       # Current UTC TS, float with fractional seconds.
UTC_UT = None                       # Current UTC UT, integer, without seconds rounding (i.e., truncation).
UTC_TS_STR = None                   # Current UTC TS string with 4 decimals.
# UTC:
UTC_YMD = None                      # Current TS YYMMDD (6 digits), UTC.
UTC_HMS = None                      # Current TS HHMMSS (6 digits), UTC.
# LOCal:
LOC_YMD = None                      # Current TS YYMMDD (6 digits), local.
LOC_HMS = None                      # Current TS HHMMSS (6 digits), local.
# Log.
LOG_PFN = None                      # Current log pfn.
LOG_FILE = None                     # Current log file handle.

# Update timestamp variables.  Local and UTC versions.
# These will (now) always be real time timestamps.
# They are used to supply timestamps to log records not having any,
# and for generating the flatfile filenames.
# Historical log recs will still have their own internal timestamp and 
# it will appear in the flatfile record prefix, but in a contemporarily
# named flatfile.
def update_ts(utcut=None):
    global UTC_TS, UTC_UT, UTC_TS_STR, UTC_YMD, UTC_HMS, LOC_YMD, LOC_HMS
    me = 'update_ts(%r)' % utcut
    try:
        if utcut:
            UTC_TS = utcut
        else:
            UTC_TS = _dt.utcut()
        UTC_TS_STR = '{:15.4f}'.format(UTC_TS)
        UTC_UT = int(UTC_TS)            # Truncate to integer.
        utc = time.gmtime(UTC_UT)
        loc = time.localtime(UTC_UT)
        UTC_YMD = '%02d%02d%02d' % (utc.tm_year % 100, utc.tm_mon, utc.tm_mday)
        UTC_HMS = '%02d%02d%02d' % (utc.tm_hour, utc.tm_min, utc.tm_sec)
        LOC_YMD = '%02d%02d%02d' % (loc.tm_year % 100, loc.tm_mon, loc.tm_mday)
        LOC_HMS = '%02d%02d%02d' % (loc.tm_hour, loc.tm_min, loc.tm_sec)
    except Exception as E:
        errmsg = '{}: {} @ {}'.format(me, E, m.tblineno())
        DOSQUAWK(errmsg)
        raise

# ...TSLOCK

####################################################################################################

# Log file functions.  Called mostly by file writer thread, so not serialized.  

# See notes.txt file(s) for layout.

# log_close also zaps LOG_PFN and LOG_FILE.
def log_close():
    global LOG_PFN, LOG_FILE
    LOG_PFN = None
    try:  LOG_FILE.close()
    except:  pass
    LOG_FILE = None

def log_open():
    global LOG_FILE
    if LOG_FILE:
        LOG_FILE.close()    # Close without zapping LOG_PFN.
    (p, fn) = os.path.split(LOG_PFN)
    if not os.path.isdir(p):
        os.makedirs(p)
    LOG_FILE = open(LOG_PFN, 'a', encoding=ENCODING, errors=ERRORS, buffering=1)  # 1 -> line buffering, obviating flushing.

# Build a log file path+fn using local time (for time and date rolling).
def current_log_pfn():
    if not LOG_PATH:
        return None
    z = LOG_PATH
    z = z.replace('~me~',   ME)
    # Use LOCal time.
    z = z.replace('~y~',    LOC_YMD[:2])
    z = z.replace('~ym~',   LOC_YMD[:4])
    z = z.replace('~ymd~',  LOC_YMD)
    z = z.replace('~h~',    LOC_HMS[:2])
    z = z.replace('~hm~',   LOC_HMS[:4])
    z = z.replace('~hms~',  LOC_HMS)
    return z

####################################################################################################

# Log file writing thread.

LFQ = None              # Log File Queue (to output thread).
LFT = None              # Log File Thread.
LFTSTOP = None          # Log File Thread signal to STOP.
LFTSTOPPED = None       # Log File Thread has responded to LFTSTOP.

def reformatLogrec(logrec):
    """Add a prefix to a sorted source logrec."""
    #
    #  In: 0.0.0.0|{...json dict payload...} 
    # Out: (rc, rm, newrec)
    #   rc: True (OK), False
    #   rm: 'OK' or errmsg
    #   newrec:  151101: Added _si.
    #                    | -> \t
    #                    Added FFV.
    #       timestamps, defaults, SHA1 and sorted json dict into a flatfile record:
    #       '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' %(FFV, UTC_TS_STR, _ts, _id, _si, _sl, _el, _sl, sha1x, jslda)
    #       
    me = 'reformatLogrec'
    rc, rm, newrec = False, '???', None
    try:
        # logrec: tx-ip|payload.
        try:
            _ip, payload = logrec.split(_, 1)
        except Exceptions as E:
            errmsg = 'split _ip|payload: %s' % E
            _sl.error(errmsg)#$#
            rc, rm, = False, errmsg
            # No exception.
            return
        if not _ip or not _ip[0].isdigit() or not _ip[-1].isdigit() or _ip.count('.') != 3:
            errmsg = 'bad _ip: %r' % _ip
            _sl.error(errmsg)#$#
            rc, rm, = False, errmsg
            # No exception.
            return
        if not payload or payload[0] != '{' or payload[-1] != '}':
            errmsg = 'bad json dict: %r' % payload
            _sl.error(errmsg)#$#
            rc, rm, = False, errmsg
            # No exception.
            return
        try:
            logdict = json.loads(payload)
        except Exception as E:
            errmsg = 'json.loads: %s' % E
            _sl.error(errmsg)#$#
            rc, rm, = False, errmsg
            # Swallow the exception.
            return
        # Inject the tx ip.
        logdict['_ip'] = _ip
        # Get a new realtime ts.
        update_ts()
        # Retrieve fields needed for the logrec prefix.  Supply '_' defaults.
        _ts, _id, _si, _el, _sl = \
            logdict.get('_ts'), logdict.get('_id', '____'), logdict.get('_si', '____'), logdict.get('_el', '_'), logdict.get('_sl', '_')
        # Convert int's to str's.
        if isinstance(_id, int):
            _id = '%04d' % _id
        if isinstance(_si, int):
            _si = '%04d' % _si
        if isinstance(_el, int):
            _el = '%d' % _el
        if isinstance(_sl, int):
            _sl = '%d' % _sl
        # If the sender didn't supply a ts string, use the realtime one.
        if not _ts:
            _ts = UTC_TS_STR
            logdict['_ts'] = _ts
        # Sort logdict to json and SHA1 it.
        jslda = json.dumps(logdict, ensure_ascii=True, sort_keys=True)
        # hashlib needs bytes.
        jsldab = jslda.encode(encoding=ENCODING, errors=ERRORS)
        h = hashlib.sha1()
        h.update(jsldab)
        sha1x = h.hexdigest()
        # A new logrec: a fat prefix + json'd sorted input dict.
        newrec = '%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s\n' %(FFV, _, UTC_TS_STR, _, _ts, _, _id, _, _si, _, _el, _, _sl, _, sha1x, _, jslda)        
        #                                                         |              | Optionally supplied by sender.
        #                                                         |              | Defaults to UTC_TS_STR.               
        #                                                         | Realtime xlog arrival ts.
        rc, rm = True, 'OK'
    except Exception as E:
        errmsg = '%s: %s @ %s' % (me, E, _m.tblineno())
        _sl.error(errmsg)#$#
        rc, rm, = False, errmsg
        # Swallow the exception.
    finally:
        return (rc, rm, newrec)

def logFileThread():  
    """Consume LFQ, writing to the log file."""
    # Additionally, when VERBOSE, write to screen.
    # When VERBOSE, the log file can be null.
    global CHK_UTC_TS, LOG_PFN, LFTSTOPPED
    me = 'LFT'
    # No thread-local vars bcs only one thread.
    _sl.extra(me + ' begins')
    try:          
        rplrc = 0           # Records per log roll check.
        wlpfn = None       # Working version of LOG_PFN.
        while True:
            if LFTSTOP:
                _sl.extra('STOPping')#$#
                LFTSTOPPED = True
                log_close()
                return
            try:        

                # Get a logrec from the input queue, with a 1-sec timeout.
                logrec = LFQ.get(block=True, timeout=1).rstrip()    # Strip the '\n'.
                
                # Log file?  (Via LOG_PATH. Can be null when VERBOSE.)
                if LOG_PATH:

                    # Log roll check every 1-sec.
                    if UTC_TS > (CHK_UTC_TS + 1):
                        CHK_UTC_TS = UTC_TS
                        # Were there records in the previous 1-sec?
                        if rplrc > 0:
                            # Flush.
                            LOG_FILE.flush()                
                            os.fsync(LOG_FILE.fileno())     
                            # Dots?
                            if not VERBOSE:
                                _sw.iw('.')
                        rplrc = 0
                        # Log roll?
                        wlpfn = current_log_pfn()
                        if wlpfn != LOG_PFN:
                            log_close()
                            LOG_PFN = wlpfn

                    # Ensure LOG_FILE.
                    if not LOG_FILE:
                        log_open()

                    # Output.
                    if LOG_FILE:
                        LOG_FILE.write(logrec + '\n')
                        rplrc += 1
                    else:
                        errmsg = '!!!'                          # !TODO!
                        print('** no LOG_FILE:', LOG_PFN)#$#
                
                # No log file?
                else:
                    if not VERBOSE:
                        raise ValueError('no LOG_FILE from: ' + LOG_PFN)

                # VERBOSE? (Custom output to screen.)
                if VERBOSE:
                    try:    
                        a = logrec.split(_, 9)
                        ffv = a.pop(0)
                        b = json.loads(a.pop(-1))
                        b['sl'] = _sl
                        ###
                        id, si, el, sl, msg = b['_id'], b['_si'], b['_el'], b['_sl'], b.get('_msg', 'None')
                        ###
                        VM.main(*a, **b)
                    except Exception as E: 
                        errmsg = str(E)
                        # In case _sl is incapacitated...
                        _m.beeps(3)
                        print('!! ' + logrec + ' !! ' + errmsg + ' !!')

            except queue.Empty:
                pass
    except Exception as E:
        errmsg = '%s: %s @ %s' % (me, E, _m.tblineno()) + '\n' + \
                 '%s: LR: %s' % (me, repr(logrec))
        DOSQUAWK(errmsg)
        raise
    finally:
        _sl.extra(me + ' ends')

def startLogFileThread():
    global LFQ, LFT
    LFQ = queue.Queue()
    LFT = threading.Thread(target=logFileThread)
    LFT.daemon = True
    LFT.start()
    # The rolling log file name and the file object are maintained by LFT.

####################################################################################################

# Threaded socketserver from Python standard library.

NCX = 0     # Number of server connections.
NOCX = 0    # Number of open server connections.

def create_server_socket(address):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(5)      # Allow a backlog of 5.
    _sl.trace('listening at {}'.format(address))
    return listener

def handle_connection(skt, address):
    global NCX, NOCX, XLOGSTOP
    try:
        NCX += 1
        NOCX += 1
        _sl.info('handle_connection: %d (%d open): %r' % (NCX, NOCX, address))
        with skt.makefile(encoding=ENCODING, errors=ERRORS, newline='\n')as cf:
            while True:
                rx = cf.readline()
                tx = None
                #$#ml.debug('rx: %r' % rx.rstrip())#$#
                if rx:
                    rx = rx.rstrip()
                    if not rx:
                        continue
                        # ??? Or, should this be ACK'd with an OK?
                    if   rx[0] == '!' and rx[-1] == '!':
                        tx = b'OK|' + rx.encode(encoding=ENCODING, errors=ERRORS)
                    elif rx == '!STOP!':
                        XLOGSTOP = True
                        tx = b'OK'
                    else:
                        # Should be a log record.
                        # Add the source IP.
                        logrec = address[0] + _ + rx
                        # Reformat to final log file format.
                        (rc, rm, newrec) = reformatLogrec(logrec)
                        # Queue to log file writing thread.
                        if rc:
                            LFQ.put(newrec)
                            tx = b'OK'
                        else:
                            # Instead of an 'OK', echo the bad record.
                            tx = 'E: ' + rm             # The squawk from xlog.
                            z  = ':: ' + logrec         # The offending logrec.
                            _sl.error(tx)#$#             
                            _sl.error(z)#$#                 
                            tx = tx.encode(encoding=ENCODING, errors=ERRORS)
                    # Respond to sender.
                    if tx:
                        skt.sendall(tx + b'\n')
                else:
                    # Connection EOF.
                    _sl.info('no more rx')
                    break
        _sl.info('skt.makefile done')
    except EOFError:
        _m.beeps(1)
        msg = 'client socket to {} has closed'.format(address)
        _sl.warning(msg)
        pass            # POR.
    except ConnectionResetError as E:
        _m.beeps(1)     # Usually not serious.
        msg = 'client {} closed connection'.format(address)
        _sl.info(msg)
        pass            # POR.
    except ConnectionAbortedError as E:
        _m.beeps(2)     # Perhaps a little more serious.
        msg = 'client {} aborted connection'.format(address)
        _sl.info(msg)
        pass            # POR.
    except Exception as E:
        _m.beeps(3)
        errmsg = 'client {} error: {} @ {}'.format(address, E, _m.tblineno())
        _sl.error(errmsg)
        pass            # POR.
    finally:
        msg = 'handle_connection: close -> %d open' % NOCX
        _sl.info(msg)
        NOCX -= 1
        try:  skt.close()
        except: pass

class Handler(BaseRequestHandler):
    def handle(self):
        handle_connection(self.request, self.client_address)

class ThreadedServer(ThreadingMixIn, TCPServer):
    allow_reuse_address = 1

XLOGSTOP = None             # Distinct from LFTSTOP.  Used for remote shutdown via '!STOP!'.

#
# main: xlog
#
def xlog():
    global LFTSTOP 
    me, action = 'main', ''
    try:
        _sl.info(me + ' begins')#$#
        _sl.info()
        _sl.info('     host: ' + HOST)
        _sl.info('    ippfx: ' + IPPFX)
        _sl.info('     port: ' + str(PORT))
        _sl.info('       hp: ' + str(HP))
        _sl.info(' log_path: ' + LOG_PATH)
        _sl.info('  verbose: ' + str(VERBOSE))
        if VERBOSE:
            _sl.info('   viewer: ' + str(VIEWER))
            _sl.info('       vm: ' + repr(VM))
        _sl.info()

        startLogFileThread()

        # Fake a log record from self.  Fake the json'd dict.  Use '0.0.0.0' as self.
        z = '%s%s{"_id": "%s", "_si": "%s", "_el": %d, "_sl": "%s", "_msg": "%s"}' %\
            ('0.0.0.0', _, '----', '----', 0, '_', (me + ' begins @ %s' % _dt.ut2iso(_dt.locut())))
        (rc, rm, newrec) = reformatLogrec(z)
        LFQ.put(newrec)

        _sl.info('starting server on %r' % (HP, ))
        server = ThreadedServer(HP, Handler)
        server.daemon_threads = True            # !!! Crucial! (Otherwise responder threads never exit.)
        ip, port = server.server_address
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        _sl.info('server running in %s' % server_thread.name)

        while True:
            if XLOGSTOP:
                break
            time.sleep(1)

        _sl.warning('server shutdown')
        server.shutdown()
        _sl.warning('server close')
        server.server_close()
        
    except KeyboardInterrupt as E:
        errmsg = '{}: KeyboardInterrupt: {}'.format(me, E)
        DOSQUAWK(errmsg, beeps=1)
        pass###raise
    except Exception as E:
        errmsg = '{}: E: {} @ {}'.format(me, E, _m.tblineno())
        DOSQUAWK(errmsg)
        raise
    finally:
        # Either: a '!STOP!' record, a KeyboardInterrupt, or an Exception.
        if LFT:
            # Fake a received log record.
            z = '%s%s{"_id": "%s", "_el": %d, "_sl": "%s", "_msg": "%s"}' %\
                ('0.0.0.0', _, '----', 0, '_', (me + ' ends @ %s' % _dt.ut2iso(_dt.locut())))
            (rc, rm, newrec) = reformatLogrec(z)
            LFQ.put(newrec)

            # Wait some to let LFT empty tis queue.
            tw, w, mt = 0, 0.1, False
            while tw < 10:
                time.sleep(w)
                tw += w
                if LFQ.empty():
                    mt = True
                    break
            if not mt:
                errmsg = 'LFT did not empty its queue'
                _sl.error(errmsg)

            # Shut down log file writing thread.
            LFTSTOP = True
            try:
                LFT.join(10)
                if LFTSTOPPED:
                    pass
                else:
                    errmsg = 'LFT didn\'t acknowledge STOP request'
                    _sl.error(errmsg)
            except Exception as E:
                errmsg = 'LFT.join(10): %s' % E
                DOSQUAWK(errmsg)
                raise

        try:  LOG_FILE.close()
        except:  pass
        _sl.info(me + ' ends')#$#

# Test data

A0 = '108.212.110.142 - - [03/Aug/2015:12:53:06 -0700] "GET /pix/t/American%20Eros%20by%20Mark%20Henderson HTTP/1.1" 200 46 "http://worldofmen.yuku.com/topic/9735/American-Eros-by-Mark-Henderson" "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/600.7.12 (KHTML, like Gecko) Version/7.1.7 Safari/537.85.16"'
A1 = '{"_el": "2", "_id": "nx01", "_ip": null, "_sl": "_", "_ts": "1438631586.    ", "ae": "a", "body_bytes_sent": 46, "http_referer": "http://worldofmen.yuku.com/topic/9735/American-Eros-by-Mark-Henderson", "http_user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/600.7.12 (KHTML, like Gecko) Version/7.1.7 Safari/537.85.16", "remote_addr": "108.212.110.142", "remote_user": null, "request": "GET /pix/t/American%20Eros%20by%20Mark%20Henderson HTTP/1.1", "status": 200, "time_local": "[03/Aug/2015:12:53:06 -0700]", "time_utc": 1438631586}'

E0 = '2015/08/03 17:48:28 [error] 1199#0: *2502 open() "/var/www/184.69.80.202/wordpress/wp-login.php" failed (2: No such file or directory), client: 58.8.154.9, server: 184.69.80.202, request: "GET /wordpress/wp-login.php HTTP/1.1", host: "wp.go-print.com"'
E1 = '{"_el": "4", "_id": "nx01", "_ip": null, "_sl": "_", "_ts": "1438649308.    ", "ae": "e", "client": "58.8.154.9", "errmsg": "(2: No such file or directory)", "error": "NF", "host": "wp.go-print.com", "mystery": "1199#0:|*2502", "referrer": null, "request": "GET /wordpress/wp-login.php HTTP/1.1", "resource": "/var/www/184.69.80.202/wordpress/wp-login.php", "server": "184.69.80.202", "status": "[error]", "time_local": "2015/08/03 17:48:28", "time_utc": 1438649308}'

if __name__ == '__main__':

    '''...
    # Test crunching.
    t0 = time.time()
    A = '192.168.100.6|' + A1
    for x in range(1000):
        (rc, rm, B) = reformatLogRec(A)
    t1 = time.time()
    print('%.3f ms/reformat' % (1000.0 * (t1 - t0) / 1000.0))
    # -> 0.125 ms/reformat
    sys.exit()
    ...'''

    try:
        xlog()
    except KeyboardInterrupt as E:
        errmsg = '{}: KeyboardInterrupt: {}'.format(ME, E)
        DOSQUAWK(errmsg, beeps=1)
        pass###raise
    except Exception as E:
        errmsg = '{}: E: {} @ {}'.format(ME, E, _m.tblineno())
        DOSQUAWK(errmsg)
        raise
    finally:
        try:  LOG_FILE.close()
        except:  pass
        _sl.info(ME + ' ends')#$#
