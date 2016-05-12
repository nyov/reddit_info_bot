# -*- coding: utf-8 -*-
"""
Contains the default values for all settings of reddit_info_bot.

"""
import platform
from .version import __version__ as BOT_VERSION

##
## program settings
##

BOT_NAME = 'reddit_info_bot'
BOT_WORKDIR = '/'
BOT_CACHEDIR = None
BOT_CHROOTDIR = None
BOT_UMASK = 0o002

DETACH_PROCESS = False
COREDUMPS_DISABLED = False

PID_FILE = None

LOG_ENABLED = True
LOG_FILE = None
LOG_FILE_ENCODING = 'utf-8'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'
LOG_LEVEL = 'INFO'
LOG_CONFIG = {
    # ignore logs from libraries (such as requests/urllib3)
    'disable_existing_loggers': True,
}

##
## imgur API settings
##

IMGUR_CLIENT_ID = ''
IMGUR_CLIENT_SECRET = '' # optional ("anonymous" if None)

IMGUR_ALBUM_ID = ''

##
## reddit API settings
##

REDDIT_ACCOUNT_NAME = ''
REDDIT_ACCOUNT_PASS = ''
OAUTH_CLIENT_ID = ''
OAUTH_SECRET_TOKEN = ''

SECOND_ACCOUNT_NAME = ''
SECOND_ACCOUNT_PASS = ''
SECOND_OAUTH_CLIENT_ID = ''
SECOND_OAUTH_SECRET_TOKEN = ''


BOT_OWNER = REDDIT_ACCOUNT_NAME or None

# bot agent according to reddit-api rules:
#  <platform>:<app ID>:<version string> (by /u/<reddit username>)
BOT_AGENT = '%s:%s:%s%s' % (
    platform.system(),
    BOT_NAME or 'reddit_info_bot',
    BOT_VERSION,
    ' (by /u/%s)' % BOT_OWNER if BOT_OWNER else '',
)


REDDIT_SPAMFILTER_SUBMISSION_ID = ''

##
## operational settings
##

BOT_MODE = []

# bot commands
BOTCMD_IMAGESEARCH_ENABLED = True
BOTCMD_IMAGESEARCH = [ # (main) initiate image search
    'u/%s' % REDDIT_ACCOUNT_NAME,
]
BOTCMD_IMAGESEARCH_MAXRESULTS_FOR_ENGINE = 5
BOTCMD_IMAGESEARCH_RESULT_TEMPLATE = (
"""[{text}]({url})
"""
)
BOTCMD_IMAGESEARCH_MESSAGE_TEMPLATE = (
"""___

**Best {search_engine} Guesses**

{search_results}

"""
)
BOTCMD_IMAGESEARCH_WORDCLOUD_TEMPLATE = ( # if wordcloud is enabled, insert this text below search results
"""___

A wordcloud of all search results was generated and [is available on Imgur]({wordcloud_link}).

"""
)
BOTCMD_IMAGESEARCH_NO_SEARCHENGINE_RESULTS_MESSAGE = (
"""No available links from this search engine found."""
)
BOTCMD_IMAGESEARCH_NO_RESULTS_MESSAGE = (
"""No search results found."""
)


BOTCMD_INFORMATIONAL_ENABLED = False
BOTCMD_INFORMATIONAL = [ # reply to potential queries with bot-info
    'source?',
    'sauce?',
]
BOTCMD_INFORMATIONAL_REPLY = (
"""It appears that you are looking for more information.

Obtain more information by making a comment in the thread which includes /u/%s""" % REDDIT_ACCOUNT_NAME or BOT_NAME
)


BOTCMD_DOWNVOTES_ENABLED = True
BOTCMD_DOWNVOTES_TESTMODE = False # if enabled, only log action
BOTCMD_DOWNVOTES_DELETE_AFTER = 30 # only act on comments after X minutes age
BOTCMD_DOWNVOTES_DELETION_SCORE = 1 # karma score below which a comment is removed


BOTCMD_WORDCLOUD_ENABLED = True # generate and upload wordclouds
BOTCMD_WORDCLOUD_CONFIG = { # Reference: https://amueller.github.io/word_cloud/generated/wordcloud.WordCloud.html#wordcloud-wordcloud
    #'font_path': '<ttf_or_otf.path>',
    #'font_path': '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf',
    'width': 400,
    'height': 200,
    'scale': 2,
    'max_words': 200,
    'background_color': 'black',
    'relative_scaling': 0.5,
    'prefer_horizontal': 0.9,
}
BOTCMD_WORDCLOUD_STOPWORDS = [ # additional stopwords to merge with wordcloud stopwords
    'gif', 'jpg', 'jpeg', 'png', # file formats often dominating content
    'Crawled on', # strip Tineye's "Crawled on" text on every results
    'Tumblr', # mentioned way too often
]


COMMENT_REPLY_AGE_LIMIT = 0 # ignore comments older than X minutes


IMAGE_EXTENSIONS = ['tif', 'tiff', 'gif', 'jpeg', 'jpg', 'jif', 'jfif', 'jp2', 'jpx', 'j2k', 'j2c', 'fpx', 'pcd', 'png']
VIDEO_EXTENSIONS = ['mp4', 'webm', 'ogg']
OTHER_EXTENSIONS = ['gifv'] # imaginary gif-video format (mp4/webm), treat as website when scraping
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + OTHER_EXTENSIONS


FOOTER_INFO_MESSAGE = (
"""

 *****
 ^(%s %s)
""" % (BOT_NAME, BOT_VERSION)
)


SUBREDDITS = [ # list of /r/<subreddits> to watch
    'all',
]

##
## search spider (scrapy) settings
##

USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)
DOWNLOAD_TIMEOUT = 360 # in seconds
DOWNLOAD_TIMEOUT_LINKCHECK = 30

AUTOTHROTTLE_ENABLED = True
COOKIES_ENABLED = True
