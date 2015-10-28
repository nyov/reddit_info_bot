# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import warnings
import time
import uuid
import requests

from . import praw
from .spamfilter import isspam, spamfilter_lists
from .search import image_search
from .util import domain_suffix, remove_control_characters
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


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
        raise ConfigurationError('Missing OAuth credentials')
    if refresh_token:
        session.refresh_access_information(refresh_token, update_session=True)
    else:
        access = session.get_bearer_access(username, password)
        session.set_access_credentials(**access)
    return session


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

def reddit_login(config):
    logger.info('Logging into Reddit API')

    user_agent = config.get('BOT_AGENT')

    client_id = config.get('OAUTH_CLIENT_ID')
    client_secret = config.get('OAUTH_SECRET_TOKEN')
    account_name = config.get('REDDIT_ACCOUNT_NAME')
    account_pass = config.get('REDDIT_ACCOUNT_PASS')

    use_oauth = client_id and client_secret
    use_login = account_name and account_pass
    if not use_login:
        raise ConfigurationError('Missing REDDIT_ACCOUNT_NAME setting')
    shadowbanned = check_shadowban(account_name, config.get('SEARCH_USER_AGENT'))
    if shadowbanned:
        logger.warning('%s may be shadowbanned.' % account_name)
    if use_oauth and use_login:
        account1 = r_oauth_login(user_agent, client_id, client_secret,
                                 username=account_name, password=account_pass)
        logger.debug('Logged in using OAuth2 (useragent: %s)' % user_agent)
    else:
        account1 = r_login(user_agent, account_name, account_pass)
        logger.debug('Logged in using password (useragent: %s)' % user_agent)

    # load a second praw instance for the second account (the one used to check the spam links)
    client2_id = config.get('SECOND_OAUTH_CLIENT_ID')
    client2_secret = config.get('SECOND_OAUTH_SECRET_TOKEN')
    account2_name = config.get('SECOND_ACCOUNT_NAME')
    account2_pass = config.get('SECOND_ACCOUNT_PASS')

    use_second_oauth = client2_id and client2_secret
    use_second_login = account2_name and account2_pass
    if use_second_login:
        shadowbanned = check_shadowban(account2_name, config.get('SEARCH_USER_AGENT'))
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
        account2 = False

    return (account1, account2)


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

def _reddit_spamfilter(results, sending_account, receiving_account, submission_id):
    urls = set([url for url, text in results])
    verified_urls = reddit_msg_linkfilter(urls, sending_account, receiving_account, submission_id)
    verified_results = []
    for result in results:
        url = result[0]
        if url in verified_urls:
            verified_results.append(result)
    return verified_results

def _filter_results(results, account1, account2, check_submission_id):
    """Filter search results
    """
    def sanitize_string(string):
        # strip possible control characters
        string = remove_control_characters(string)

        # also strip non-ascii characters
        #string = ''.join(c for c in string if ord(c) in range(32, 127))

        string = string.strip()
        return string

    results = [[sanitize_string(v) for v in result]
               for result in results]

    # filter results for spam
    spamlists = spamfilter_lists()
    results = [result for result in results if not isspam(result, spamlists)]
    if account2 and check_submission_id: # do reddit msg spamcheck if second account is configured
        results = _reddit_spamfilter(results, account2, account1, check_submission_id)

    return results

