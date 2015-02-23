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
import itertools
import random

def get_google_results(submission, limit=15): #limit is the max number of results to grab (not the max to display)
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get('http://www.google.com/searchbyimage?image_url={0}'.format(image), headers=headers).content
    #response_text = response_text[response_text.find('Pages that include'):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'r'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].find('a')['href'],re.sub('<.*?>', '', re.sub('&#\d\d;', "'", ''.join([str(j) for j in list_class_results[i].find('a').contents])))) for i in xrange(limit)]
    return results

def get_bing_results(submission, limit=15):
    image = submission.url
    cj = cookielib.MozillaCookieJar('cookies.txt')
    cj.load()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
    response_text = opener.open("https://www.bing.com/images/searchbyimage?FORM=IRSBIQ&cbir=sbi&imgurl="+image).read()
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'sbi_sp'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].findAll(attrs={'class':'info'})[0].find('a')['href'],list_class_results[i].findAll(attrs={'class':'info'})[0].find('a').contents[0]) for i in xrange(limit)]
    return results

def get_karmadecay_results(submission, limit=15):
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get("http://www.karmadecay.com/search?kdtoolver=b1&q="+image, headers=headers).content
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(")+1:i.find(")")],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def get_nonspam_links(results):
    #comment the links on a post made by an alt account to see if they show up
    for i in results:
        link = i[0]
        print link
        domain =  re.search("http\w?://\w.*\.\w.+\.\w*/|http://\w.+\.\w*/",link).group().decode('utf-8')
        submission = r.get_submission(submission_id=submission_id)
        submission.add_comment(domain)
        print "posted: "+domain
    passed_domains = []
    for msg in r2.get_unread(limit=15):
        passed_domains.append(msg.body)
        msg.mark_as_read()
    nonspam_links = []
    for i in results:
        text = i[1]
        link = i[0]
        print "checking "+link
        domain =  re.search("http\w?://\w.*\.\w.+\.\w*/|http://\w.+\.\w*/",link).group().decode('utf-8')
        if domain in passed_domains:
            nonspam_links.append([i[0],i[1]])
            print link + " IS CLEAN"
        else:
            print link + " IS SPAM"
    print nonspam_links
    return nonspam_links

def format_results(results): #returns a formatted and spam filtered list of the results
    ascii = [[''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2)] for i in results] #eliminates non-ascii characters
    #filter the links and words.
    ascii_filtered = []
    for i in ascii:
        if not any(j in i[1] for j in bad_words):
            ascii_filtered.append(i)

    ascii_final = get_nonspam_links(ascii_filtered) #filter the links for spam
    if len(ascii_final) > 5:
        ascii_final = ascii_final[:5] #limit the list to 5 items
    linkified = ["["+i[1]+"]("+i[0]+")" for i in ascii_final] #reformats the results into markdown links
    formatted = ''.join(i for i in '\n\n'.join(linkified))
    return formatted

def give_more_info(comment):
    extra_message = config["EXTRA_MESSAGE"]
    google_available = True
    bing_available = True
    karmadecay_available = True
    try:
        google_formatted = format_results(get_google_results(comment.submission))
    except IndexError:
        google_available = False
    try:
        bing_formatted = format_results(get_bing_results(comment.submission))
    except IndexError:
        bing_available = False
    try:
        karmadecay_formatted = ""
        #karmadecay_formatted = format_results(get_karmadecay_results(comment.submission))
    except IndexError:
        karmadecay_available = False

    google_message = "**Best Google Guesses**\n\n{0}\n\n"
    bing_message = "**Best Bing Guesses**\n\n{0}\n\n"
    karmadecay_message = "**Best Karma Decay Guesses**\n\n{0}\n\n"

    reply = ""
    if google_available:
        reply += google_message.format(google_formatted)
    if bing_available:
        reply += bing_message.format(bing_formatted)
    if karmadecay_available:
        reply += karmadecay_message.format(karmadecay_formatted)
    if not all((karmadecay_available, bing_available, google_available)):
        reply = "Sorry, no information is available for this link."

    try:
        reply += extra_message
        comment.reply(reply)
        print 'replied to comment with more info'
    except HTTPError:
        print 'HTTP Error. Bot might be banned from this sub'

