# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import logging
import warnings
import time
import uuid

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
    session = praw.Reddit(user_agent)
    shadowbanned = False
    try:
        user = session.get_redditor(user)
    except praw.errors.HTTPException as e:
        if e._raw.status_code == 404:
            shadowbanned = True
        else:
            raise
    return shadowbanned

def reddit_login(config):
    logger.info('Logging into Reddit API')

    user_agent = config.get('BOT_AGENT')

    client_id = config.get('OAUTH_CLIENT_ID')
    client_secret = config.get('OAUTH_SECRET_TOKEN')
    account_name = config.get('REDDIT_ACCOUNT_NAME')
    account_pass = config.get('REDDIT_ACCOUNT_PASS')

    use_oauth = client_id and client_secret
    use_login = account_name and account_pass
    if use_oauth and use_login:
        account1 = r_oauth_login(user_agent, client_id, client_secret,
                                 username=account_name, password=account_pass)
        logger.debug('Logged in using OAuth2 (useragent: %s)' % user_agent)
    else:
        if not account_name or not account_pass:
            raise ConfigurationError('Missing login credentials')
        shadowbanned = check_shadowban(account_name, user_agent)
        if shadowbanned:
            logger.warning('%s may be shadowbanned.' % account_name)
        account1 = r_login(user_agent, account_name, account_pass)
        logger.debug('Logged in using password (useragent: %s)' % user_agent)

    # load a second praw instance for the second account (the one used to check the spam links)
    client2_id = config.get('SECOND_OAUTH_CLIENT_ID')
    client2_secret = config.get('SECOND_OAUTH_SECRET_TOKEN')
    account2_name = config.get('SECOND_ACCOUNT_NAME')
    account2_pass = config.get('SECOND_ACCOUNT_PASS')

    use_second_oauth = client2_id and client2_secret
    use_second_login = account2_name and account2_pass
    if use_second_oauth and use_second_login:
        account2 = r_oauth_login(user_agent, client2_id, client2_secret,
                                 username=account2_name, password=account2_pass)
        logger.debug('Logged in second account using OAuth2')
    elif use_second_login:
        shadowbanned = check_shadowban(account2_name, user_agent)
        if shadowbanned:
            logger.warning('%s may be shadowbanned.' % account2_name)
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
        print('<', end='')
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
            print('>', end='')
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

def reply_to_potential_comment(comment, account, config, already_done):
    keyword_list = config.getlist('BOTCMD_INFORMATIONAL')
    image_formats = config.getlist('IMAGE_FORMATS')
    reply = config.get('BOTCMD_INFORMATIONAL_REPLY')

    if not keyword_list:
        return True
    if not any(i in str(comment.submission.url) for i in image_formats):
        return True
    done = False
    try:
        if ACTMODE & ACTMODE_LOG:
            logger.warning(reply)
        if ACTMODE & ACTMODE_COMMENT:
            comment.reply(reply)
        if ACTMODE & ACTMODE_PM:
            logger.info(account.send_message(comment.author, 'Info Bot Information', reply))
        logger.info('replied to potential comment: {0}'.format(comment.body))
        done = True
        already_done.append(comment.id)
    except praw.errors.Forbidden as e:
        done = True
        logger.warning('Cannot reply. Bot forbidden from this sub: %s' % e)
        already_done.append(comment.id)
    except praw.errors.InvalidComment:
        done = True
        logger.warning('Comment was deleted while trying to reply.')
    except praw.errors.PRAWException as e:
        done = True # at least for now? but don't store state
        logger.error('Some unspecified PRAW issue occured while trying to reply: %s' % e)
    return done

def _applicable_comment(comment, subreddit_list, time_limit_minutes):
    if not comment.author: #check if the comment exists
        print('x', end='')
        return False
    if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
        print('!', end='')
        return False
    if (time.time()-comment.created_utc)/60 > time_limit_minutes: #if the age of the comment is more than the time limit
        print('o', end='')
        return False
    return True # good

def _any_from_list_in_string(list_, string_):
    string_ = str(string_).lower()
    return any(str(w).lower() in string_ for w in list_)
    #return any(True for w in list_ if str(w).lower() in string_)

