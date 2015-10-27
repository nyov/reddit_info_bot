# -*- coding: utf-8 -*-
"""
reddit_info_bot
"""
from __future__ import absolute_import, unicode_literals
import sys
import os
import warnings
import logging
import time
import pickle
import re

from . import praw
from .version import __version__, version_info
from .search import image_search
from .reddit import reddit_login, build_subreddit_feeds, find_username_mentions, find_keywords, check_downvotes
from .spamfilter import spamfilter_lists
from .util import chwd

logger = logging.getLogger(__name__)


def main(settings, account1, account2, subreddit_list, comment_stream_urls):
    start_time = time.time()
    comment_deleting_wait_time = settings.getint('COMMENT_DELETIONCHECK_WAIT_LIMIT') #how many minutes to wait before deleting downvoted comments
    find_mentions_enabled = settings.getbool('BOTCMD_IMAGESEARCH_ENABLED')
    find_keywords_enabled = settings.getbool('BOTCMD_INFORMATIONAL_ENABLED')

    already_done = []
    if os.path.isfile("already_done.p"):
        with open("already_done.p", "rb") as f:
            already_done = pickle.load(f)

    logger.info('Starting run...')
    while True:
        try:
            # check inbox messages for username mentions and reply to bot requests
            if find_mentions_enabled:
                logger.info('finding username mentions')
                find_username_mentions(account1, account2, settings, subreddit_list, already_done)

            # scan for potential comments to reply to
            if find_keywords_enabled:
                for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                    logger.info('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
                    feed_comments = stream.get_comments()
                    #feed_comments = stream.get_comments(limit=100)
                    #feed_comments = stream.get_comments(limit=None) # all
                    if not feed_comments:
                        continue
                    find_keywords(feed_comments, account1, settings, subreddit_list, already_done)

                    # back off a second
                    time.sleep(1)

            # check downvoted comments (to delete where necessary)
            if True:
                    start_time = check_downvotes(account1.user, start_time, comment_deleting_wait_time)

            with open("already_done.p", "wb") as df:
                pickle.dump(already_done, df, protocol=2)

            if not find_keywords_enabled:
                # no need to hammer the API, once every minute should suffice in this case
                sleep = 60
                logger.info('Sleeping %d seconds.' % sleep)
                time.sleep(sleep)
            else:
                sleep = 10
                logger.info('Finished visiting all streams. Sleeping %d seconds.' % sleep)
                time.sleep(sleep)

        except praw.errors.ClientException:
            raise
        except praw.errors.OAuthInvalidToken:
            # full re-auth
            logger.info('Access token expired, re-logging.')
            (account1, account2) = reddit_login(settings)
        except praw.errors.PRAWException as e:
            logger.error('Some unspecified PRAW error caught in main loop: %s' % e)


def run(settings={}, **kwargs):
    wd = settings.get('BOT_WORKDIR')
    if wd:
        ok, errmsg = chwd(wd)
        if not ok:
            sys.exit(errmsg)
    else:
        msg = 'No BOT_WORKDIR set, running in current directory.'
        warnings.warn(msg, RuntimeWarning)
        #logger.warning(msg)

    # how the bot handles actions
    ACTMODE_NONE    = 0 # no action
    ACTMODE_LOG     = 1 # log action
    ACTMODE_PM      = 2 # pm/message action
    ACTMODE_COMMENT = 4 # (reddit-) comment action
    ACTMODES = (ACTMODE_LOG | ACTMODE_PM | ACTMODE_COMMENT)

    global ACTMODE # whoops
    ACTMODE = ACTMODE_NONE

    botmodes = settings.getlist('BOT_MODE')
    for botmode in botmodes:
        botmode = botmode.lower()
        if botmode == 'comment':
            ACTMODE |= ACTMODE_COMMENT
        if botmode == 'pm':
            ACTMODE |= ACTMODE_PM
        if botmode == 'log':
            ACTMODE |= ACTMODE_LOG

    # verify modes
    if ACTMODE & ACTMODE_LOG:
        logger.info('log mode enabled')
    if ACTMODE & ACTMODE_PM:
        logger.info('pm mode enabled')
    if ACTMODE & ACTMODE_COMMENT:
        logger.info('comment mode enabled')

    # force early cache-refreshing spamlists
    spamfilter_lists()

    (account1, account2) = reddit_login(settings)

    logger.info('Fetching Subreddit list')
    subreddit_list = set([account1.get_subreddit(i).display_name for i in settings.getlist('SUBREDDITS')])

    logger.info('Fetching comment stream urls')
    #comment_stream_urls = [account1.get_subreddit(subredditlist) for subredditlist in build_subreddit_feeds(subreddit_list)]
    comment_stream_urls = []
    for count, subredditlist in enumerate(build_subreddit_feeds(subreddit_list)):
        logger.info('loading comment stream %2d "%s..."' % (count+1, subredditlist[:60]))
        comment_feed = account1.get_subreddit(subredditlist)
        # lazy objects, nothing done yet
        comment_stream_urls += [comment_feed]

    main(settings, account1, account2, subreddit_list, comment_stream_urls)
