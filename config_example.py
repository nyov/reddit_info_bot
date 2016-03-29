# -*- mode: python; coding: utf-8; -*-
"""
reddit_info_bot settings

For a list of all configuration options, see default_settings.py
"""
from reddit_info_bot import __version__ as BOT_VERSION

##
## program settings
##

BOT_NAME = 'reddit_info_bot'
BOT_WORKDIR = '/tmp/redditbot'
BOT_CACHEDIR = 'cache'

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


BOT_MODE = ['comment']

# bot commands
BOTCMD_IMAGESEARCH_ENABLED = True
BOTCMD_IMAGESEARCH = [ # (main) initiate image search
    'u/%s' % REDDIT_ACCOUNT_NAME,
]
BOTCMD_IMAGESEARCH_NO_RESULTS_MESSAGE = (
"""No search results found."""
)


BOTCMD_INFORMATIONAL_ENABLED = True
BOTCMD_INFORMATIONAL = [ # reply to potential queries with bot-info
    'source?',
    'sauce?',
]
BOTCMD_INFORMATIONAL_REPLY = (
"""It appears that you are looking for more information.

Obtain more information by making a comment in the thread which includes /u/%s""" % BOT_NAME
)


BOTCMD_DOWNVOTES_ENABLED = True
BOTCMD_DOWNVOTES_TESTMODE = True # if enabled, only log action
BOTCMD_DOWNVOTES_DELETE_AFTER = 30 # only act on comments after X minutes age
BOTCMD_DOWNVOTES_DELETION_SCORE = 1 # karma score below which a comment is removed


COMMENT_REPLY_AGE_LIMIT = 2 # ignore comments older than minutes

REDDIT_SPAMFILTER_SUBMISSION_ID = '2fu04u'


FOOTER_INFO_MESSAGE = (
"""

 *****
 ^(%s %s)
""" % (BOT_NAME, BOT_VERSION)
)


SUBREDDITS = ['all']

##
## search / scrapy spider settings
##

USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)