def find_username_mentions(account, account2, config, subreddit_list, already_done):
    search_strings = config.getlist('BOTCMD_IMAGESEARCH')
    time_limit_minutes = config.getint('COMMENT_REPLY_AGE_LIMIT') #how long before a comment will be ignored for being too old
    image_formats = config.getlist('IMAGE_FORMATS')
    extra_message = config.get('FOOTER_INFO_MESSAGE')

    count = 0
    for message in account.get_unread(limit=100):
        count += 1
        message_body = message.body.encode('utf-8')
        if not _any_from_list_in_string(search_strings, message_body):
            print('.', end='')
            continue
        if not _applicable_comment(message, subreddit_list, time_limit_minutes):
            continue
        isPicture = _any_from_list_in_string(image_formats, message.submission.url)
        if not isPicture:
            domain = domain_suffix(message.submission.url)
            if domain not in ('imgur.com', 'gfycat.com'):
                print('t', end='')
                continue
        top_level = [i.replies for i in message.submission.comments]
        submission_comments = []
        for i in top_level:
            for j in i:
                submission_comments.append(j)
        if any(i for i in submission_comments if extra_message in i.body): #If there are link replies
            print('p', end='')
            continue
        if message.id in already_done:
            print('r', end='')
            continue
        if message.author == account.user:
            print('u', end='')
            continue
        print('R')
        try:
            reply = image_search(message.submission.url, config, account, account2, display_limit=5)
        except Exception as e:
            logger.error('Error occured in search: %s' % e)
            reply = None
            # lets cancel this answer to try again, instead of replying with no results
            break
        if not reply:
            logger.error('image_search failed (bug)! skipping')
            continue
        done = False
        attempt = 0
        while not done:
            attempt += 1
            if attempt > 2: # max retries: 2
                done = True

            try:
                if ACTMODE & ACTMODE_LOG:
                    logger.warning(reply)
                if ACTMODE & ACTMODE_COMMENT or ACTMODE & ACTMODE_PM:
                    message.reply(reply)
                #if ACTMODE & ACTMODE_PM:
                #    print(account.send_message(message.author, 'Info Bot Information', reply))
                print(' (replied to message comment with more info) ', end='')
                print('>')
                done = True
            except praw.errors.RateLimitExceeded as e:
                errmsg = str(e)
                backoff, min_secs = re.search(r'try again in ([0-9]+) (minutes?|seconds?)', errmsg).groups()
                if 'second' in min_secs:
                    backoff = int(backoff)
                elif 'minute' in min_secs:
                    backoff = int(backoff) * 60
                backoff += 3 # grace
                logger.warning('Rate limited. Backing off %d seconds!' % backoff)
                time.sleep(backoff)
            # the following are permanent errors, no retry
            except praw.errors.InvalidComment:
                logger.warning('Comment was deleted while trying to reply.')
                done = True
            except praw.errors.Forbidden as e:
                logger.warning('Cannot reply. Bot forbidden: %s' % e)
                done = True
            except praw.errors.PRAWException as e:
                logger.error('Some unspecified PRAW issue occured while trying to reply: %s' % e)
                done = True

        already_done.append(message.id)
        message.mark_as_read()
    logger.info('(%d messages handled)' % (count,))


def find_keywords(all_comments, account, config, subreddit_list, already_done):
    keyword_list = config.getlist('BOTCMD_INFORMATIONAL')
    time_limit_minutes = config.getint('COMMENT_REPLY_AGE_LIMIT') #how long before a comment will be ignored for being too old
    image_formats = config.getlist('IMAGE_FORMATS')
    extra_message = config.get('FOOTER_INFO_MESSAGE')
    information_reply = config.get('BOTCMD_INFORMATIONAL_REPLY')

    count = 0
    for comment in all_comments:
        count += 1
        comment_body = comment.body.encode('utf-8')
        if not _applicable_comment(comment, subreddit_list, time_limit_minutes):
            continue
        isPicture = _any_from_list_in_string(image_formats, comment.link_url)
        if not isPicture:
            print('t', end='')
            continue
        if not _any_from_list_in_string(keyword_list, comment_body):
            print('p', end='')
            continue
        top_level = [i.replies for i in comment.submission.comments]
        submission_comments = []
        for i in top_level:
            for j in i:
                submission_comments.append(j)
        if any(i for i in submission_comments if extra_message in i.body): #If there are link replies
            print('r', end='')
            continue
        if not any(i for i in submission_comments if i.body == information_reply): #If there are information replies
            print('r', end='')
            continue
        print('\ndetected keyword: %s' % comment_body.lower())
        if comment.id in already_done:
            print('r', end='')
            continue
        if comment.author == account.user:
            print('u', end='')
            continue
        print('R', end='')
        done = False
        attempt = 0
        while not done:
            attempt += 1
            if attempt > 2: # max retries: 2
                done = True

            try:
                done = reply_to_potential_comment(comment, account, config, already_done)
                print('>', end='')
            except praw.errors.RateLimitExceeded as e:
                errmsg = str(e)
                backoff, min_secs = re.search(r'try again in ([0-9]+) (minutes?|seconds?)', errmsg).groups()
                if 'second' in min_secs:
                    backoff = int(backoff)
                elif 'minute' in min_secs:
                    backoff = int(backoff) * 60
                backoff += 3 # grace
                logger.warning('Rate limited. Backing off %d seconds!' % backoff)
                time.sleep(backoff)
            # the following are permanent errors, no retry
            except praw.errors.InvalidComment:
                logger.warning('Comment was deleted while trying to reply.')
                done = True
            except praw.errors.Forbidden as e:
                logger.warning('Cannot reply. Bot forbidden: %s' % e)
                done = True
            except praw.errors.PRAWException as e:
                logger.error('Some unspecified PRAW issue occured while trying to reply: %s' % e)
                done = True

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #logger.info('(%d comments - %s)' % (count, se))
    logger.info('(%d comments)' % (count,))

def check_downvotes(user, start_time, comment_deleting_wait_time):
    # FIXME: should check for comment's creation time
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 1:
                comment_id = comment.id
                if ACTMODE & ACTMODE_COMMENT:
                    comment.delete()
                    logger.info('deleted comment: %s' % comment_id)
                #if ACTMODE & ACTMODE_PM:
                #    logger.info('should delete comment: %s' % comment_id)
                if ACTMODE & ACTMODE_LOG:
                    logger.warning('would have deleted comment: %s' % comment_id)
        return current_time
    return start_time
