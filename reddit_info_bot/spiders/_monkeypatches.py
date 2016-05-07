import scrapy
import logging
import pprint

logger = logging.getLogger('reddit_info_bot.spiders')

# MiddlewareManager extension to allow loading objects from settings
# [1] patch update_classpath
from scrapy.utils.deprecate import update_classpath, DEPRECATION_RULES
import warnings
from scrapy.exceptions import ScrapyDeprecationWarning

def update_classpath(path):
    """Update a deprecated path from an object with its new location"""
    if hasattr(path, 'startswith') and hasattr(path, 'replace'):
        for prefix, replacement in DEPRECATION_RULES:
            if path.startswith(prefix):
                new_path = path.replace(prefix, replacement, 1)
                warnings.warn("`{}` class is deprecated, use `{}` instead".format(path, new_path),
                            ScrapyDeprecationWarning)
                return new_path
    return path

scrapy.utils.deprecate.update_classpath = update_classpath
# /[1]

# [2] patch MiddlewareManager
from scrapy.middleware import MiddlewareManager
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object

def getclsname(cls):
    if hasattr(cls, '__qualname__'):
        return cls.__module__ + "." + cls.__qualname__
    return cls.__module__ + "." + cls.__name__


class ExtMiddlewareManager(MiddlewareManager):

    @classmethod
    def from_settings(cls, settings, crawler=None):
        mwlist = cls._get_mwlist_from_settings(settings)
        middlewares = []
        enabled = []
        for cls_or_clspath in mwlist:
            try:
                if callable(cls_or_clspath):
                    mwcls = cls_or_clspath
                else:
                    mwcls = load_object(cls_or_clspath)
                if crawler and hasattr(mwcls, 'from_crawler'):
                    mw = mwcls.from_crawler(crawler)
                elif hasattr(mwcls, 'from_settings'):
                    mw = mwcls.from_settings(settings)
                else:
                    mw = mwcls()
                middlewares.append(mw)
                #enabled.append(mwcls.__name__)
                enabled.append(getclsname(mwcls))
            except NotConfigured as e:
                if e.args:
                    clsname = cls_or_clspath.split('.')[-1]
                    logger.warning("Disabled %(clsname)s: %(eargs)s",
                                   {'clsname': clsname, 'eargs': e.args[0]},
                                   extra={'crawler': crawler})

        logger.debug("Enabled %(componentname)ss:\n%(enabledlist)s",
                    {'componentname': cls.component_name,
                     'enabledlist': pprint.pformat(enabled)},
                    extra={'crawler': crawler})
        return cls(*middlewares)

scrapy.middleware.MiddlewareManager = ExtMiddlewareManager
# /[2]
# /end MiddlewareManager extension
