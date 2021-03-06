"""
reddit_info_bot bot commands

"""
from __future__ import absolute_import, unicode_literals
import sys, os
import warnings
import logging
import time
import datetime
import pickle
import pprint
from functools import wraps

from .version import __version__, version_info
from . import praw
from .reddit import (
    reddit_login, reddit_logout,
    build_subreddit_feeds, handle_bot_action, check_downvotes,
)
from .spamfilter import populate_spamfilter_lists
from .log import setup_logging, release_logging
from .util import chwd, cached_psl, daemon_context
from .signals import signal_map, running
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def bot_commands():
    """List of registered bot commands"""
    cmds = {
        'run': with_setup(cmd_run),
        'imagesearch': with_setup(cmd_imagesearch),
        'wordcloud': cmd_wordcloud,
        'exit': do_exit,
    }
    return cmds

def do_exit(settings):
    """Deallocation (atexit)

    Last second clean up.
    This is always called on clean Python interpreter shutdown.
    """
    # close open files
    open_file_handles = settings.getdict('_FILE_')
    for fh in open_file_handles.values():
        fh.__exit__(None, None, None)

def do_setup(settings, command=None, *a, **kw):
    """Bot environment setup and shutdown
    """
    startup_time = time.time()

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

    sys.stdout.write('%s starting up at %s\n' % (
                     settings.get('_BOT_INSTANCE_'),
                     time.ctime(startup_time)))

    # open files
    open_file_handles = {}
    for file, filename in open_files.items():
        if os.path.exists(filename):
            open_file_handles[file] = open(filename, 'rb+').__enter__()
        else:
            open_file_handles[file] = open(filename, 'wb').__enter__()
    settings.set('_FILE_', open_file_handles) # (runtime setting)

    # configure logging
    log_handler = setup_logging(settings)

    files_preserve = open_file_handles.values()
    files_preserve.append(log_handler.stream)
    with daemon_context(settings, files_preserve=files_preserve, signal_map=signal_map):
        logger.info('%s started' % settings.get('_BOT_INSTANCE_'))

        # force early cache-refreshing spamlists
        populate_spamfilter_lists(settings.get('_CACHEDIR_'))
        # cache-load psl
        cached_psl(settings.getdict('_FILE_')['pubsuflist'])

        if callable(command):
            command(settings, *a, **kw)

        logger.info('%s shutting down' % settings.get('_BOT_INSTANCE_'))
        release_logging(log_handler)

        shutdown_time = time.time()
        uptime = datetime.datetime.fromtimestamp(shutdown_time) - datetime.datetime.fromtimestamp(startup_time)
        format_uptime = uptime.__str__()
        sys.stdout.write('%s shut down on %s [uptime: %s]\n' % (
                         settings.get('_BOT_INSTANCE_'),
                         time.ctime(shutdown_time),
                         format_uptime))

def with_setup(command):
    """setup decorator"""
    @wraps(command)
    def wrapped(settings, *args, **kwargs):
        return do_setup(settings, command, *args, **kwargs)
    return wrapped

#
# main routines
#

