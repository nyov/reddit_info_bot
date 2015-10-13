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
import praw.errors
from collections import OrderedDict
from six.moves.urllib.parse import urlsplit

from .version import __version__, version_info
from .search import (
    #get_google_results,
    #get_bing_results,
    #get_yandex_results,
    #get_karmadecay_results,
    get_tineye_results,
)
from .reddit import reddit_login, build_subreddit_feeds, _filter_results, _format_results
from .antispam import spamfilter_lists
from .util import domain_suffix, chwd

logger = logging.getLogger(__name__)


def give_more_info(submission_url, config, account1, account2, display_limit=None):
    """
    """
    from base64 import b64decode
    extra_message = config['EXTRA_MESSAGE']
    no_results_message = config['NO_SEARCH_RESULTS_MESSAGE']
    submission_id = config['SUBMISSION_ID']

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
        # on imgur, this could be a regular image, but luckily imgur provides a .gif url anyway :)
        elif urlsplit(submission_url).path.rstrip(string.ascii_lowercase+string.ascii_uppercase) == '/':
            submission_url += '.gif'
            print('Found potential %s video - using gif url: %s' % (domain, submission_url))

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
        filtered  = _filter_results(result, account1, account2, submission_id)

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

# how the bot handles actions
ACTMODE_NONE    = 0 # no action
ACTMODE_LOG     = 1 # log action
ACTMODE_PM      = 2 # pm/message action
ACTMODE_COMMENT = 4 # (reddit-) comment action
ACTMODES = (ACTMODE_LOG | ACTMODE_PM | ACTMODE_COMMENT)

ACTMODE = ACTMODE_NONE

def reply_to_potential_comment(comment, account, config, already_done):
    keyword_list = config['KEYWORDS']
    image_formats = config['IMAGE_FORMATS']
    reply = config['INFORMATION_REPLY']

    if not keyword_list:
        return True
    if not any(i in str(comment.submission.url) for i in image_formats):
        return True
    done = False
    try:
        if ACTMODE & ACTMODE_LOG:
            print(reply)
        if ACTMODE & ACTMODE_COMMENT:
            comment.reply(reply)
        if ACTMODE & ACTMODE_PM:
            print(account.send_message(comment.author, 'Info Bot Information', reply))
        print("replied to potential comment: {0}".format(comment.body))
        done = True
        already_done.append(comment.id)
    except praw.errors.Forbidden as e:
        done = True
        print('\nCannot reply. Bot forbidden from this sub:', e)
        already_done.append(comment.id)
    except praw.errors.InvalidComment:
        done = True
        print('\nComment was deleted while trying to reply.')
    except praw.errors.PRAWException as e:
        done = True # at least for now? but don't store state
        print('\nSome unspecified PRAW issue occured while trying to reply:', e)
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

def find_username_mentions(account, account2, config, user, subreddit_list, already_done):
    search_string = config['SEARCH_STRING']
    time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
    image_formats = config['IMAGE_FORMATS']
    extra_message = config['EXTRA_MESSAGE']

    count = 0
    for comment in account.get_unread(limit=100):
        count += 1
        if search_string not in comment.body:
            print('.', end='')
            continue
        if not _applicable_comment(comment, subreddit_list, time_limit_minutes):
            continue
        try:
            isPicture = any(i in str(comment.submission.url) for i in image_formats)
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
        if any(i for i in submission_comments if extra_message in i.body): #If there are link replies
            print('p', end='')
            continue
        if comment.id in already_done:
            print('r', end='')
            continue
        if comment.author == user:
            # oops
            print('u', end='')
            continue
        reply = give_more_info(comment.submission.url, config, account, account2, display_limit=5)
        try:
            if ACTMODE & ACTMODE_LOG:
                print(reply)
            if ACTMODE & ACTMODE_COMMENT:
                comment.reply(reply)
                print(' (replied to comment with more info) ', end='')
            #if ACTMODE & ACTMODE_PM:
            #    print(account.send_message(comment.author, 'Info Bot Information', reply))
            print('>', end='')
        except praw.errors.Forbidden as e:
            print('\nCannot reply. Bot forbidden:', e)
        except praw.errors.InvalidComment:
            print('\nComment was deleted while trying to reply.')
        except praw.errors.PRAWException as e:
            print('\nSome unspecified PRAW issue occured while trying to reply:', e)

        already_done.append(comment.id)
        comment.mark_as_read()
    print(' (%d comments)' % (count,))


