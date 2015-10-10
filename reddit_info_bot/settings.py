class Settings(object):

    def __init__(self, values=None, defaults={}):
        self.values = values.copy() if values else {}
        self.global_defaults = defaults

    def __getitem__(self, opt_name):
        if opt_name in self.values:
            return self.values[opt_name]
        return getattr(self.global_defaults, opt_name, None)

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=False):
        return bool(int(self.get(name, default)))

    def getint(self, name, default=0):
        return int(self.get(name, default))

    def getfloat(self, name, default=0.0):
        return float(self.get(name, default))

    def getlist(self, name, default=None):
        value = self.get(name)
        if value is None:
            return default or []
        elif hasattr(value, '__iter__'):
            return value
        else:
            return str(value).split(',')
