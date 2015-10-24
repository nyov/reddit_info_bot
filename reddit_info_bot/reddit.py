# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import time
import uuid

from . import praw
from .antispam import isspam, spamfilter_lists
from .util import remove_control_characters
from .exceptions import ConfigurationError


def r_login(user_agent, username, password):
    """authenticate to reddit api using user credentials
    """
    session = praw.Reddit(user_agent)
    session.login(username, password)
    return session

def r_oauth_login(user_agent, client_id, client_secret,
                  redirect_uri=None, refresh_token=None,
                  username=None, password=None):
    """authenticate to reddit api using oauth
    """
    session = praw.Reddit(user_agent)
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
    print('Logging into accounts')

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
    else:
        if not account_name or not account_pass:
            raise ConfigurationError('Missing login credentials')
        shadowbanned = check_shadowban(account_name, user_agent)
        if shadowbanned:
            print('%s may be shadowbanned.' % account_name)
        account1 = r_login(user_agent, account_name, account_pass)

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
    elif use_second_login:
        shadowbanned = check_shadowban(account2_name, user_agent)
        if shadowbanned:
            print('%s may be shadowbanned.' % account2_name)
        account2 = r_login(user_agent, account2_name, account2_pass)
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
        #print('%4d' % url_length, subreddit)
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
    print('reddit_msg_linkfilter posting messages: ', end='')
    count = 0
    for message in messages:
        # use a unique id in the message so we'll always recognize it
        # (even if the text got mangled, e.g. unicode or other strangeness)
        id = uuid.uuid4()
        try:
            _message = '[%s] %s' % (id, message)
            submission.add_comment(_message)
        except Exception as e:
            print('\nreddit_msg_linkfilter failed to post "%s"' % (message,))
            print(e)
            # FIXME: check exception for http errors (retry?) or other (spam?)
            continue
        queue.update({id: message})
        count += 1
        print('<', end='')
    print(' (%d message(s), waiting...)' % count)

    time.sleep(7) # wait a bit

    # fetch posts on second account
    print('reddit_msg_linkfilter verifying messages: ', end='')
    verified_messages = []
    fetched_messages = list(receiving_account.get_unread(limit=40))
    count = 0
    for msg in fetched_messages:
        msg_body = msg.body # is unicode
        if not msg_body.startswith('['):
            # skip unknown messages
            #print('(skipping unknown message "%s...") ' % msg_body[:10], end='')
            continue
        for id in queue.keys():
            if str(id) not in msg_body:
                continue
            message = queue.pop(id)
            #if message != msg_body.replace('[%s] ' % id, ''):
            #    print('(message got mangled?)')
            msg.mark_as_read()
            verified_messages += [message]
            print('>', end='')
            count += 1
    print(' (%d unread message(s) fetched, %d verified, %d unknown(s))' % (len(fetched_messages)-1, count, len(fetched_messages)-1-count))
    if queue: # shouldnt have any messages left at this point
        print('reddit_msg_linkfilter filtered out: %s' % ', '.join('"%s"' % x for x in queue.values()))
    failed_messages = [m for m in messages if (m not in verified_messages and m not in queue.values())]
    if failed_messages:
        print('reddit_msg_linkfilter completely failed on: %s' % str(failed_messages))
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
