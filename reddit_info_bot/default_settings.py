"""
Contains the default values for all settings of reddit_info_bot.

"""
import platform
from . import __version__ as BOT_VERSION

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

SECOND_ACCOUNT_NAME = ''
SECOND_ACCOUNT_PASS = ''


BOT_OWNER = REDDIT_ACCOUNT_NAME or BOT_NAME

# bot agent according to reddit-api rules
BOT_AGENT = '%s:%s:%s%s' % (
    platform.system(),
    BOT_NAME,
    BOT_VERSION,
    ' (by /u/%s)' % BOT_OWNER if BOT_OWNER else '',
)

BOT_MODE = []

# bot commands
BOTCMD_IMAGESEARCH_ENABLED = True
BOTCMD_IMAGESEARCH = [ # (main) initiate image search
    'u/%s' % REDDIT_ACCOUNT_NAME,
]

BOTCMD_INFORMATIONAL_ENABLED = False
BOTCMD_INFORMATIONAL = [ # reply to potential queries with bot-info
    'source?',
    'sauce?',
]


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

NO_SEARCH_RESULTS_MESSAGE = (
"""No search results found."""
)

INFOREPLY_MESSAGE = (
"""It appears that you are looking for more information.\n\nObtain more information by making a comment in the thread which includes /u/%s""" \
    % REDDIT_ACCOUNT_NAME
)


SUBREDDITS = ['all']

##
## search agent settings
##

SEARCH_USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)
