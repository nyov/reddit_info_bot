#!/usr/bin/python
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
import urllib2
import requests
import re
import json
import string
from praw.errors import RateLimitExceeded
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit

# version
import pkgutil
__version__ = pkgutil.get_data(__package__ or __name__, 'VERSION').decode('ascii').strip()
version_info = tuple(int(v) if v.isdigit() else v
                     for v in __version__.split('.'))
del pkgutil

from .search import (
    #get_google_results,
    #get_bing_results,
    #get_yandex_results,
    #get_karmadecay_results,
    get_tineye_results,
)
from .reddit import reddit_login, reddit_msg_linkfilter
from .antispam import spamfilter_lists, isspam
from .util import domain_suffix, remove_control_characters

logger = logging.getLogger(__name__)


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
    results = [result for result in results if not isspam(result)]
    if account2: # do reddit msg spamcheck if second account is configured
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

def comment_exists(comment):
    return True
    try:
        if account1.get_info(thing_id = comment.id):
            return True
    except:
        pass
    print('Comment was deleted')
    return False

def give_more_info(submission_url, display_limit=None):
    """
    """
    from base64 import b64decode
    extra_message = config['EXTRA_MESSAGE']
    no_results_message = config['NO_SEARCH_RESULTS_MESSAGE']

    print('Image-searching for %s' % submission_url)

    # substitute videos with gif versions where possible
    # (because search engines index those)
    domain = domain_suffix(submission_url)
    if domain in ('imgur.com', 'gfycat.com'):
        fileformats = ('.gifv', '.mp4', '.webm', '.ogg')
        if submission_url.endswith(fileformats):
            for ff in fileformats:
                submission_url = submission_url.replace(ff, '.gif')
            print('Found %s video - substituting with gif url: %s' % (domain, submission_url))
        elif urlsplit(submission_url).path.rstrip(string.ascii_lowercase+string.ascii_uppercase) == '/':
            submission_url += '.gif'
            print('Found %s video - using gif url: %s' % (domain, submission_url))

    link = re.sub("/","*", submission_url)
    results = ''
    i = 0
    app = unicode(b64decode('aHR0cHM6Ly9zbGVlcHktdHVuZHJhLTU2NTkuaGVyb2t1YXBwLmNvbS9zZWFyY2gv'))
    while not results:
        i += 1
        try:
            if 'DEBUG' in config and config['DEBUG']:
                ### for debugging, cache response
                _dumpfile = 'proxydebug'
                if not os.path.exists(_dumpfile):
                    response = urllib2.urlopen(app+link).read()
                    with open(_dumpfile, 'wb') as f:
                        f.write(response)
                with open(_dumpfile, 'rb') as f:
                    response = f.read()
            else:
                response = urllib2.urlopen(app+link).read()
            results = eval(response)
        except urllib2.HTTPError as e:
            print(e)
            print("Retrying %d" % i)

    search_engines = OrderedDict([
        ('google', 'Google'),
        ('bing', 'Bing'),
        ('yandex', 'Yandex'),
        ('tineye', 'Tineye'),
        ('karmadecay', 'Karma Decay'),
    ])

    message = '**Best %s Guesses**\n\n%s\n\n'
    reply = ''

    for engine, provider in search_engines.items():
        try:
            # hardcoded results
            if engine == 'google':
                result = results[0]
                #print('google:', result)
            if engine == 'bing':
                result = results[1]
                #print('bing:', result)
            if engine == 'yandex':
                result = results[2]
                #print('yandex:', result)
            if engine == 'karmadecay':
                result = results[3]
                # sometimes we get nonempty empty results...
                if result == [(u'', u'')]:
                    result = []
                #print('karma:', result)
            if engine == 'tineye':
                result = get_tineye_results(submission_url, config)
                #print('tineye:', result)
        except IndexError as e:
            print('Failed fetching %s results: %s' % (provider, e))

        # sanity check on app's response:
        _dropped = _ok = 0
        _good = []
        for idx, item in enumerate(result):
            # result should always be '(url, text)', nothing else
            if len(item) != 2:
                _dropped += 1
                continue
            (url, text) = item
            # quick check for *impossible* urls
            if not url.strip().startswith(('http', 'ftp', '//')): # http | ftp | //:
                _dropped += 1
                continue
            _ok += 1
            _good += [item]
        result = _good

        if _dropped > 0:
            print('Dropped %d invalid result(s) from proxy for %s, %d result(s) remaining' % \
                    (_dropped, provider, _ok))
        del _dropped, _ok, _good

        if not result:
            reply += message % (provider, 'No available links from this search engine found.')
            del search_engines[engine]
            continue

        # spam-filter results
        filtered  = _filter_results(result, account1, account2, config['SUBMISSION_ID'])

        if not filtered:
            reply += message % (provider, 'No available links from this search engine found.')
            del search_engines[engine]
            continue

        # limit output to `display_limit` results
        if display_limit:
            filtered = filtered[:display_limit]

        # format results
        formatted = _format_results(filtered)

        reply += message % (provider, formatted)

    if not search_engines:
        reply = no_results_message

    reply += extra_message
    return reply

