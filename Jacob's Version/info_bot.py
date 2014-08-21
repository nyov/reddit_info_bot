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

def get_google_results(submission, limit=5): #limit is the max number of results to display
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get('http://www.google.com/searchbyimage?image_url={0}'.format(image), headers=headers).content
    response_text = response_text[response_text.find('Pages that include'):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'r'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].find('a')['href'],re.sub('<.*?>', '', re.sub('&#\d\d;', "'", ''.join([str(j) for j in list_class_results[i].find('a').contents])))) for i in xrange(limit)]
    return results

def get_bing_results(submission, limit=5):
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

def format_results(results):
    ascii = [[''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2)] for i in results] #eliminates non-ascii characters
    #filter the links and words.
    ascii_filtered = []
    for i in ascii:
        if not any(j in i[1] for j in bad_words):
            if not any(j in i[0] for j in bad_links):
                ascii_filtered.append(i)
    linkified = ["["+i[1]+"]("+i[0]+")" for i in ascii_filtered] #reformats the results into markdown links
    formatted = ''.join(i for i in '\n\n'.join(linkified))
    return formatted

def give_more_info(comment):
    extra_message = extra_message = "\n\n ***** \n ^^[Suggestions](http://www.reddit.com/message/compose/?to=info_bot&subject=Suggestion) ^^| ^^[FAQs](http://www.reddit.com/r/info_bot/comments/2cc45a/info_bot_info/) ^^| ^^[Issues](http://www.reddit.com/message/compose/?to=info_bot&subject=Issue) \
    \n ^^Downvoted ^^comments ^^from ^^info_bot ^^are ^^automagically ^^removed."
    google_available = True
    bing_available = True
    try:
        google_formatted = format_results(get_google_results(comment.submission))
    except IndexError:
        google_available = False
    try:
        bing_formatted = format_results(get_bing_results(comment.submission))
    except IndexError:
        bing_available = False
    if google_available and bing_available:
        reply = "**Best Google Guesses:**\n\n{0}\n\n**Best Bing Guesses:**\n\n{1}".format(google_formatted,bing_formatted)
    elif google_available:
        reply = "**Best Google Guesses:**\n\n{0}".format(google_formatted)
    elif bing_available:
        reply = "**Best Bing Guesses:**\n\n{0}".format(bing_formatted)
    else:
        reply = "Sorry, no information is available for this link."
    try:
        reply += extra_message
        comment.reply(reply)
        print 'replied to comment with more info'
    except HTTPError:
        print 'HTTP Error. Bot might be banned from this sub'

def reply_to_potential_comment(comment,attempt): #uncomment 'return true' to disable this feature
    #return True
    done = False
    try:
        comment.reply('It appears that you are looking for more information.\n\nObtain more information by replying to this comment with the phrase "more info info_bot"')
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
    SEARCH_STRING = 'u/info_bot'
    for comment in all_comments:
        if comment.author:
            if (time.time()-comment.created)/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                top_level = [i.replies for i in comment.submission.comments]
                submission_comments = []
                for i in top_level:
                    for j in i:
                        submission_comments.append(j)
                if not any(i for i in submission_comments if i.author == user): #If it hasn't already posted in this thread
                    if re.search('{0}$|{0}\s'.format(SEARCH_STRING),comment.body.lower()) and comment.id not in already_done and comment.author != user:
                        give_more_info(comment)
                        already_done.append(comment.id)
                    elif any(word.lower() in comment.body.lower() for word in keyword_list):
                        if comment.id not in already_done and comment.author != user:
                            done = False
                            attempt = 1
                            while not done:
                                done = reply_to_potential_comment(comment,attempt)

def check_downvotes(user,start_time):
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=100)
        for comment in my_comments:
            if comment.score < 0:
                comment.delete()
                print 'deleted a comment'
        return current_time
    return start_time


keyword_list = ["what is this",
                "I want more info",
                "/u/info_bot",
                "what is that",
                "more info please",
                "where is this",
                "who is this"]

with open('config.json') as json_data:
    config = json.load(json_data)

time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
comment_deleting_wait_time = 30 #how many minutes to wait before deleting downvoted comments
r = praw.Reddit('Info Bot')
r.login(config['USER_NAME'],config['PASSWORD'])
user = r.get_redditor(config['USER_NAME'])
already_done = pickle.load(open("already_done.p", "rb"))
start_time = int(time.time()/60) #time in minutes for downvote checking

with open('words') as raw_words:
    bad_words = raw_words.read().split('\n')
with open('links') as raw_links:
    bad_links = raw_links.read().split('\n')

while True:
    try:
        all_comments = r.get_comments(subreddit = r.get_subreddit('nagasgura'),limit = None)
        parse_comments(all_comments)
        start_time = check_downvotes(user,start_time)
        pickle.dump(already_done, open("already_done.p", "wb"))
        print 'Finished a round of comments. Waiting two seconds.\n'
        time.sleep(2)
    except ConnectionError:
        print 'Connection Error'
    except HTTPError:
        print 'HTTP Error'