def reply_to_potential_comment(comment,attempt): #uncomment 'return true' to disable this feature
    if (not use_keywords):
        return True
    if not any(i in str(comment.submission.url) for i in ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png']):
        return True
    done = False
    try:
        reply = config["INFORMATION_REPLY"]
        if mode == COMMENT:
            comment.reply(reply)
        elif mode == LOG:
            print reply
        elif mode == PM:
             print r.send_message(comment.author, 'Info Bot Information', reply)
        print "replied to potential comment: {0}".format(comment.body)
        done = True
        already_done.append(comment.id)
    except HTTPError:
        done = True
        print 'HTTP Error. Bot might be banned from this sub'
        already_done.append(comment.id)
    except RateLimitExceeded:
        print 'submission rate exceeded! attempt %i'%attempt
        time.sleep(30)
    return done

def parse_comments(all_comments):
    SEARCH_STRING = config["SEARCH_STRING"]
    for comment in all_comments:
        print ".",
        if comment.author: #check if the comment exists
            if comment.subreddit.display_name in subreddit_list: #check if it's in one of the right subs
                if (time.time()-comment.created_utc)/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                    if any(i in str(comment.submission.url) for i in ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png']):
                        top_level = [i.replies for i in comment.submission.comments]
                        submission_comments = []
                        for i in top_level:
                            for j in i:
                                submission_comments.append(j)
                        if not any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are no link replies
                            if re.search('{0}$|{0}\s'.format(SEARCH_STRING),comment.body.lower()) and comment.id not in already_done and comment.author != user:
                                give_more_info(comment)
                                already_done.append(comment.id)
                            elif not any(i for i in submission_comments if i.body == config['INFORMATION_REPLY']): #If there are no information replies
                                if any(word.lower() in comment.body.lower() for word in keyword_list):
                                    if comment.id not in already_done and comment.author != user:
                                        done = False
                                        attempt = 1
                                        while not done:
                                            done = reply_to_potential_comment(comment,attempt)
    print

def check_downvotes(user,start_time):
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 0:
                comment.delete()
                print 'deleted a comment'
        return current_time
    return start_time

def get_filter(filter_type):
    filters=json.load(urllib2.urlopen('http://spambot.rarchives.com/api.cgi?method=get_filters&start=0&count=2000&type={0}'.format(filter_type)))['filters']
    return [i['spamtext'] for i in filters]

def main():
    pass
with open('config.json') as json_data:
    config = json.load(json_data)

COMMENT = 'comment'
PM = 'PM'
LOG = 'log'
mode = config['MODE']
submission_id = config['SUBMISSION_ID']

use_keywords = config['USE_KEYWORDS']

keyword_list = config['KEYWORDS']
time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments
r = praw.Reddit(config['BOT_NAME'])
r.login(config['USER_NAME'],config['PASSWORD'])

r2 = praw.Reddit(config['BOT_NAME']) #load a second praw instance for the second account (the one used to check the spam links)
r2.login(config['SECOND_ACCOUNT_NAME'],config['SECOND_ACCOUNT_PASS'])

user = r.get_redditor(config['USER_NAME'])
already_done = pickle.load(open("already_done.p", "rb"))
start_time = int(time.time()/60) #time in minutes for downvote checking

subreddit_list = [r.get_subreddit(i).display_name for i in config['SUBREDDITS']]
#load the word list:
bad_words = get_filter('text')

while True:
    try:
        all_comments = r.get_comments(subreddit = r.get_subreddit('all'),limit = None)
        parse_comments(all_comments)
        start_time = check_downvotes(user,start_time)

        pickle.dump(already_done, open("already_done.p", "wb"))

        print 'Finished a round of comments. Waiting two seconds.\n'
        time.sleep(2)
    except ConnectionError:
        print 'Connection Error'
    except HTTPError:
        print 'HTTP Error'
