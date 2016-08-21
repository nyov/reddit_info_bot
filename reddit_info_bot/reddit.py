# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import warnings
import time
import requests
import re
import hashlib

from . import praw
from .search import is_media_domain
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

REDDIT_MESSAGE_SIZELIMIT = 10000


# Reddit authentication helpers

def _praw_session(user_agent):
    with warnings.catch_warnings():
        # discard ugly "`bot` in your user_agent may be problematic"-message
        warnings.simplefilter('ignore', UserWarning)
        session = praw.Reddit(user_agent)
    return session

def r_login(user_agent, username, password):
    """authenticate to reddit api using user credentials
    """
    session = _praw_session(user_agent)
    session.login(username, password)
    return session

def r_oauth_login(user_agent, client_id, client_secret,
                  redirect_uri=None, refresh_token=None,
                  username=None, password=None):
    """authenticate to reddit api using oauth
    """
    session = _praw_session(user_agent)
    session.set_oauth_app_info(client_id, client_secret, redirect_uri)
    if not session.has_oauth_app_info:
        raise ConfigurationError('Missing OAuth credentials for Reddit login')
    if refresh_token:
        session.refresh_access_information(refresh_token, update_session=True)
    else:
        access = session.get_bearer_access(username, password)
        session.set_access_credentials(**access)
    return session

def r_logout(session):
    session.clear_authentication()

# Reddit / PRAW functionality

def check_shadowban(user, user_agent):
    """Simple check for a potential shadowban on `user`

    using a non-authenticated connection.
    """
    headers={'User-Agent': user_agent}
    status = requests.get('https://www.reddit.com/user/%s' % user,
                          headers=headers).status_code
    if status == 404:
        return True
    return False

def reddit_login(settings):
    user_agent = settings.get('BOT_AGENT')

    client_id = settings.get('OAUTH_CLIENT_ID')
    client_secret = settings.get('OAUTH_SECRET_TOKEN')
    account_name = settings.get('REDDIT_ACCOUNT_NAME')
    account_pass = settings.get('REDDIT_ACCOUNT_PASS')

    use_oauth = client_id and client_secret
    use_login = account_name and account_pass
    if not use_login:
        raise ConfigurationError('Missing REDDIT_ACCOUNT_NAME setting')
    shadowbanned = check_shadowban(account_name, settings.get('USER_AGENT'))
    if shadowbanned:
        logger.warning("User '%s' may be shadowbanned." % account_name)
    if use_oauth and use_login:
        account1 = r_oauth_login(user_agent, client_id, client_secret,
                                 username=account_name, password=account_pass)
        logger.debug("Logged into account '%s' using OAuth2 (useragent: %s)" % (account1.user, user_agent))
    else:
        account1 = r_login(user_agent, account_name, account_pass)
        logger.debug("Logged into account '%s' using password (useragent: %s)" % (account1.user, user_agent))

    # load a second praw instance for the second account (the one used to check the spam links)
    client2_id = settings.get('SECOND_OAUTH_CLIENT_ID')
    client2_secret = settings.get('SECOND_OAUTH_SECRET_TOKEN')
    account2_name = settings.get('SECOND_ACCOUNT_NAME')
    account2_pass = settings.get('SECOND_ACCOUNT_PASS')

    use_second_oauth = client2_id and client2_secret
    use_second_login = account2_name and account2_pass
    if use_second_login:
        shadowbanned = check_shadowban(account2_name, settings.get('USER_AGENT'))
        if shadowbanned:
            logger.warning('%s may be shadowbanned.' % account2_name)
        if use_second_oauth:
            account2 = r_oauth_login(user_agent, client2_id, client2_secret,
                                    username=account2_name, password=account2_pass)
            logger.debug("Logged into second account '%' using OAuth2" % account2.user)
        else:
            account2 = r_login(user_agent, account2_name, account2_pass)
            logger.debug("Logged into second account '%s' using password" % account2.user)
    else:
        account2 = None

    return (account1, account2)

def reddit_logout(account):
    if not account:
        return
    user = str(account.user)
    r_logout(account)
    logger.debug('Logged out of Reddit API account (%s)' % (user,))
    success = not account.is_logged_in() and not account.is_oauth_session()
    # remove reddit object entirely
    del account
    return success

MAX_URL_LENGTH = 2010

def build_subreddit_feeds(subreddits, max_url_length=MAX_URL_LENGTH):
    """combine subreddits into 'feeds' for requests
    """
    base_length = 35 # length of 'https://reddit.com/r/%s/comments.json'
    url_length = 0
    subredditlist = []
    feed_urls = []
    for subreddit in subreddits:
        url_length += len(subreddit) + 1 # +1 for '+' delimiter
        #logger.debug('%4d %s' % (url_length, subreddit))
        subredditlist += [subreddit]
        if url_length + base_length >= max_url_length:
            feed_urls += ['+'.join(subredditlist)]
            # reset
            subredditlist = []
            url_length = 0
    feed_urls += ['+'.join(subredditlist)]
    # reset
    subredditlist = []
    url_length = 0
    return feed_urls