def cmd_run(settings):

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

    # load cached comments-done-list
    comments_seen_fh = settings.getdict('_FILE_')['comments_seen']
    try:
        comments_seen_fh.seek(0)
        comments_seen = pickle.load(comments_seen_fh) or []
    except Exception:
        comments_seen = []

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

    last_downvote_check = 0

    logger.info('Starting run...')
    while running():
        try:
            sleep_timer = 60

            # check inbox messages for username mentions and reply to bot requests
            if settings.getbool('BOTCMD_IMAGESEARCH_ENABLED'):
                logger.info('finding username mentions')
                messages = account1.get_unread(limit=100)
                if messages:
                    handle_bot_action(messages, settings, account1, account2, subreddit_list, comments_seen, 'find_username_mentions')

            if settings.getbool('BOTCMD_INFORMATIONAL_ENABLED'):
                sleep_timer = 10
                for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                    logger.info('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
                    stream_comments = stream.get_comments()
                    #stream_comments = stream.get_comments(limit=100)
                    #stream_comments = stream.get_comments(limit=None) # all
                    if stream_comments:

                        # scan for potential comments to reply to
                        handle_bot_action(stream_comments, settings, account1, None, subreddit_list, comments_seen, 'find_keywords')

            # check downvoted comments (to delete where necessary)
            if settings.getbool('BOTCMD_DOWNVOTES_ENABLED'):
                now = time.time()
                # only check once every X seconds
                if now - last_downvote_check >= 300:
                    logger.info('checking downvotes')
                    last_downvote_check = now
                    check_downvotes(settings, account1.user)

            comments_seen_fh.seek(0)
            pickle.dump(comments_seen, comments_seen_fh, protocol=2)
            comments_seen_fh.truncate()
            comments_seen_fh.flush()

            logger.info('Sleeping %d seconds.' % sleep_timer)
            time.sleep(sleep_timer)

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

def cmd_imagesearch(settings, image_url=None, image_data=None, image_ext='jpg',
                    from_cli=False, **kwargs):
    from .search import (image_search, filter_image_search, format_image_search,
                         filter_wordcloud_text)
    from .imgur import image_upload, imgur_login

    if not image_url and not image_data:
        logger.error('Missing source for image search')
        return

    display_limit = settings.getint('BOTCMD_IMAGESEARCH_MAXRESULTS_FOR_ENGINE', 15)
    wordcloud = settings.getbool('BOTCMD_WORDCLOUD_ENABLED', not from_cli)

    search_results = image_search(settings,
            image_url=image_url, image_data=image_data, num_results=display_limit,
            image_ext=image_ext,
        )

    if wordcloud:
        text = filter_wordcloud_text(settings, search_results)
        if text:
            logger.info('Generating wordcloud for results.')
            filename = "%swordcloud.png" % settings.get('_CACHEDIR_')
            wordcloud_image = cmd_wordcloud(settings, text, from_cli=from_cli, filename=filename)
            if not wordcloud_image: # not uploading when run from CLI (dumped to file)
                wordcloud = False
                logger.info('Wordcloud was written to "%s"' % filename)
        else:
            wordcloud = False
            logger.info('No text to build wordcloud, skipping.')

    filter_results = filter_image_search(settings, search_results,
            account1=kwargs.get('account1'), account2=kwargs.get('account2'),
            display_limit=display_limit,
        )

    imgur_link = None
    if wordcloud and wordcloud_image:
        logger.info('Uploading wordcloud to Imgur.')
        client = imgur_login(settings)
        config = {}
        album = settings.get('IMGUR_ALBUM_ID')
        if album:
            config.update({'album': album})
        idata = image_upload(client, wordcloud_image, config)
        imgur_link = idata['link']
        #imgur_hash = idata['deletehash']
        # log metadata including the deletehash
        logger.info('...Imgur link: %s -- Metadata:\n%s' % (imgur_link, pprint.pformat(idata)))

    reply_contents = format_image_search(settings, filter_results,
            escape_chars=not from_cli, metainfo={'wordcloud':imgur_link})

    if from_cli: # being called directly, dump output to terminal
        logger.info('Image-search results:\n%s' % reply_contents)
        return
    return reply_contents

def cmd_wordcloud(settings, text, from_cli=False, filename=None, **kwargs):
    from .wcloud import wordcloud_image

    config = settings.getdict('BOTCMD_WORDCLOUD_CONFIG')
    kwargs.update(config) # kwargs options override settings from config
    if 'stopwords' not in kwargs:
        from .wcloud import stopwords
        stopwords |= set(settings.getlist('BOTCMD_WORDCLOUD_STOPWORDS'))
        kwargs.update({'stopwords':stopwords})
    image, imgsize = wordcloud_image(text, **kwargs)

    if not from_cli:
        return image

    if filename:
        with open(filename, 'wb') as of:
            image.seek(0)
            of.write(image.read())
        image.close()
