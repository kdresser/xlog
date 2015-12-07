
#
## xviewer: Imported by xlog server for displaying log messages in
##            verbose mode.
##          Expects a simple message in _msg.
##          Outputs to a simple logger passed in **b.
#

def main(*a, **b):
    _msg = b.get('_msg', 'None')
    if _msg == 'None':
        return
    sl = b['sl']
    try:    el = int(b['_el'])
    except: el = None
    ###msg = '%-4s %-4s %1s %1s %s' % (b['_id'], b['_si'], b['_el'], b['_sl'], _msg)
    lines = _msg.split('||')
    pfx = '%4s %4s %1s %1s ' % ((str(b['_id'])+'    ')[:4], 
                                (str(b['_si'])+'    ')[:4], 
                                (str(b['_el'])+' '   )[:1], 
                                (str(b['_sl'])+' '   )[:1])
    for line in lines:
        msg = pfx + line.replace('|', ' | ')           
        if   el == 0:   sl.null    (msg)
        elif el == 1:   sl.debug   (msg)
        elif el == 2:   sl.info    (msg)
        elif el == 3:   sl.warning (msg)
        elif el == 4:   sl.error   (msg)
        elif el == 5:   sl.critical(msg)
        else:           sl.extra   (msg)
        pfx = len(pfx) * ' '