def reddit_messagefilter(messages, sending_account, receiving_account, submission_id):
    """Post reddit comments with `sending_account` to `submission_id`
    and check from `receiving_account` to verify they were not filtered out.
    """

    def is_hashed_message(text):
        hash = text[1:33] # the added md5
        found, = re.findall(r'([a-fA-F\d]{32})', hash) or [False]
        return found

    def build_message_posts(messages):
        message_queue = {}
        for message in messages:
            # use a unique id in the message so we'll always recognize it
            # (even if the text got mangled, e.g. unicode or other strangeness)
            # using a hashsum of message helps to reduce posting duplicate content
            id = hashlib.md5(message.encode('utf-8', 'strict')).hexdigest()
            if id not in message_queue:
                hashed = '[%s] %s' % (id, message)
                message_queue.update({id: (message, hashed)})
        return message_queue

    def submit_messages(message_queue):
        # post with sending_account

        submission = sending_account.get_submission(submission_id=submission_id)
        count = all = 0
        for id, (message, hashed) in message_queue.items():
            all += 1
            try:
                submission.add_comment(hashed)
            except Exception as e:
                logger.warning('reddit_messagefilter failed to post "%s"\n%s' % (hashed, e))
                message_queue.pop(id, None)
                continue
            count += 1
        logger.debug('%d of %d message(s) posted' % (count, all))

    def fetch_posted_messages(refresh=False):
        #try:
        #    submission = receiving_account.get_submission(
        #            submission_id=submission_id, comment_sort='new')
        #except praw.errors.Forbidden:
        #    # it does not seem to matter if we check with the posting account
        #    submission = sending_account.get_submission(
        #            submission_id=submission_id, comment_sort='new')

        #if isinstance(submission, praw.objects.Moderatable):
        #    pass # have mod access, will also see banned comments/messages

        submission = sending_account.get_submission(submission_id=submission_id, comment_sort='new')

        if refresh: # drop a previous lookup from PRAW's cache
            submission.refresh()

        messages = submission.comments
        return list(messages)

    def fetch_inbox_messages():
        # fetch posts on receiving_account
        # works only for the creator of `submission_id` thread
        messages = receiving_account.get_messages(limit=200)
        messages = [m for m in messages if is_hashed_message(m.body)]
        return messages

    def check_messages(message_queue, messages):
        fetched_messages = []
        for message in messages:
            if not isinstance(message, (praw.objects.Comment, praw.objects.Message)):
                continue
            id = is_hashed_message(message.body)
            if not id:
                continue

            # mark any new messages as read (so they dont bother us elsewhere)
            if isinstance(message, praw.objects.Message):
                message.mark_as_read()

            if id not in message_queue:
                continue

            # if we have mod status, we should see the banned messages,
            # and can drop them from queue (confirmed positive)
            if isinstance(message, praw.objects.Comment) and message.banned_by:
                message_queue.pop(id)
                if isinstance(message.banned_by, praw.objects.Redditor):
                    # banned by mod / bot
                    banned_by = message.banned_by
                else:
                    # met by reddit banhammer
                    banned_by = 'reddit'
                logger.info('...message banned by %s: %s' % (banned_by, message.body))
                continue

            msg, _ = message_queue.pop(id)
            fetched_messages += [msg]
        return fetched_messages

    verified_messages = []
    message_queue = build_message_posts(messages)
    logger.info('reddit_messagefilter spam-checking %d messages' % len(message_queue))

    # check whats already there (in case we run a search twice)
    fetched_messages = fetch_posted_messages()
    verified_messages += check_messages(message_queue, fetched_messages)

    if message_queue:
        logger.debug('reddit_messagefilter posting %d messages to %s' % (len(message_queue), submission_id))
        submit_messages(message_queue)
        time.sleep(7) # wait a bit

        # check again
        #fetched_messages = fetch_inbox_messages()
        #if len(fetched_messages) == 0: # are we checking from a different account (not our inbox)?
        #    # check submission thread instead
        #    fetched_messages = fetch_posted_messages(refresh=True)
        fetched_messages = fetch_posted_messages(refresh=True)
        verified_messages += check_messages(message_queue, fetched_messages)

    verified_messages = set(verified_messages)
    logger.info('reddit_messagefilter verified %d message(s) as good' % len(verified_messages))

    if message_queue:
        _filtered = ', '.join([m for (h, (o, m)) in message_queue.items()])
        logger.info('reddit_messagefilter filtered out: %s' % _filtered)

    return verified_messages

