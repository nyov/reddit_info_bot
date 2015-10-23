# -*- coding: utf-8 -*-
"""
reddit_info_bot
"""
from __future__ import (absolute_import, unicode_literals, print_function)
import sys
import os
import logging
import time
import pickle
import re

from . import praw
from .version import __version__, version_info
from .search import image_search
from .reddit import reddit_login, build_subreddit_feeds, find_username_mentions, find_keywords, check_downvotes
from .antispam import spamfilter_lists
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

    print('Starting run...')
    while True:
        try:
            # check inbox messages for username mentions and reply to bot requests
            if find_mentions_enabled:
                print('finding username mentions: ', end='')
                find_username_mentions(account1, account2, settings, subreddit_list, already_done)
                print()

            # scan for potential comments to reply to
            if find_keywords_enabled:
                for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                    print('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
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
                pickle.dump(already_done, df)

            if find_mentions_enabled and not find_keywords_enabled:
                # no need to hammer the API, once every minute should suffice in this case
                print('Checking back in sixty seconds.')
                time.sleep(60)
            else:
                print('Finished a round of comments. Waiting ten seconds.')
                time.sleep(10)

        except praw.errors.ClientException:
            raise
        except praw.errors.OAuthInvalidToken:
            # full re-auth
            print('Access token expired, re-logging.')
            (account1, account2) = reddit_login(settings)
        except praw.errors.PRAWException as e:
            print('\nSome unspecified PRAW error occured in main loop:', e)


def run(settings={}, **kwargs):
    logger.setLevel(settings.get('LOG_LEVEL', 'DEBUG'))

    wd = settings.get('BOT_WORKDIR')
    if wd:
        ok, errmsg = chwd(wd)
        if not ok:
            sys.exit(errmsg)
    else:
        print('No BOT_WORKDIR set, running in current directory.')

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
        print('log mode enabled')
    if ACTMODE & ACTMODE_PM:
        print('pm mode enabled')
    if ACTMODE & ACTMODE_COMMENT:
        print('comment mode enabled')

    # force early cache-refreshing spamlists
    spamfilter_lists()

    (account1, account2) = reddit_login(settings)

    #account1 = account2 = None
    #url = ''
    #print(image_search(url, settings, account1, account2, display_limit=5))
    #sys.exit()

    print('Fetching Subreddit list')
    subreddit_list = set([account1.get_subreddit(i).display_name for i in settings.getlist('SUBREDDITS')])

    print('Fetching comment stream urls')
    #comment_stream_urls = [account1.get_subreddit(subredditlist) for subredditlist in build_subreddit_feeds(subreddit_list)]
    comment_stream_urls = []
    for count, subredditlist in enumerate(build_subreddit_feeds(subreddit_list)):
        print('loading comment stream %2d "%s..."' % (count+1, subredditlist[:60]))
        comment_feed = account1.get_subreddit(subredditlist)
        # lazy objects, nothing done yet
        comment_stream_urls += [comment_feed]

    main(settings, account1, account2, subreddit_list, comment_stream_urls)
