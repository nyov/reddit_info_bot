#!/usr/bin/python
# -*- coding: utf-8 -*-
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
from praw.errors import RateLimitExceeded

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
from .reddit import reddit_login
from .antispam import spamfilter_lists
from .util import domain_suffix, tld_from_suffix

logger = logging.getLogger(__name__)

# mock objects to emulate praw interface
class submission:
    def __init__(self,link):
        self.url = link

class comment:
    def __init__(self,link):
        self.submission = submission(link)
        self.id = "dummy comment"
    def reply(self,text):
        print(text)


def isspam(result):
    """check search result for spammy content
    """
    url, text = result[0].lower(), result[1].lower()

    if len(url) < 6: # shorter than '//a.bc' can't be a useable absolute HTTP URL
        print('Skipping invalid URL: {0}'.format(url))
        return True
    # domain from URL using publicsuffix (not a validator)
    domain = domain_suffix(url)
    if not domain:
        print('Failed to lookup PSL/Domain for: {0}'.format(url))
        return True
    tld = tld_from_suffix(domain)
    if not tld or tld == '':
        print('Failed to lookup TLD from publicsuffix for: {0}'.format(url))
        return True
    if tld in tld_blacklist:
        print('Skipping blacklisted TLD "{0}": {1}'.format(tld, url))
        return True
    if domain in hard_blacklist:
        print('Skipping blacklisted Domain "{0}": {1}'.format(domain, url))
        return True
    if any(j in url for j in link_filter):
        # TODO, return hit
        print('Skipping spammy link match "{0}": {1}'.format(domain, url))
        return True
    if any(j in text for j in text_filter):
        # TODO, return hit
        print('Skipping spammy text match: "{1}"'.format(text))
        return True
    # no spam, result is good
    return False

def reddit_msg_linkfilter(results, sending_account, receiving_account, submission_id):
    """comment the links on a post made by an alt account to see if they show up
    """
    queue_url, queue_work = [], []
    submission = sending_account.get_submission(submission_id)
    # post links with first account
    for result in results:
        # post link to check against reddit blacklist
        url = result[0].lower()
        try:
            submission.add_comment(url)
        except Exception as e:
            print('reddit_msg_linkfilter Failed to post url "%s"' % (url,))
            print(e)
            # FIXME: check exception for http errors (retry?) or other (spam?)
            continue
        queue_url += [url]
        queue_work += [result]
    time.sleep(7) # wait a bit
    # fetch posted links from second account
    verified_results = []
    urlcheck_messages = receiving_account.get_unread(limit=40)
    for msg in urlcheck_messages:
        if msg.body in queue_url:
            idx = queue_url.index(msg.body)
            url = queue_url.pop(idx)
            result = queue_work.pop(idx)
            assert url == result[0], 'queue_url and queue_work were not in sync (%s != %s)' % (url, result[0])
            msg.mark_as_read()
            verified_results += [result]
        else:
            print('skipping unknown message "%s"' % msg.body)
    failed_results = [r for r in results if r not in verified_results]
    if failed_results:
        print('reddit_msg_linkfilter failed links: %s' % ','.join([str(url) for url, text in failed_results]))
    return verified_results

def _format_results(results, display_limit=5): #returns a formatted and spam filtered list of the results. Change 5 to adjust number of results to display per provider. Fi
    ascii = [[''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2)] for i in results] #eliminates non-ascii characters
    #filter the links and words.
    ascii_filtered = []
    ASCII = ''.join(chr(x) for x in range(128))
    for i in ascii:
        text = ""
        for char in i[1]:
            if char in ASCII and char not in "\)([]^/":
                text += char
        ascii_filtered.append([i[0],text])

    # filter results for spam
    ascii_final = [result for result in ascii_filtered if not isspam(result)]
    if account2:
        # do reddit msg spamcheck
        ascii_final = reddit_msg_linkfilter(ascii_final, account2, account1, config['SUBMISSION_ID'])
    if len(ascii_final) > display_limit:
        ascii_final = ascii_final[:display_limit] #limit the list to 5 items
    linkified = ["["+i[1]+"]("+i[0]+")" for i in ascii_final] #reformats the results into markdown links
    formatted = ''.join(i for i in '\n\n'.join(linkified))
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