def reddit_markdown_escape(string):
    if not isinstance(string, (str, unicode)):
        return string
    # escape markdown characters
    # from https://daringfireball.net/projects/markdown/syntax#backslash
    # \   backslash
    # `   backtick
    # *   asterisk
    # _   underscore
    # {}  curly braces
    # []  square brackets
    # ()  parentheses
    # #   hash mark
    # +   plus sign
    # -   minus sign (hyphen)
    # .   dot
    # !   exclamation mark
    markdown_chars = r'\`*_{}[]()#+-.!'
    reddit_chars = r'^~<>'
    escape_chars = markdown_chars + reddit_chars
    string = ''.join(c if c not in escape_chars else '\%s' % c for c in string)
    return string


#
# Bot actions
#

def check_downvotes(settings, user):
    deletion_wait_time = settings.getint('BOTCMD_DOWNVOTES_DELETE_AFTER', 1) * 60 # in minutes
    deletion_comment_score = settings.getint('BOTCMD_DOWNVOTES_DELETION_SCORE', 1)
    deletion_testmode = settings.getbool('BOTCMD_DOWNVOTES_TESTMODE', False)

    my_comments = user.get_comments(limit=100)
    for comment in my_comments:
        # check comment age, skip if not old enough
        if comment.created_utc < deletion_wait_time:
            continue
        if comment.score < deletion_comment_score:
            if deletion_testmode:
                logger.warning('would have deleted comment %s (score: %s)' %
                        (comment.permalink, comment.score))
                continue
            logger.info('deleting comment %s' % (comment.permalink,))
            comment.delete()

def _any_from_list_in_string(list_, string_):
    list_ = [str(s).lower() for s in list_]
    string_ = str(string_).lower()
    #return any(s in string_ for s in list_)
    return [s for s in list_ if s in string_]

def _any_from_list_end_string(list_, string_):
    list_ = [str(s).lower() for s in list_]
    string_ = str(string_).lower()
    return [s for s in list_ if string_.endswith(s)]

def _applicable_comment(comment, settings, account, comments_seen, subreddit_list, search_list, information_reply):
    time_limit_minutes = settings.getint('COMMENT_REPLY_AGE_LIMIT')
    media_extensions = ['.%s' % e.strip('.') for e in settings.getlist('MEDIA_EXTENSIONS')]
    footer_message = settings.get('FOOTER_INFO_MESSAGE')

    def done(): # put in database and abort processing
        comments_seen.append(comment.id)
        return False

    if comment.id in comments_seen:
        #logger.debug('[D] comment %s already logged as done' % comment.id)
        return False

    if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
        logger.debug('[!] %s - comment\'s subreddit is not in our list [%s]' % (comment.id, comment.permalink))
        return done()

    comment_time_diff = (time.time() - comment.created_utc)
    if comment_time_diff / 60 > time_limit_minutes:
        logger.debug('[O] %s - comment has been created %d minutes ago, our reply-limit is %d [%s]' \
                     % (comment.id, comment_time_diff / 60, time_limit_minutes, comment.permalink))
        return done()

    is_media = _any_from_list_end_string(media_extensions, comment.submission.url)
    if not is_media:
        if not hasattr(comment.submission, 'post_hint'): # 'post_hint' attribute only exists on media posts
            # not a media-url, UNLESS we see a special domain here which we know has only media
            if not is_media_domain(comment.submission.url):
                logger.debug('[T] %s - comment submission has no image [%s]' % (comment.id, comment.permalink))
                return done()
        elif comment.submission.post_hint == 'rich:video':
            pass
            # TODO: dont really have an image here to search for yet, might fail
            #comment.submission.url = comment.submission.preview.images.source.url
        elif comment.submission.post_hint == 'image':
            pass
        else:
            logger.debug('[T] %s - comment submission has no image [%s]' % (comment.id, comment.permalink))
            return done()

    comment_body = comment.body.encode('utf-8')
    keywords = _any_from_list_in_string(search_list, comment_body)
    if not keywords:
        logger.debug('[P] %s - comment has no keyword [%s]' % (comment.id, comment.permalink))
        return done()

    # found a keyword
    if not comment.author:
        logger.debug('[X] %s - comment has no author / does not exist [%s]' % (comment.id, comment.permalink))
        return done()

    top_level = [c.replies for c in comment.submission.comments] # FIXME: do we need this?
    submission_comments = []
    for i in top_level:
        for j in i:
            submission_comments.append(j)

    if any(i for i in submission_comments if footer_message in i.body): # already replied? FIXME: wont match if our FOOTER_MESSAGE changed!
        logger.debug('[R] %s - comment has our footer message (ours) [%s]' % (comment.id, comment.permalink))
        return done()
    if any(i for i in submission_comments if information_reply in i.body): # already replied? (this applies only to `find_keywords` method)
        logger.debug('[R] %s - comment has our info message (ours) [%s]' % (comment.id, comment.permalink))
        return done()
    if comment.author == account.user: # ooh, that's us!? we lost our memory?
        logger.debug('[U] %s - comment author is us (ours) [%s]' % (comment.id, comment.permalink))
        return done()

    return keywords # good

