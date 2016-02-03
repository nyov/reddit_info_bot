# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import warnings
import time
import uuid
import requests
import re

from . import praw
from .search import image_search, filter_image_search, format_image_search
from .util import domain_suffix
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


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
    shadowbanned = check_shadowban(account_name, settings.get('SEARCH_USER_AGENT'))
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
        shadowbanned = check_shadowban(account2_name, settings.get('SEARCH_USER_AGENT'))
        if shadowbanned:
            logger.warning('%s may be shadowbanned.' % account2_name)
        if use_second_oauth:
            account2 = r_oauth_login(user_agent, client2_id, client2_secret,
                                    username=account2_name, password=account2_pass)
            logger.debug('Logged in second account using OAuth2')
        else:
            account2 = r_login(user_agent, account2_name, account2_pass)
            logger.debug('Logged in second account using password')
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

def reddit_msg_linkfilter(messages, sending_account, receiving_account, submission_id):
    """ Post reddit comments with one account and check from second account
    to see if they were filtered out.
    """
    queue = {}
    submission = sending_account.get_submission(submission_id=submission_id)
    # post with first account
    logger.info('reddit_msg_linkfilter posting messages')
    count = 0
    for message in messages:
        # use a unique id in the message so we'll always recognize it
        # (even if the text got mangled, e.g. unicode or other strangeness)
        id = uuid.uuid4()
        try:
            _message = '[%s] %s' % (id, message)
            submission.add_comment(_message)
        except Exception as e:
            logger.error('reddit_msg_linkfilter failed to post "%s"\n%s' % (message, e))
            # FIXME: check exception for http errors (retry?) or other (spam?)
            continue
        queue.update({id: message})
        count += 1
    logger.info('%d message(s) posted' % count)

    time.sleep(7) # wait a bit

    # fetch posts on second account
    logger.info('reddit_msg_linkfilter verifying messages')
    verified_messages = []
    fetched_messages = list(receiving_account.get_unread(limit=40))
    count = 0
    for msg in fetched_messages:
        msg_body = msg.body # is unicode
        if not msg_body.startswith('['):
            # skip unknown messages
            #logger.debug('(skipping unknown message "%s...") ' % msg_body[:10], end='')
            continue
        for id in queue.keys():
            if str(id) not in msg_body:
                continue
            message = queue.pop(id)
            #if message != msg_body.replace('[%s] ' % id, ''):
            #    logger.debug('(message got mangled?)')
            msg.mark_as_read()
            verified_messages += [message]
            count += 1
    logger.info('%d unread message(s) fetched, %d verified, %d unknown(s)' % (len(fetched_messages)-1, count, len(fetched_messages)-1-count))
    if queue: # shouldnt have any messages left at this point
        logger.info('reddit_msg_linkfilter filtered out: %s' % ', '.join('"%s"' % x for x in queue.values()))
    failed_messages = [m for m in messages if (m not in verified_messages and m not in queue.values())]
    if failed_messages:
        logger.error('reddit_msg_linkfilter completely failed on: %s' % str(failed_messages))
    return verified_messages

def reddit_spamfilter(results, sending_account, receiving_account, submission_id):
    urls = set([url for url, text in results])
    verified_urls = reddit_msg_linkfilter(urls, sending_account, receiving_account, submission_id)
    verified_results = []
    for result in results:
        url = result[0]
        if url in verified_urls:
            verified_results.append(result)
    return verified_results

def reddit_format_results(results, escape_chars=True):
    """Format search results for reddit.

    Returns a markdown-formatted and spam-filtered list of the results.
    """
    def escape_markdown(string):
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

    if escape_chars:
        results = [[escape_markdown(v) for v in result]
                   for result in results]

    # format output
    markdown_links = ['[%s](%s)' % (text, url) for url, text in results]
    formatted = '\n\n'.join(markdown_links)
    return formatted


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
                logger.warning('would have deleted comment %s (score: %s): %s' %
                        (comment.id, comment.score, comment.title))
                continue
            logger.info('deleting comment %s: %s' % (comment.id, comment.title))
            comment.delete()

def _any_from_list_in_string(list_, string_):
    string_ = str(string_).lower()
    #return any(str(w).lower() in string_ for w in list_)
    return [str(w).lower() for w in list_ if str(w).lower() in string_]

