"""
reddit_info_bot bot commands

"""
from __future__ import absolute_import, unicode_literals
import sys, os
import warnings
import logging
import time
import pickle

from .version import __version__, version_info
from . import praw
from .reddit import (
    reddit_login, reddit_logout,
    build_subreddit_feeds, handle_bot_action, check_downvotes,
)
from .spamfilter import spamfilter_lists
from .log import setup_logging
from .util import chwd, cached_psl, daemon_context
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def bot_commands():
    """List of registered bot commands"""
    cmds = {
        'run': cmd_run,
        'shutdown': cmd_shutdown,
    }
    return cmds

def cmd_shutdown(settings):
    """Shutdown sequence
    """
    # close open files
    open_file_handles = settings.getdict('_FILE_')
    for fh in open_file_handles.values():
        fh.__exit__(None, None, None)

def cmd_run(settings):
    """Main routine
    """
    # setup

    workdir = settings.get('BOT_WORKDIR')
    if workdir:
        ok, errmsg = chwd(workdir)
        if not ok:
            sys.exit(errmsg)
    else:
        msg = 'No BOT_WORKDIR set, running in current directory.'
        warnings.warn(msg, RuntimeWarning)
    del workdir

    cachedir = settings.get('BOT_CACHEDIR', '')
    # relative to workdir, or absolute path
    # (will be workdir if not provided)
    if cachedir:
        cachedir = os.path.abspath(cachedir)
        if not os.path.isdir(cachedir):
            raise ConfigurationError('BOT_CACHEDIR was set, '
                                     'but is not a directory (%s)'
                                     % cachedir)
        cachedir = cachedir.rstrip('/') + '/'
    settings.set('_CACHEDIR_', cachedir) # (runtime setting)

    open_files = {
        'comments_seen': cachedir + 'comments_seen.cache',
        #'spamfilter': cachedir + 'spamfilter.cache',
        'pubsuflist': cachedir + 'public_suffix_list.dat',
    }
    del cachedir

    # startup
    #
    # Environment is set up at this point,
    # now open files and daemonize.

    sys.stdout.write('%s starting\n' % settings.get('_BOT_INSTANCE_', 'reddit_info_bot'))

    # open files
    open_file_handles = {}
    for file, filename in open_files.items():
        open_file_handles[file] = open(filename, 'ab+').__enter__()
    settings.set('_FILE_', open_file_handles) # (runtime setting)

    log_fh = setup_logging(settings)

    files_preserve = open_file_handles.values()
    files_preserve.append(log_fh)
    with daemon_context(settings, files_preserve=files_preserve):
        cmd_running(settings)

def cmd_running(settings):

    logger.info('%s started\n' % settings.get('_BOT_INSTANCE_', 'reddit_info_bot'))

    # verify modes
    botmodes = settings.getlist('BOT_MODE', ['log'])
    botmodes = [m.lower() for m in botmodes]
    settings.set('BOT_MODE', botmodes)

    if 'comment' in botmodes: # (reddit-) comment action
        logger.info('comment mode enabled')
    if 'pm' in botmodes: # pm/message action
        logger.info('pm mode enabled')
    if 'log' in botmodes: # log action
        logger.info('log mode enabled')

    # force early cache-refreshing spamlists
    spamfilter_lists(settings.get('_CACHEDIR_'))
    # cache-load psl
    cached_psl(settings.getdict('_FILE_')['pubsuflist'])
    # load cached comments-done-list
    comments_seen_fh = settings.getdict('_FILE_')['comments_seen']
    try:
        comments_seen_fh.seek(0)
        already_done = pickle.load(comments_seen_fh) or []
        comments_seen_fh.seek(0)
    except Exception:
        already_done = []

    logger.info('Logging into Reddit API')
    (account1, account2) = reddit_login(settings)

    logger.info('Fetching Subreddit list')
    subreddit_list = set(account1.get_subreddit(i).display_name for i in settings.getlist('SUBREDDITS'))

    logger.info('Fetching comment stream urls')
    #comment_stream_urls = [account1.get_subreddit(subredditlist) for subredditlist in build_subreddit_feeds(subreddit_list)]
    comment_stream_urls = []
    for count, subredditlist in enumerate(build_subreddit_feeds(subreddit_list)):
        logger.info('loading comment stream %2d "%s..."' % (count+1, subredditlist[:60]))
        comment_feed = account1.get_subreddit(subredditlist)
        # lazy objects, nothing done yet
        comment_stream_urls += [comment_feed]

    #
    # main loop
    #

    start_time = time.time()
    find_mentions_enabled = settings.getbool('BOTCMD_IMAGESEARCH_ENABLED')
    find_keywords_enabled = settings.getbool('BOTCMD_INFORMATIONAL_ENABLED')
    delete_downvotes_enabled = settings.getbool('BOTCMD_DELETE_DOWNVOTES_ENABLED')
    delete_downvotes_after = settings.getint('BOTCMD_DELETE_DOWNVOTES_AFTER')

    logger.info('Starting run...')
    while True:
        try:
            # check inbox messages for username mentions and reply to bot requests
            if find_mentions_enabled:
                logger.info('finding username mentions')
                messages = account1.get_unread(limit=100)
                if messages:
                    handle_bot_action(messages, settings, account1, account2, subreddit_list, already_done, 'find_username_mentions')

            # scan for potential comments to reply to
            if find_keywords_enabled:
                for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                    logger.info('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
                    feed_comments = stream.get_comments()
                    #feed_comments = stream.get_comments(limit=100)
                    #feed_comments = stream.get_comments(limit=None) # all
                    if feed_comments:
                        handle_bot_action(feed_comments, settings, account1, None, subreddit_list, already_done, 'find_keywords')

                        # back off a second
                        time.sleep(1)

            # check downvoted comments (to delete where necessary)
            if delete_downvotes_enabled:
                    start_time = check_downvotes(account1.user, start_time, delete_downvotes_after, settings)

            comments_seen_fh.seek(0)
            pickle.dump(already_done, comments_seen_fh, protocol=2)

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

    #
    # shutdown
    #

    logger.info('Logging out of Reddit API')
    reddit_logout(account2)
    reddit_logout(account1)
