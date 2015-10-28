# -*- python -*-
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
"""Well that's embarrassing.  Not for me, but for the search engines.

I was not able to automatically find results for this link."""
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


BOTCMD_DELETE_DOWNVOTES_ENABLED = True
BOTCMD_DELETE_DOWNVOTES_AFTER = 30 # only act on comments after X minutes age


COMMENT_REPLY_AGE_LIMIT = 2 # ignore comments older than minutes

REDDIT_SPAMFILTER_SUBMISSION_ID = '2fu04u'


IMAGE_FORMATS = ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png']
VIDEO_FORMATS = ['.gifv', '.mp4', '.webm', '.ogg']
IMAGE_FORMATS += VIDEO_FORMATS


FOOTER_INFO_MESSAGE = (
"""

 ***** 
 ^^[Suggestions](http://www.reddit.com/message/compose/?to=info_bot&subject=Suggestion) ^^| ^^[FAQs](http://www.reddit.com/r/info_bot/comments/2cc45a/info_bot_info/) ^^| ^^[Issues](http://www.reddit.com/message/compose/?to=info_bot&subject=Issue)

 ^^Downvoted ^^comments ^^from ^^info_bot ^^are ^^automagically ^^removed.

 ^(%s %s)
""" % (BOT_NAME, BOT_VERSION)
)


SUBREDDITS = [
    'all',
]
try: # custom external subreddits list
    from config_subreddits import SUBREDDITS
    SUBREDDITS = SUBREDDITS
except ImportError: pass

##
## search agent settings
##

SEARCH_USER_AGENT = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17'