def _format_results(results):
    """Format search results
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

    results = [[escape_markdown(v) for v in result]
               for result in results]

    # format output
    markdown_links = ['[%s](%s)' % (text, url) for url, text in results]
    formatted = '\n\n'.join(markdown_links)
    return formatted


#
# Bot actions
#

# how the bot handles actions
ACTMODE_NONE    = 0 # no action
ACTMODE_LOG     = 1 # log action
ACTMODE_PM      = 2 # pm/message action
ACTMODE_COMMENT = 4 # (reddit-) comment action
ACTMODES = (ACTMODE_LOG | ACTMODE_PM | ACTMODE_COMMENT)

#ACTMODE = ACTMODE_NONE

def _any_from_list_in_string(list_, string_):
    string_ = str(string_).lower()
    return any(str(w).lower() in string_ for w in list_)

def _applicable_comment(comment, config, account, already_done, subreddit_list, search_list, information_reply):
    time_limit_minutes = config.getint('COMMENT_REPLY_AGE_LIMIT')
    image_formats = config.getlist('IMAGE_FORMATS')
    footer_message = config.get('FOOTER_INFO_MESSAGE')

    def skip_as_done(): # put in database and abort processing
        already_done.append(comment.id)
        return False

    if comment.id in already_done:
        #logger.debug('[D] comment %s already logged as done' % comment.id)
        return False
    if not comment.author: #check if the comment exists
        logger.debug('[X] %s - comment has no author / does not exist' % comment.id)
        skip_as_done()
    if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
        logger.debug('[!] %s - comment\'s subreddit is not in our list' % comment.id)
        skip_as_done()
    comment_time_diff = (time.time() - comment.created_utc)
    if comment_time_diff / 60 > time_limit_minutes:
        logger.debug('[O] %s - comment has been created %d minutes ago, our reply-limit is %d' \
                     % (comment.id, comment_time_diff / 60, time_limit_minutes))
        skip_as_done()
    is_image = _any_from_list_in_string(image_formats, message.submission.url)
    if not is_image:
        # not relevant; unless we see an imgur/gfycat domain (those are always images)
        domain = domain_suffix(message.submission.url)
        if domain not in ('imgur.com', 'gfycat.com'):
            logger.debug('[T] %s - comment has no picture' % comment.id)
            skip_as_done()
    comment_body = comment.body.encode('utf-8')
    keywords = _any_from_list_in_string(search_list, comment_body)
    if not keywords:
        logger.debug('[P] %s - comment has no keyword' % comment.id)
        skip_as_done()
    # found a keyword
    top_level = [c.replies for c in comment.submission.comments] # FIXME: do we need this?
    submission_comments = []
    for i in top_level:
        for j in i:
            submission_comments.append(j)

    if any(i for i in submission_comments if footer_message in i.body): # already replied? FIXME: wont match if our FOOTER_MESSAGE changed!
        logger.debug('[R] %s - comment has our footer message (ours)' % comment.id)
        skip_as_done()
    if any(i for i in submission_comments if information_reply in i.body): # already replied? (this applies only to `find_keywords` method)
        logger.debug('[R] %s - comment has our info message (ours)' % comment.id)
        skip_as_done()
    if comment.author == account.user: # ooh, that's us!? we lost our memory?
        logger.debug('[U] %s - comment author is us (ours)' % comment.id)
        skip_as_done()

    return keywords # good

def _message_reply(message, reply_func):
    if not callable(reply_func):
        return # error

    attempt = 0
    while True:
        if attempt >= 2: # max retries: 2
            return
            #return ('error', 'max retries reached')
        attempt += 1
        try:
            return reply_func(message)
        except praw.errors.RateLimitExceeded as e:
            errmsg = str(e)
            backoff, min_secs = re.search(r'try again in ([0-9]+) (minutes?|seconds?)', errmsg).groups()
            if 'second' in min_secs:
                backoff = int(backoff)
            elif 'minute' in min_secs:
                backoff = int(backoff) * 60
            backoff += 3 # grace
            logger.warning('Ratelimit hit. Backing off %d seconds!' % backoff) # TODO: get ratelimit reset time here
            time.sleep(backoff)
        # the following are permanent errors, no retry
        except praw.errors.InvalidComment:
            logger.warning('[F] %s - comment invalid (was deleted while trying to reply?)', comment.id)
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

def handle_bot_action(messages, config, account, account2, subreddit_list, already_done, action):

    # find_username_mentions
    def find_username_mentions(message): # reply_func
        try:
            reply_content = image_search(message.submission.url, config, account, account2, display_limit=5)
            if not reply_content:
                logger.error('image_search failed (bug)! skipping')
                # try that again, instead of replying with no results
                return
        except Exception as e:
            logger.error('Error occured in image_search: %s' % e)
            return

        if ACTMODE & ACTMODE_LOG:
            logger.warning(reply_content)
        if ACTMODE & ACTMODE_COMMENT:
            message.reply(reply_content)
        elif ACTMODE & ACTMODE_PM:
            message.reply(reply_content)
        #if ACTMODE & ACTMODE_PM:
        #    whatever = account.send_message(message.author, 'Info Bot Information', reply_content)
        #    logger.info(whatever)

        message.mark_as_read()
        return

    # find_keywords
    def find_keywords(message): # reply_func
        reply_content = information_reply
        if ACTMODE & ACTMODE_LOG:
            logger.warning(reply_content)
        if ACTMODE & ACTMODE_COMMENT:
            message.reply(reply_content)
        if ACTMODE & ACTMODE_PM:
            whatever = account.send_message(message.author, 'Info Bot Information', reply_content)
            logger.info(whatever)
        return

    if action == 'find_username_mentions':
        search_list = config.getlist('BOTCMD_IMAGESEARCH')
        reply_func = find_username_mentions
    elif action == 'find_keywords':
        search_list = config.getlist('BOTCMD_INFORMATIONAL')
        reply_func = find_keywords
    else:
        return
    information_reply = config.get('BOTCMD_INFORMATIONAL_REPLY')

    if not search_list:
        return

    count = 0
    for message in messages:
        count += 1
        message_body = message.body.encode('utf-8')
        keywords = _applicable_comment(message, config, account, already_done, subreddit_list, search_list, information_reply)
        if not keywords:
            continue
        logger.info('[R] Detected keyword/s %s in %s, replying [%s]' % (keywords, message.id, message_body))
        _message_reply(message, reply_func)
        already_done.append(message.id)
        logger.info('replied to message: {0}'.format(message.body))

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #logger.info('(%d comments - %s)' % (count, se))
    logger.info('(%d comments/messages scanned)' % (count,))


def check_downvotes(user, start_time, deletion_wait_time):
    # FIXME: should check for comment's creation time
    current_time = int(time.time()/60)
    if (current_time - start_time) >= deletion_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 1:
                comment_id = comment.id
                if ACTMODE & ACTMODE_COMMENT:
                    comment.delete()
                    logger.info('deleted comment: %s' % comment_id)
                elif ACTMODE & ACTMODE_PM:
                    comment.delete()
                    logger.info('deleted comment: %s' % comment_id)
                #if ACTMODE & ACTMODE_PM:
                #    logger.info('should delete comment: %s' % comment_id)
                if ACTMODE & ACTMODE_LOG:
                    logger.warning('would have deleted comment: %s' % comment_id)
        return current_time
    return start_time