def _comment_reply(comment, reply_func, reply_content):
    if not callable(reply_func):
        return # error

    attempt = 0
    while True:
        if attempt >= 3: # max retries: 3
            logger.info('Max failure count reached. Could not reply to comment {0} ({1})'.format(comment.permalink, comment.body))
            return
            #return ('error', 'max retries reached')
        attempt += 1
        try:
            return reply_func(comment, reply_content)
        except praw.errors.RateLimitExceeded as e:
            errmsg = str(e)
            backoff, min_secs = re.search(r'try again in ([0-9]+) (minutes?|seconds?)', errmsg).groups()
            if 'second' in min_secs:
                backoff = int(backoff)
            elif 'minute' in min_secs:
                backoff = int(backoff) * 60
            backoff += 9 # grace (for timing differences with reddit)
            logger.warning('Ratelimit hit. Backing off %d seconds! (%s)' % (backoff, e))
            time.sleep(backoff)
        # the following are permanent errors, no retry
        except praw.errors.InvalidComment:
            logger.warning('[F] %s - comment invalid (was deleted while trying to reply?) [%s]', (comment.id, comment.permalink))
            # dont need to store this, since it's gone(?)
            #comments_seen.append(comment.id)
            return
        except praw.errors.Forbidden as e:
            logger.warning('[F] %s - cannot reply to comment %s. Bot forbidden from this sub: %s' % (comment.permalink, comment.submission, e))
            comments_seen.append(comment.id)
            return
        except praw.errors.PRAWException as e:
            logger.error('Some unspecified PRAW issue occured while trying to reply: %s' % e)
            return # done for now but don't save state and retry later

def handle_bot_action(comments, settings, account, account2, subreddit_list, comments_seen, action):
    from .commands import cmd_imagesearch
    botmodes = settings.getlist('BOT_MODE', ['log'])

    # find_username_mentions
    def find_username_mentions(comment, reply_content): # reply_func
        if 'log' in botmodes:
            logger.warning('find_username_mentions would post:\n%s' % reply_content)
        if 'comment' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        elif 'pm' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        return True

    # find_keywords
    def find_keywords(comment, reply_content): # reply_func
        if 'log' in botmodes:
            logger.warning('find_keywords would post:\n%s' % reply_content)
        if 'comment' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        if 'pm' in botmodes:
            whatever = account.send_message(comment.author, 'Info Bot Information', reply_content)
            logger.info(whatever)
        return True

    if action == 'find_username_mentions':
        search_list = settings.getlist('BOTCMD_IMAGESEARCH')
        reply_func = find_username_mentions
        # Only handle 'username mention's, ignore any messages that are direct PMs (praw.objects.Message)
        comments = [c for c in comments if isinstance(c, praw.objects.Comment)]
    elif action == 'find_keywords':
        search_list = settings.getlist('BOTCMD_INFORMATIONAL')
        reply_func = find_keywords
    else:
        return
    information_reply = settings.get('BOTCMD_INFORMATIONAL_REPLY')

    if not search_list:
        return

    count = 0
    for comment in comments:
        count += 1
        comment_body = comment.body.encode('utf-8')
        keywords = _applicable_comment(comment, settings, account, comments_seen, subreddit_list, search_list, information_reply)
        if not keywords:
            continue
        logger.info('[N] Detected keyword(s) %s in %s' % (', '.join(keywords), comment.permalink))

        if action == 'find_username_mentions':
            reply_content = cmd_imagesearch(settings, image_url=comment.submission.url,
                                            account1=account, account2=account2)
            if not reply_content:
                logger.error('cmd_imagesearch failed! skipping')
                continue # try that again, don't mark as done yet
        if action == 'find_keywords':
            reply_content = information_reply

        done = _comment_reply(comment, reply_func, reply_content)
        if done:
            # do not mark as 'done' in test-mode
            if 'comment' in botmodes or 'pm' in botmodes:
                comments_seen.append(comment.id)
            logger.info('replied to comment {0} ({1})'.format(comment.permalink, comment.body))

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #logger.info('(%d comments - %s)' % (count, se))
    logger.info('(%d comments scanned)' % (count,))
