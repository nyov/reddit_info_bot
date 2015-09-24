#!/usr/bin/env python
from __future__ import print_function
import sys
import os
import logging
import time
import praw
import pickle
import urllib2
import cookielib
import BeautifulSoup
import requests
import re
import json
from requests import HTTPError,ConnectionError
from praw.errors import RateLimitExceeded
from parsel import Selector
import itertools
import random

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

def get_google_results(image_url, limit=15): #limit is the max number of results to grab (not the max to display)
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get('https://www.google.com/searchbyimage?image_url={0}'.format(image_url), headers=headers).content
    response_text += requests.get('https://www.google.com/searchbyimage?image_url={0}&start=10'.format(image_url), headers=headers).content
    #response_text = response_text[response_text.find('Pages that include'):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    print(len(response_text))
    print(response_text)
    list_class_results = tree.findAll(attrs={'class':'r'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].find('a')['href'],re.sub('<.*?>', '', re.sub('&#\d\d;', "'", ''.join([str(j) for j in list_class_results[i].find('a').contents])))) for i in xrange(limit)]
    return results

def get_bing_results(image_url, limit=15):
    cj = cookielib.MozillaCookieJar('cookies.txt')
    cj.load()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', config['SEARCH_USER_AGENT'])]
    response_text = opener.open("https://www.bing.com/images/searchbyimage?FORM=IRSBIQ&cbir=sbi&imgurl="+image_url).read()
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'sbi_sp'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].findAll(attrs={'class':'info'})[0].find('a')['href'],list_class_results[i].findAll(attrs={'class':'info'})[0].find('a').contents[0]) for i in xrange(limit)]
    return results

