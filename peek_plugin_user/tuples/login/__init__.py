from txhttputil.util.ModuleUtil import filterModules

def loadTuples():
    for mod in filterModules(__name__, __file__):
        __import__(mod, locals(), globals())
