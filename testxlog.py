#> !P3!

###
### testxlog: Test xlog server.
###

"""
Usage:
  testxlog.py [--ini=<ini> --srcid=<srcid> --subid=<subid> --el=<el> --sl=<sl> --count=<count> --rate=<rate> --hp=<hp>]
  testxlog.py (-h | --help | --version)

Options:
  -h --help              Show help.
  --version              Show version.
  --ini=<ini>            Overrides default ini pfn.
  --srcid=<srcid>        Source ID.
  --subid=<subid>        Sub-id.
  --el=<el>              Error Level.
  --sl=<sl>              Sub Level.
  --count=<count>        Number of messages to send.
  --rate=<rate>          Minimum time between transmissions.
  --hp=<hp>              host:port of xlog server.
"""

import os, sys, stat
import time, datetime, calendar
import shutil
import collections
import pickle
import copy
import json
import configparser
import threading
import re
import gzip

import docopt

gP2 = (sys.version_info[0] == 2)
gP3 = (sys.version_info[0] == 3)
assert gP3, 'requires Python 3'

gWIN = sys.platform.startswith('win')
gLIN = sys.platform.startswith('lin')

####################################################################################################

import l_dt as _dt              # Date, time helpers.
import l_misc as _m              

import l_screen_writer
_sw = l_screen_writer.ScreenWriter()             

import l_simple_logger 
_sl = l_simple_logger.SimpleLogger(screen_writer=_sw)

import l_args as _a             # INI + command line args.
ME = _a.get_args(__doc__, '0.1')

SRCID = _a.ARGS['--srcid']
SUBID = _a.ARGS['--subid']
EL    = _a.ARGS['--el']
SL    = _a.ARGS['--sl']
COUNT = _a.ARGS['--count']
RATE  = _a.ARGS['--rate']
HP    = _a.ARGS['--hp']

HOST, PORT = HP.split(':')
PORT = int(PORT)

SQUAWKED = False

####################################################################################################

import l_xlog

from l_xlogtxrx import XLogTxRx

####################################################################################################

# Test xlogtxrx.

ENSURE_ASCII = True
SORT_KEYS = True

def test():
    me, action = 'TEST', ''
    try:

        _sl.info('test begins')
        _sl.info('(host, port): ' + repr((HOST, PORT)))

        if True:
            # Try numbered messages to a listening xlog.
            xl = l_xlog.XLog(xloghost=HOST, xlogport=PORT, xsrcid='_SRC', xsubid='_SUB', xlogel='0', xlogsl='_', 
                             sl=None, sw=_sw, txrate=0.1)###txrate=0.02)
            1/1
            for x in range(int(COUNT)):

                if False:
                    # 0: simple str message sent as xl.null()
                    msg = 'n%03d' % (x+1)
                    _sl.info('0: %s' % msg)
                    xl.null(msg, srcid=':%03d'%(101+x), subid='.%03d'%(201+x))
                    1/1

                if True:
                    # 1: simple str message sent via msg2xlog()
                    msg = 'n%03d' % (x+1)
                    _sl.info('1: %s' % msg)
                    xl.msg2xlog(msg, srcid=':%03d'%(101+x), subid='.%03d'%(201+x), el=1, sl=2)
                    1/1

                if False:
                    # 2: ready-to-use dict sent via logd2xlog()
                    logd = {'_id': ':%03d'%(301+x), '_si': '.%03d'%(401+x), '_el': 3, '_sl': 4, '_msg': 'n%03d' % (x+1), 'n': x+1}
                    xl.logd2xlog(logd)
                    1/1

                if False:
                    # 3: ready-to-use json'd dict sent via logdj2xlog()
                    logd = {'_id': ':%03d'%(501+x), '_si': '.%03d'%(601+x), '_el': 5, '_sl': 6, '_msg': 'n%03d' % (x+1), 'n': x+1}
                    logdj = json.dumps(logd, ensure_ascii=ENSURE_ASCII, sort_keys=SORT_KEYS)
                    xl.logdj2xlog(logdj)
                    1/1

                time.sleep(float(RATE))

            1/1
            while xl.busy():
                _m.beep()
                time.sleep(0.5)
            xl.close()
            1/1

        _sl.info('test ends')
        1/1

    except Exception as E:
        errmsg = 'test: {} @ {}'.format(str(E), _m.tblineno())
        _sl.error(errmsg)
        raise
    finally:
        1/1

####################################################################################################

if __name__ == '__main__':

    try:
        test()
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt as E:
        msg = '{}: KeyboardInterrupt: {} @ {}'.format(ME, str(E), _m.tblineno())
        _sl.warning(msg)
    except Exception as E:
        if not SQUAWKED:
            errmsg = '{}: E: {} @ {}'.format(ME, str(E), _m.tblineno())
            _sl.error(errmsg)
        errmsg = 'aborted'
        _sl.error(errmsg)
        ###raise
    finally:
        ###closeOutput()
        1/1

###
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=222 --rate=0.5 --hp=192.168.100.2:23456
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=222 --rate=0.5 --hp=192.168.100.1:12321
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=22  --rate=0.15 --hp=192.168.100.1:12321
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=22  --rate=0 --hp=192.168.100.1:12321
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=2  --rate=0 --hp=192.168.100.1:12321
###
### --srcid=0001 --subid=___a  --el=0  --sl=_  --count=22  --rate=0 --hp=192.168.100.5:12321
###
