import six
import copy
import json
from importlib import import_module

from . import default_settings


class Settings(object):

    def __init__(self, values=None):
        self.attributes = {}
        self.setmodule(default_settings)
        if values is not None:
            self.setdict(values)

    def __getitem__(self, name):
        value = None
        if name in self.attributes:
            value = self.attributes[name]
        return value

    def __iter__(self):
        return iter(self.attributes)

    def __len__(self):
        return len(self.attributes)

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=False):
        return bool(int(self.get(name, default)))

    def getint(self, name, default=0):
        return int(self.get(name, default))

    def getfloat(self, name, default=0.0):
        return float(self.get(name, default))

    def getlist(self, name, default=None):
        value = self.get(name, default or [])
        if isinstance(value, six.string_types):
            value = value.split(',')
        return list(value)

    def getdict(self, name, default=None):
        value = self.get(name, default or {})
        if isinstance(value, six.string_types):
            value = json.loads(value)
        return dict(value)

    def set(self, name, value):
        self.attributes[name] = value

    def setdict(self, values):
        for name, value in six.iteritems(values):
            self.set(name, value)

    def setmodule(self, module):
        if isinstance(module, six.string_types):
            module = import_module(module)
        for key in dir(module):
            if key.isupper():
                self.set(key, getattr(module, key))

    def copy(self):
        return copy.deepcopy(self)