#
# Bot actions
#

def reply_to_potential_comment(comment, account):
    if not config['USE_KEYWORDS']:
        return True
    if not any(i in str(comment.submission.url) for i in config['IMAGE_FORMATS']):
        return True
    done = False
    try:
        reply = config["INFORMATION_REPLY"]
        if ACTMODE & ACTMODE_LOG:
            print(reply)
        if ACTMODE & ACTMODE_COMMENT:
            if comment_exists(comment):
                comment.reply(reply)
        if ACTMODE & ACTMODE_PM:
            print(account.send_message(comment.author, 'Info Bot Information', reply))
        print("replied to potential comment: {0}".format(comment.body))
        done = True
        already_done.append(comment.id)
    except requests.HTTPError as e:
        done = True
        print('HTTP Error. Bot might be banned from this sub:', e)
        already_done.append(comment.id)
    return done

def find_username_mentions():
    count = 0
    for comment in account1.get_unread(limit=100):
        count += 1
        if config['SEARCH_STRING'] not in comment.body:
            print('.', end='')
            continue
        if not comment.author: #check if the comment exists
            print('x', end='')
            continue
        if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
            print('!', end='')
            continue
        if (time.time()-comment.created_utc)/60 > time_limit_minutes: #if the age of the comment is more than the time limit
            print('o', end='')
            continue
        try:
            isPicture = any(i in str(comment.submission.url) for i in config['IMAGE_FORMATS'])
        except UnicodeEncodeError:
            isPicture = False #non-ascii url
        if not isPicture:
            print('t', end='')
            continue
        top_level = [i.replies for i in comment.submission.comments]
        submission_comments = []
        for i in top_level:
            for j in i:
                submission_comments.append(j)
        if any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are link replies
            print('p', end='')
            continue
        if comment.id in already_done:
            print('r', end='')
            continue
        if comment.author == user:
            # oops
            print('u', end='')
            continue
        reply = give_more_info(comment.submission.url, display_limit=5)
        try:
            if ACTMODE & ACTMODE_LOG:
                print(reply)
            if ACTMODE & ACTMODE_COMMENT or ACTMODE & ACTMODE_PM:
                if comment_exists(comment):
                    comment.reply(reply)
                    print('replied to comment with more info', end='')
            print('>', end='')
        except requests.HTTPError as e:
            print('HTTP Error. Bot might be banned from this sub')
            print(e)

        already_done.append(comment.id)
        comment.mark_as_read()
    print(' (%d comments)' % (count,))


def find_keywords(all_comments):
    keyword_list = config['KEYWORDS']
    count = 0
    for comment in all_comments:
        count += 1
        if not comment.author: #check if the comment exists
            print('x', end='')
            continue
        if str(comment.subreddit) not in subreddit_list: #check if it's in one of the right subs
            print('!', end='')
            continue
        if (time.time()-comment.created_utc)/60 > time_limit_minutes: #if the age of the comment is more than the time limit
            print('o', end='')
            continue
        try:
            isPicture = any(i in str(comment.link_url) for i in config['IMAGE_FORMATS'])
        except UnicodeEncodeError:
            isPicture = False #non-ascii url
        if not isPicture:
            print('t', end='')
            continue
        body = comment.body.lower()
        if not any(word.lower() in body.lower() for word in keyword_list):
            print('p', end='')
            continue
        ##comments = account1.get_submission(url="https://www.reddit.com/r/{0}/comments/{1}/aaaa/{2}".format(comment.subreddit, comment.link_id[3:], comment.id)).comments
        #comments = comment.submission.comments
        #if comments: #get_submission returns a valid comment object
        #    comment = comments[0]
        top_level = [i.replies for i in comment.submission.comments]
        submission_comments = []
        for i in top_level:
            for j in i:
                submission_comments.append(j)
        if any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are link replies
            print('R', end='')
            continue
        if not any(i for i in submission_comments if i.body == config['INFORMATION_REPLY']): #If there are information replies
            print('R', end='')
            continue
        try:
            print("\ndetected keyword: "+ comment.body.lower())
        except UnicodeEncodeError:
            print("\ndetected keyword: ", end="")
            try:
                print(comment.body)
            except: pass #print(''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2))
        if comment.id in already_done:
            print('r', end='')
            continue
        if comment.author == user:
            # oops
            print('u', end='')
            continue
        done = False
        attempt = 1
        while not done:
            try:
                done = reply_to_potential_comment(comment, account1)
                print('>', end='')
            except RateLimitExceeded as e:
                print('submission rate exceeded! attempt %i' % attempt)
                print(e)
                time.sleep(30)

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #print(' (%d comments - %s)' % (count, se))
    print(' (%d comments)' % (count,))

