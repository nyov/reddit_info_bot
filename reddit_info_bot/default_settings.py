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

LOG_LEVEL = 'DEBUG'

##
## reddit settings
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

BOT_MODE = []

# bot commands
BOTCMD_IMAGESEARCH_ENABLED = True
BOTCMD_IMAGESEARCH = [ # (main) initiate image search
    'u/%s' % REDDIT_ACCOUNT_NAME,
]
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

Obtain more information by making a comment in the thread which includes /u/%s""" % BOT_NAME
)


COMMENT_REPLY_AGE_LIMIT = 0 # ignore comments older than
COMMENT_DELETIONCHECK_WAIT_LIMIT = 30 # first schdule deletion of downvoted comment after

REDDIT_SPAMFILTER_SUBMISSION_ID = ''


IMAGE_FORMATS = ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png']


FOOTER_INFO_MESSAGE = (
"""

 *****
 ^(%s %s)
""" % (BOT_NAME, BOT_VERSION)
)


SUBREDDITS = ['all']

##
## search agent settings
##

SEARCH_USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)