def get_yandex_results(image_url, limit=15):
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get("https://www.yandex.com/images/search?img_url={0}&rpt=imageview&uinfo=sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900".format(image_url), headers=headers).content
    response_text = response_text[response_text.find("Sites where the image is displayed"):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'link other-sites__title-link i-bem'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    results = []
    for a in list_class_results:
        a = str(a)
        b = "https:"+a[a.find('href="')+6:a.find('" target="')]
        filtered_link = re.compile(r'\b(amp;)\b', flags=re.IGNORECASE).sub("",b)
        try:
            redirect_url = urllib2.urlopen(filtered_link).geturl()
            text = a[a.find('"_blank">')+9:a.find('</a>')]
            results.append((redirect_url,text))
        except: pass #this site bands bots and cannot be accessed
    if limit >= len(results):
        limit = len(results)
    return results[:limit]

def get_karmadecay_results(image_url, limit=15):
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get("http://www.karmadecay.com/search?kdtoolver=b1&q="+image_url, headers=headers).content
    if "No very similar images were found." in response_text:
        return []
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(",i.find(']'))+1:i.find(")",i.find(']'))],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def get_tineye_results(image_url, limit=15):
    def extract(r, count):
        sel = Selector(text=r.content.decode(r.encoding))
        page = sel.xpath('//div[@class="results"]//div[@class="row matches"]//div[contains(@class, "match-row")]')
        if not page:
            raise IndexError('No search results')
        if 'Your IP has been blocked' in page:
            print('IP banned')
            raise IndexError('No search results')
        if '403 Forbidden' in page: # hmm, something else?
            raise IndexError('No search results')

        results = []
        for found in page:
            count -= 1
            if count < 0:
                break # stop after our search limit
            source_image = found.xpath('.//div[@class="match"]/p[contains(@class, "short-image-link")]/a/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[2]/text()').extract_first()
            source_link = found.xpath('.//div[@class="match"]/p[not(@class)]/a/@href').extract_first()
            source_title = found.xpath('.//div[@class="match"]/h4[@title]/text()').extract_first()
            #source_text = found.xpath('.//div[@class="match"]/p[@class="crawl-date"]/text()').extract_first()

            if source_image:
                source_image = os.path.basename(source_image)
                text = '{0} {1} on {2}'.format(source_image, source_image_size, source_title)
                results += [(source_link, text)]
        return results # [(link,text)]

    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response = requests.post("https://www.tineye.com/search", data={'url': image_url})

    results = extract(response, limit)
    limit = limit - len(results)
    if limit > 0: # try another page
        sel = Selector(text=response.content.decode(response.encoding))
        next_link = sel.xpath('//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if next_link:
            response = requests.get(response.url + '?page=2')
            results += extract(response, limit)

    return results


def get_domain(link):
    #result = re.search("http\w?:///?(\w+\..+\.\w*)/?|http\w?:///?(.+\.\w*)/?",link)
    result = re.search("http\w?:///?\w+\.[^/]+(\.\w*)/?|http\w?:///?[^/]+(\.\w*)/?",link)
    try:
        group = result.group(1) if result.group(1) else result.group(2)
    except:
        #"ERROR: get_domain("+link+") could not find a working domain. Attempting to skip..."
        group = link
    return group.decode('utf-8')

def get_nonspam_links(results):
    #comment the links on a post made by an alt account to see if they show up
    nonspam_links = []
    passed_domains = []
    for i in results:
        link = i[0].lower()
        text = i[1].lower()
        print(link)
        good_tld = ''.join(letter for letter in get_domain(link) if letter!='.') not in tld_blacklist
        #not_in_hard_list = not any(item in get_domain(link) for item in hard_blacklist)
        no_spamlinks_in_link = not any(j in link for j in link_filter)
        no_text_spam = not any(j in text for j in text_filter)
        print("Good tld: {0}\nNo spamlinks in link: {1}\nNo text spam: {2}\n".format(good_tld,no_spamlinks_in_link,no_text_spam))
        if len(link) < 6:
            print("Skipping invalid URL: {0}".format(link))
            continue
        if good_tld and no_spamlinks_in_link and no_text_spam:
            nonspam_links.append([i[0],i[1]])
            print(link + " IS CLEAN\n")
            # post link, check reddit blacklist
            submission = account1.get_submission(submission_id=config['SUBMISSION_ID'])
            submission.add_comment(link)
            print("posted: "+link+"\n")
        else:
            print(link + " IS SPAM\n")
    time.sleep(7)
    for msg in account2.get_unread(limit=40):
        if msg.body in [i[0] for i in nonspam_links]:
            passed_domains.append([i for i in nonspam_links if i[0]==msg.body][0])
            print("read:   " + msg.body)
            #print([i for i in nonspam_links if i[0]==msg.body][0])
        msg.mark_as_read()
    print("passed domains: "+ str(passed_domains))
    return passed_domains


def format_results(results, display_limit=5): #returns a formatted and spam filtered list of the results. Change 5 to adjust number of results to display per provider. Fi
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

    if account2:
        ascii_final = get_nonspam_links(ascii_filtered) #filter the links for spam
    else: # skip spamfilter, for testing only (FIXME)
        ascii_final = ascii_filtered
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
    extra_message = config["EXTRA_MESSAGE"]
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
        print("GOOGLE:")
        google_formatted = format_results(results[0])
    except IndexError as e:
        google_available = False
        print(e)

    try:
        print("BING:")
        bing_formatted = format_results(results[1])
    except IndexError:
        bing_available = False

    try:
        print("YANDEX:")
        yandex_formatted = format_results(results[2])
    except IndexError:
        yandex_available = False

    print("KARMA DECAY:")
    karmadecay_formatted = format_results(results[3])

    try:
        print("TINEYE:")
        tineye_results = get_tineye_results(submission_url)
        if tineye_results:
            tineye_formatted = format_results(tineye_results)
    except IndexError:
        tineye_available = False

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
    if not any((karmadecay_available, bing_available, google_available, yandex_available)):
        reply = "Well that's embarrassing.  Not for me, but for the search engines. \n\n I was not able to automatically find results for this link.  \n\n ^^If ^^this ^^is ^^a ^^.gifv ^^I ^^am ^^working ^^on ^^adding ^^them ^^to ^^searches."
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
    except HTTPError:
        done = True
        print('HTTP Error. Bot might be banned from this sub')
        already_done.append(comment.id)
    except RateLimitExceeded:
        print('submission rate exceeded! attempt %i'%attempt)
        time.sleep(30)
    return done

def find_username_mentions():
    for comment in account1.get_unread(limit=100):
        if config['SEARCH_STRING'] in comment.body:
            print("search string in body")
            if comment.author: #check if the comment exists
                print("comment.author")
                print(comment.subreddit)
                if str(comment.subreddit) in subreddit_list: #check if it's in one of the right subs
                    print("comment.subreddit")
                    if (time.time()-comment.created_utc)/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                        print("time")
                        try:
                            isPicture = any(i in str(comment.submission.url) for i in config['IMAGE_FORMATS'])
                        except UnicodeEncodeError:
                            isPicture = False #non-ascii url
                        if isPicture:
                            print("isPicture")
                            top_level = [i.replies for i in comment.submission.comments]
                            submission_comments = []
                            for i in top_level:
                                for j in i:
                                    submission_comments.append(j)
                            if not any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are no link replies
                                print("no link replies")
                                if comment.id not in already_done and comment.author != user:
                                    #print("not already done and not its own user")
                                    reply = give_more_info(comment.submission.url)
                                    try:
                                        if botmode == LOG:
                                            print(reply)
                                        else:
                                            if comment_exists(comment):
                                                comment.reply(reply)
                                                print('replied to comment with more info')
                                    except HTTPError:
                                        print('HTTP Error. Bot might be banned from this sub')

                                    already_done.append(comment.id)
        comment.mark_as_read()


def find_keywords(all_comments):
    keyword_list = config['KEYWORDS']
    for comment in all_comments:
        print(".", end="")
        if comment['author']: #check if the comment exists
            if comment['subreddit'] in subreddit_list: #check if it's in one of the right subs
                if (time.time()-comment['created_utc'])/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                    try:
                        isPicture = any(i in str(comment['link_url']) for i in config['IMAGE_FORMATS'])
                    except UnicodeEncodeError:
                        isPicture = False #non-ascii url
                    if isPicture:
                        body = comment['body'].lower()
                        if any(word.lower() in body.lower() for word in keyword_list):
                            comment = account1.get_submission(url="https://www.reddit.com/r/{0}/comments/{1}/aaaa/{2}".format(comment['subreddit'],comment['link_id'][3:],comment['id'])).comments
                            if comment: #get_submission returns a valid comment object
                                comment = comment[0]
                                top_level = [i.replies for i in comment.submission.comments]
                                submission_comments = []
                                for i in top_level:
                                    for j in i:
                                        submission_comments.append(j)
                                if not any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are no link replies
                                    if not any(i for i in submission_comments if i.body == config['INFORMATION_REPLY']): #If there are no information replies
                                        if any(word.lower() in comment.body.lower() for word in keyword_list):
                                            try:
                                                print("\ndetected keyword: "+ comment.body.lower())
                                            except UnicodeEncodeError:
                                                print("\ndetected keyword: ", end="")
                                                try:
                                                    print(comment.body)
                                                except: pass #print(''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2))
                                            if comment.id not in already_done and comment.author != user:
                                                done = False
                                                attempt = 1
                                                while not done:
                                                    done = reply_to_potential_comment(comment,attempt)

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

def get_filter(filter_type):
    def cache_filters(filter_type):
        try:
            response = urllib2.urlopen('http://spambot.rarchives.com/api.cgi?method=get_filters&start=0&count=3000&type={0}'.format(filter_type)).read()
            # test if the response is valid for us
            json.loads(response)['filters']
        except (urllib2.HTTPError, KeyError, Exception) as e:
            msg = 'Spamfilter update failed with error "{0}", using cached files (if available)'.format(str(e))
            print(msg)
        else:
            with open(filename, 'wb') as outf:
                outf.write(response)

    filename = 'spamfilter_{0}.json'.format(filter_type)
    if not os.path.isfile(filename) or \
            (int(time.time() - os.path.getmtime(filename)) > 43200): # cache 24 hours
        cache_filters(filter_type)
        if not os.path.isfile(filename):
            errmsg = "Could not load spam filters. Cached files invalid or Network failure."
            sys.exit(errmsg) # quick&ugly, sorry

    filters = None
    try:
        with open(filename, 'rb') as inf:
            filters = json.load(inf)['filters']
    except (ValueError, KeyError): # cached file contents invalid
        os.unlink(filename)
        # retry? potential loop
        #get_filter(filter_type)
        errmsg = "Could not load spam filters. Cached files invalid or Network failure."
        sys.exit(errmsg)

    return [i['spamtext'] for i in filters]

def get_comment_stream_urls(subreddit_list):
    MAX_LENGTH = 2010
    url_list = []
    subreddit_chain = ""
    for i in subreddit_list:
        new_element = i + "+"
        if len(subreddit_chain) + len(new_element) > MAX_LENGTH:
            url_list.append("https://reddit.com/r/{0}/comments.json".format(subreddit_chain[:-1]))
            subreddit_chain = ""
        subreddit_chain += new_element
    url_list.append("https://reddit.com/r/{0}/comments.json".format(subreddit_chain[:-1]))
    return url_list

def get_all_comments(stream):
    a = session_client.get(stream, headers=headers)
    try:
        js = json.loads(a.content)
        if not 'data' in js:
            return None
        b =  js['data']['children']
        comments_json = [i['data'] for i in b]
        return comments_json
    except ValueError:
        return None


with open('config.json') as json_data:
    config = json.load(json_data)

# startup

wd = None
if 'BOT_WORKDIR' in config:
    wd = config["BOT_WORKDIR"]
if wd: # If no BOT_WORKDIR was specified in the config, run in current dir
    if os.path.exists(wd):
        os.chdir(wd)
    else: # BOT_WORKDIR was requested, but does not exist. That's a failure.
        errmsg = "Requested BOT_WORKDIR '{0}' does not exist, aborting.".format(wd)
        sys.exit(errmsg)


blacklist = []
if os.path.isfile("blacklist.p"):
    with open("blacklist.p", "rb") as f:
        blacklist = pickle.load(f)
print('Adding Rarchives links to blacklist.')
rarchives_spam_domains = link_filter = get_filter('link') + get_filter('thumb')
text_filter = get_filter('text') + get_filter('user')
"""for domain in rarchives_spam_domains:
    if 'http' not in domain and domain[0] != '.':
        domain = "http://"+domain
    if not re.search('\.[^\.]+/.+$',domain): #if the link isn't to a specific page (has stuff after the final /) instead of an actual domain
        if domain[0] != '.':
            if domain not in blacklist:
                blacklist.append(domain)
"""
hard_blacklist = ["tumblr.com"]
#whitelist = ["reddit.com"]
tld_blacklist = [''.join(letter for letter in tld if letter!=".") for tld in get_filter('tld')]

COMMENT = 'comment'
PM = 'pm'
LOG = 'log'
botmode = config['MODE']
botmode = botmode.lower()

time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments

#url = 'https://i.imgur.com/yZKXDPV.jpg'
#print(give_more_info(url))
#sys.exit()

# login to reddit accounts

print('Logging into accounts')
account1 = praw.Reddit(config['BOT_NAME'])
account1.login(config['USER_NAME'], config['PASSWORD'], disable_warning=True) # drop the warning for now (working on it)

if config['SECOND_ACCOUNT_NAME'] and config['SECOND_ACCOUNT_PASS']:
    account2 = praw.Reddit(config['BOT_NAME']) #load a second praw instance for the second account (the one used to check the spam links)
    account2.login(config['SECOND_ACCOUNT_NAME'], config['SECOND_ACCOUNT_PASS'], disable_warning=True)
else:
    account2 = False

user = account1.get_redditor(config['USER_NAME'])
already_done = []
if os.path.isfile("already_done.p"):
    with open("already_done.p", "rb") as f:
        already_done = pickle.load(f)
start_time = int(time.time()/60) #time in minutes for downvote checking

print('Fetching Subreddit list')
subreddit_list = [account1.get_subreddit(i).display_name for i in config['SUBREDDITS']]
#load the word list:
bad_words = get_filter('text')

credentials = {
    'user': config["USER_NAME"],
    'passwd': config["PASSWORD"],
    'api_type': 'json',
}
headers = {'user-agent': config["BOT_NAME"],}
session_client = requests.session()
r1 = session_client.post('https://www.reddit.com/api/login', data = credentials, headers=headers)
the_json = json.loads(r1.text)
session_client.modhash = the_json['json']['data']['modhash']

print('Fetching comment stream urls')
comment_stream_urls = get_comment_stream_urls(subreddit_list)


def main():
    start_time = time.time()
    print('Starting run...')
    while True:
        try:
            for stream in comment_stream_urls: #uses separate comment streams for large subreddit list due to URL length limit
                a = time.time()
                all_comments = get_all_comments(stream)
                if not all_comments:
                    continue
                print(time.time()-a)
                find_keywords(all_comments)
                print("finding username mentions...")
                find_username_mentions()
                start_time = check_downvotes(user,start_time)

                with open("already_done.p", "wb") as df:
                    pickle.dump(already_done, df)
                with open("blacklist.p", "wb") as bf:
                    pickle.dump(blacklist, bf)

                print('Finished a round of comments. Waiting two seconds.\n')
                time.sleep(2)
        except ConnectionError:
            print('Connection Error')
        except HTTPError:
            print('HTTP Error')


if __name__ == "__main__":

    main()
