# -*- coding: utf-8 -*-
from __future__ import print_function
import praw
import time
import uuid

from .antispam import isspam, spamfilter_lists
from .util import remove_control_characters


def r_login(user_agent, username, password):
    """login to reddit account"""

    account = praw.Reddit(user_agent)
    account.login(username, password, disable_warning=True) # drop the warning for now (working on it)
    # 'Logged in as /u/%s' % username
    return account

def reddit_login(config):
    print('Logging into accounts')

    user_agent = config['BOT_NAME']

    account1 = r_login(user_agent, config.get('REDDIT_ACCOUNT_NAME'), config.get('REDDIT_ACCOUNT_PASS'))
    if config.get('SECOND_ACCOUNT_NAME', None) and config.get('SECOND_ACCOUNT_PASS', None):
        # load a second praw instance for the second account (the one used to check the spam links)
        account2 = r_login(user_agent, config['SECOND_ACCOUNT_NAME'], config['SECOND_ACCOUNT_PASS'])
    else:
        account2 = False

    user = account1.get_redditor(config['REDDIT_ACCOUNT_NAME'])

    return (account1, account2, user)


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
        print('<', end='')
    print()

    time.sleep(7) # wait a bit

    # fetch posts on second account
    print('reddit_msg_linkfilter verifying messages: ', end='')
    verified_messages = []
    fetched_messages = receiving_account.get_unread(limit=40)
    for msg in fetched_messages:
        if not msg.body.startswith('['):
            # skip unknown messages
            #print('\nreddit_msg_linkfilter skipping unknown message "%s..."' % msg.body[:10])
            continue
        for id in queue.keys():
            if str(id) not in msg.body:
                continue
            message = queue.pop(id)
            #if message != str(msg.body).replace('[%s] ' % id, ''):
            #    print('(message got mangled?)')
            msg.mark_as_read()
            verified_messages += [message]
            print('>', end='')
    print()
    if queue: # shouldnt have any messages left at this point
        print('reddit_msg_linkfilter posted but did not find: %s' % str(queue.values()))
    failed_messages = [m for m in messages if (m not in verified_messages and m not in queue.values())]
    if failed_messages:
        print('reddit_msg_linkfilter failed on: %s' % str(failed_messages))
    return verified_messages

def _reddit_spamfilter(results, sending_account, receiving_account, submission_id):
    urls = set([url for url, text in results])
    verified_urls = reddit_msg_linkfilter(urls, sending_account, receiving_account, submission_id)
    verified_results = []
    for url, text in results:
        if url in verified_urls:
            verified_results += result
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