def give_more_info(submission_url):
    extra_message = config['EXTRA_MESSAGE']
    no_results_message = config['NO_SEARCH_RESULTS_MESSAGE']
    google_available = True
    bing_available = True
    karmadecay_available = True
    yandex_available = True
    tineye_available = True

    google_formatted = []
    bing_formatted = []
    karmadecay_formatted = []
    yandex_formatted = []
    tineye_formatted = []
    link = re.sub("/","*", submission_url)
    print(link)
    print('searching')
    results = ''
    i = 0
    while not results:
        i += 1
        try:
            response = urllib2.urlopen("https://sleepy-tundra-5659.herokuapp.com/search/"+link).read()
            results = eval(response)
        except urllib2.HTTPError:
            print("503 Service Unavailable. Retrying "+str(i))

    try:
        print('GOOGLE:')
        google_formatted = _format_results(results[0])
    except IndexError as e:
        google_available = False
        print('GOOGLE error:', e)

    try:
        print('BING:')
        bing_formatted = _format_results(results[1])
    except IndexError as e:
        bing_available = False
        print('BING error:', e)

    try:
        print('YANDEX:')
        yandex_formatted = _format_results(results[2])
    except IndexError as e:
        yandex_available = False
        print('YANDEX error:', e)

    try:
        print('KARMA DECAY:')
        karmadecay_formatted = _format_results(results[3])
    except IndexError as e:
        karmadecay_available = False
        print('KARMA DECAY error:', e)

    try:
        print('TINEYE:')
        tineye_results = get_tineye_results(submission_url, config)
        if tineye_results:
            tineye_formatted = _format_results(tineye_results)
    except IndexError as e:
        tineye_available = False
        print('TINEYE error:', e)

    if not tineye_formatted:
        tineye_available = False
    if not karmadecay_formatted:
        karmadecay_available = False
    if not yandex_formatted:
        yandex_available = False
    if not bing_formatted:
        bing_available = False
    if not google_formatted:
        google_available = False

    google_message = "**Best Google Guesses**\n\n{0}\n\n"
    bing_message = "**Best Bing Guesses**\n\n{0}\n\n"
    yandex_message = "**Best Yandex Guesses**\n\n{0}\n\n"
    karmadecay_message = "**Best Karma Decay Guesses**\n\n{0}\n\n"
    tineye_message = "**Best Tineye Guesses**\n\n{0}\n\n"
    available_dict = {"google":google_available, "bing":bing_available, "karmadecay":karmadecay_available, "yandex":yandex_available, "tineye":tineye_available}
    searchengine_dict = {"google":(google_message, google_formatted), "karmadecay":(karmadecay_message,karmadecay_formatted), "bing":(bing_message, bing_formatted), "yandex":(yandex_message, yandex_formatted), "tineye":(tineye_message, tineye_formatted)}
    reply = ""
    if not any((karmadecay_available, bing_available, google_available, yandex_available, tineye_available)):
        reply = no_results_message
    else:
        for availability in ("google", "bing", "yandex", "karmadecay", "tineye"):
            #for each search engine, add the results if they're available, otherwise say there are no links from that search engine.
            if available_dict[availability]:
                reply += searchengine_dict[availability][0].format(searchengine_dict[availability][1]) #0: message; 1: formatted results
            else:
                reply += searchengine_dict[availability][0].format("No available links from this search engine found.")
    reply += extra_message
    return reply

#
# Bot actions
#

def reply_to_potential_comment(comment,attempt): #uncomment 'return true' to disable this feature
    if (not config['USE_KEYWORDS']):
        return True
    if not any(i in str(comment.submission.url) for i in config['IMAGE_FORMATS']):
        return True
    done = False
    try:
        reply = config["INFORMATION_REPLY"]
        if botmode == COMMENT:
            if comment_exists(comment):
                comment.reply(reply)
        elif botmode == LOG:
            print(reply)
        elif botmode == PM:
             print(account1.send_message(comment.author, 'Info Bot Information', reply))
        print("replied to potential comment: {0}".format(comment.body))
        done = True
        already_done.append(comment.id)
    except requests.HTTPError:
        done = True
        print('HTTP Error. Bot might be banned from this sub')
        already_done.append(comment.id)
    except RateLimitExceeded:
        print('submission rate exceeded! attempt %i'%attempt)
        time.sleep(30)
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
        reply = give_more_info(comment.submission.url)
        try:
            if botmode == LOG:
                print(reply)
            else:
                if comment_exists(comment):
                    comment.reply(reply)
                    print('replied to comment with more info', end='')
            print('.', end='')
        except requests.HTTPError:
            print('HTTP Error. Bot might be banned from this sub')

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
        # previously determined already
        #if any(word.lower() in comment.body.lower() for word in keyword_list):
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
            done = reply_to_potential_comment(comment, attempt)
    #se = '/'.join(['%d %s' % (v, k) for k, v in stats])
    #print(' (%d comments - %s)' % (count, se))
    print(' (%d comments)' % (count,))

def check_downvotes(user, start_time):
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 1:
                comment.delete()
                print('deleted a comment')
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
                start_time = check_downvotes(user,start_time)

                with open("already_done.p", "wb") as df:
                    pickle.dump(already_done, df)
                with open("blacklist.p", "wb") as bf:
                    pickle.dump(blacklist, bf)

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
    if wd: # If no BOT_WORKDIR was specified in the config, run in current dir
        if os.path.exists(wd):
            os.chdir(wd)
        else: # BOT_WORKDIR was requested, but does not exist. That's a failure.
            errmsg = "Requested BOT_WORKDIR '{0}' does not exist, aborting.".format(wd)
            sys.exit(errmsg)

    COMMENT = 'comment'
    PM = 'pm'
    LOG = 'log'
    botmode = config['MODE']
    botmode = botmode.lower()

    time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
    comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments

    # load spam lists
    (
        link_filter,
        text_filter,
        word_filter,
        hard_blacklist,
        whitelist,
        tld_blacklist,
        blacklist,
    ) = spamfilter_lists()

    already_done = []
    if os.path.isfile("already_done.p"):
        with open("already_done.p", "rb") as f:
            already_done = pickle.load(f)

    #account2 = None
    #url = 'https://i.imgur.com/yZKXDPV.jpg'
    #print(give_more_info(url))

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
