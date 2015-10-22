
#
## xviewer: Imported by xlog server for displaying log 
##          messages in verbose mode.
#

def main(*a, **b):
    ml = b['ml']
    msg = '%s %s %s %s' % (b['_id'], b['_el'], b['_sl'], b['_msg'])
    try:    el = int(b['_el'])
    except: el = None
    if   el == 0:   ml.null    (msg)
    elif el == 1:   ml.debug   (msg)
    elif el == 2:   ml.info    (msg)
    elif el == 3:   ml.warning (msg)
    elif el == 4:   ml.error   (msg)
    elif el == 5:   ml.critical(msg)
    else:           ml.extra   (msg)