def find_keywords(all_comments, account, config, user, subreddit_list, already_done):
    keyword_list = config['KEYWORDS']
    time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
    image_formats = config['IMAGE_FORMATS']
    extra_message = config['EXTRA_MESSAGE']
    information_reply = config['INFORMATION_REPLY']

    count = 0
    for comment in all_comments:
        count += 1
        if not _applicable_comment(comment, subreddit_list, time_limit_minutes):
            continue
        try:
            isPicture = any(i in str(comment.link_url) for i in image_formats)
        except UnicodeEncodeError:
            isPicture = False #non-ascii url
        if not isPicture:
            print('t', end='')
            continue
        body = comment.body.lower()
        if not any(word.lower() in body.lower() for word in keyword_list):
            print('p', end='')
            continue
        top_level = [i.replies for i in comment.submission.comments]
        submission_comments = []
        for i in top_level:
            for j in i:
                submission_comments.append(j)
        if any(i for i in submission_comments if extra_message in i.body): #If there are link replies
            print('R', end='')
            continue
        if not any(i for i in submission_comments if i.body == information_reply): #If there are information replies
            print('R', end='')
            continue
        print('\ndetected keyword: %s' % comment.body.lower())
        if comment.id in already_done:
            print('r', end='')
            continue
        if comment.author == user:
            print('u', end='')
            continue
        done = False
        attempt = 1
        while not done:
            try:
                done = reply_to_potential_comment(comment, account, config, already_done)
                print('>', end='')
            except praw.errors.RateLimitExceeded as e:
                print('submission rate exceeded! attempt %i' % attempt)
                print(e)
                time.sleep(30)

    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #print(' (%d comments - %s)' % (count, se))
    print(' (%d comments)' % (count,))

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
                    print('deleted comment: %s' % comment_id)
                #if ACTMODE & ACTMODE_PM:
                #    print('should delete comment: %s' % comment_id)
                if ACTMODE & ACTMODE_LOG:
                    print('would have deleted comment: %s' % comment_id)
        return current_time
    return start_time


def main(config, account1, account2, user, subreddit_list, comment_stream_urls):
    start_time = time.time()
    comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments

    already_done = []
    if os.path.isfile("already_done.p"):
        with open("already_done.p", "rb") as f:
            already_done = pickle.load(f)

    print('Starting run...')
    while True:
        try:
            for count, stream in enumerate(comment_stream_urls): #uses separate comment streams for large subreddit list due to URL length limit
                print('visiting comment stream %d/%d "%s..."' % (count+1, len(comment_stream_urls), str(stream)[:60]))
                a = time.time()
                feed_comments = stream.get_comments()
                #feed_comments = stream.get_comments(limit=None) # all
                if not feed_comments:
                    continue
                print(time.time()-a)
                find_keywords(feed_comments, account1, config, user, subreddit_list, already_done)
                print('finding username mentions: ', end='')
                find_username_mentions(account1, account2, config, user, subreddit_list, already_done)
                start_time = check_downvotes(user, start_time, comment_deleting_wait_time)

                with open("already_done.p", "wb") as df:
                    pickle.dump(already_done, df)

                print('Finished a round of comments. Waiting two seconds.\n')
                time.sleep(2)
        except requests.ConnectionError:
            print('Connection Error')
        except requests.HTTPError:
            print('HTTP Error')


def run():
    with open('config.json') as json_data:
        config = json.load(json_data)

    if 'BOT_WORKDIR' in config:
        ok, errmsg = chwd(config['BOT_WORKDIR'])
        if not ok:
            sys.exit(errmsg)
    else:
        print('No BOT_WORKDIR set, running in current directory.')

    # TODO: get a list from config
    #botmodes = config['BOT_MODE']
    botmodes = [config['MODE']]
    ACTMODE = ACTMODE_NONE
    for botmode in botmodes:
        botmode = botmode.lower()
        if botmode == 'comment':
            ACTMODE |= ACTMODE_COMMENT
        if botmode == 'pm':
            ACTMODE |= ACTMODE_PM
        if botmode == 'log':
            ACTMODE |= ACTMODE_LOG

    # force early cache-refreshing spamlists
    spamfilter_lists()

    (account1, account2, user, subreddit_list) = reddit_login(config)

    #account1 = account2 = user = subreddit_list = None
    #url = 'https://i.imgur.com/yZKXDPV.jpg'
    #url = 'http://i.imgur.com/mQ7Tuye.gifv'
    #print(give_more_info(url, config, account1, account2, display_limit=5))
    #sys.exit()

    print('Fetching comment stream urls')
    #comment_stream_urls = [account1.get_subreddit(subredditlist) for subredditlist in build_subreddit_feeds(subreddit_list)]
    comment_stream_urls = []
    for count, subredditlist in enumerate(build_subreddit_feeds(subreddit_list)):
        print('loading comment stream %2d "%s..."' % (count+1, subredditlist[:60]))
        comment_feed = account1.get_subreddit(subredditlist)
        # lazy objects, nothing done yet
        comment_stream_urls += [comment_feed]

    main(config, account1, account2, user, subreddit_list, comment_stream_urls)