def check_downvotes(user, start_time):
    # FIXME: should check for comment's creation time
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 1:
                comment_id = comment.id
                if ACTMODE & ACTMODE_COMMENT:
                    comment.delete()
                    print('deleted comment: %s' % comment_id)
                #if ACTMODE & ACTMODE_PM:
                #    print('should delete comment: %s' % comment_id)
                if ACTMODE & ACTMODE_LOG:
                    print('would have deleted comment: %s' % comment_id)
        return current_time
    return start_time

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

def get_all_comments(stream):
    # paginated
    #feed_comments = stream.get_comments(limit=None)
    # using default limit (old implementation)
    feed_comments = stream.get_comments()
    return feed_comments


def main():
    start_time = time.time()
    print('Starting run...')
    while True:
        try:
            for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                print('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
                a = time.time()
                all_comments = get_all_comments(stream)
                if not all_comments:
                    continue
                print(time.time()-a)
                find_keywords(all_comments)
                print('finding username mentions: ', end='')
                find_username_mentions()
                start_time = check_downvotes(user, start_time)

                with open("already_done.p", "wb") as df:
                    pickle.dump(already_done, df)

                print('Finished a round of comments. Waiting two seconds.\n')
                time.sleep(2)
        except requests.ConnectionError:
            print('Connection Error')
        except requests.HTTPError:
            print('HTTP Error')


if __name__ == "__main__" or True: # always do this, for now
    with open('config.json') as json_data:
        config = json.load(json_data)

    wd = None
    if 'BOT_WORKDIR' in config:
        wd = config["BOT_WORKDIR"]
    if wd:
        if os.path.exists(wd):
            os.chdir(wd)
            if os.getcwd() != wd:
                errmsg = 'Switching to workdir failed!'
                sys.exit(errmsg)
        else: # BOT_WORKDIR was requested, but does not exist. That's a failure.
            errmsg = "Requested BOT_WORKDIR '{0}' does not exist, aborting.".format(wd)
            sys.exit(errmsg)
    else:
        print('No BOT_WORKDIR was specified in the config, running in current directory.')

    # how the bot handles actions
    ACTMODE_NONE    = 0 # no action
    ACTMODE_LOG     = 1 # log action
    ACTMODE_PM      = 2 # pm/message action
    ACTMODE_COMMENT = 4 # (reddit-) comment action
    ACTMODES = (ACTMODE_LOG | ACTMODE_PM | ACTMODE_COMMENT)

    # TODO: get a list from config
    botmodes = [config['MODE'].lower()]
    ACTMODE = ACTMODE_NONE
    for botmode in botmodes:
        if botmode == 'comment':
            ACTMODE |= ACTMODE_COMMENT
        if botmode == 'pm':
            ACTMODE |= ACTMODE_PM
        if botmode == 'log':
            ACTMODE |= ACTMODE_LOG

    time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
    comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments

    already_done = []
    if os.path.isfile("already_done.p"):
        with open("already_done.p", "rb") as f:
            already_done = pickle.load(f)

    #account1 = account2 = None
    #url = 'https://i.imgur.com/yZKXDPV.jpg'
    #url = 'http://i.imgur.com/mQ7Tuye.gifv'
    #print(give_more_info(url, display_limit=5))
    #sys.exit()

    (account1, account2, user, subreddit_list) = reddit_login(config)

    print('Fetching comment stream urls')
    #comment_stream_urls = [account1.get_subreddit(subredditlist) for subredditlist in build_subreddit_feeds(subreddit_list)]
    comment_stream_urls = []
    for count, subredditlist in enumerate(build_subreddit_feeds(subreddit_list)):
        print('loading comment stream %2d "%s..."' % (count+1, subredditlist[:60]))
        comment_feed = account1.get_subreddit(subredditlist)
        # lazy objects, nothing done yet
        comment_stream_urls += [comment_feed]

    main()