def _applicable_comment(comment, settings, account, already_done, subreddit_list, search_list, information_reply):
    time_limit_minutes = settings.getint('COMMENT_REPLY_AGE_LIMIT')
    image_formats = settings.getlist('IMAGE_FORMATS')
    footer_message = settings.get('FOOTER_INFO_MESSAGE')

    def done(): # put in database and abort processing
        already_done.append(comment.id)
        return False

    if comment.id in already_done:
        #logger.debug('[D] comment %s already logged as done [%s]' % (comment.id, comment.permalink))
        return False
    if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
        logger.debug('[!] %s - comment\'s subreddit is not in our list [%s]' % (comment.id, comment.permalink))
        return done()
    comment_time_diff = (time.time() - comment.created_utc)
    if comment_time_diff / 60 > time_limit_minutes:
        logger.debug('[O] %s - comment has been created %d minutes ago, our reply-limit is %d [%s]' \
                     % (comment.id, comment_time_diff / 60, time_limit_minutes, comment.permalink))
        return done()
    is_image = _any_from_list_in_string(image_formats, comment.submission.url)
    if not is_image:
        # not relevant; unless we see an imgur/gfycat domain (those are always images)
        domain = domain_suffix(comment.submission.url)
        if domain not in ('imgur.com', 'gfycat.com'):
            logger.debug('[T] %s - comment has no picture [%s]' % (comment.id, comment.permalink))
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
        if attempt >= 2: # max retries: 2
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
            backoff += 3 # grace
            logger.warning('Ratelimit hit. Backing off %d seconds! (%s)' % (backoff, e))
            time.sleep(backoff)
        # the following are permanent errors, no retry
        except praw.errors.InvalidComment:
            logger.warning('[F] %s - comment invalid (was deleted while trying to reply?) [%s]', (comment.id, comment.permalink))
            # dont need to store this, since it's gone(?)
            #already_done.append(comment.id)
            return
        except praw.errors.Forbidden as e:
            logger.warning('[F] %s - cannot reply to comment. Bot forbidden from this sub: %s' % (comment.id, e)) # FIXME: add SUB
            already_done.append(comment.id)
            return
        except praw.errors.PRAWException as e:
            logger.error('Some unspecified PRAW issue occured while trying to reply: %s' % e)
            return # done for now but don't save state and retry later

def handle_bot_action(comments, settings, account, account2, subreddit_list, already_done, action):
    botmodes = settings.getlist('BOT_MODE', ['log'])

    # find_username_mentions
    def find_username_mentions(comment, reply_content): # reply_func
        if 'log' in botmodes:
            logger.warning(reply_content)
        if 'comment' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        elif 'pm' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        return

    # find_keywords
    def find_keywords(comment, reply_content): # reply_func
        if 'log' in botmodes:
            logger.warning(reply_content)
        if 'comment' in botmodes:
            comment.reply(reply_content)
            comment.mark_as_read()
        if 'pm' in botmodes:
            whatever = account.send_message(comment.author, 'Info Bot Information', reply_content)
            logger.info(whatever)
        return

    if action == 'find_username_mentions':
        search_list = settings.getlist('BOTCMD_IMAGESEARCH')
        reply_func = find_username_mentions
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
        keywords = _applicable_comment(comment, settings, account, already_done, subreddit_list, search_list, information_reply)
        if not keywords:
            continue
        logger.info('[N] Detected keyword/s %s in %s' % (', '.join(keywords), comment.id))

        if action == 'find_username_mentions':
            try:
                display_limit = 5
                search_results = image_search(settings, comment.submission.url)
                filter_results = filter_image_search(settings, search_results, account, account2)
                reply_content = format_image_search(settings, filter_results, display_limit)
                if not reply_content:
                    logger.error('image_search failed (bug)! skipping')
                    # try that again, instead of replying with no results
                    continue
            except Exception as e:
                logger.error('Error occured in image_search: %s' % e)
                continue
        if action == 'find_keywords':
            reply_content = information_reply

        _comment_reply(comment, reply_func, reply_content)
        # do not mark as 'done' in test-mode
        if 'comment' in botmodes or 'pm' in botmodes:
            already_done.append(comment.id)
        logger.info('replied to comment {0}: {1}'.format(comment.id, comment.body))

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #logger.info('(%d comments - %s)' % (count, se))
    logger.info('(%d comments scanned)' % (count,))
