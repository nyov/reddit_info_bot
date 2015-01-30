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

def get_karmadecay_results(image, limit=15):
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get("http://www.karmadecay.com/search?kdtoolver=b1&q="+image, headers=headers).content
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(")+1:i.find(")")],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def check_spam(link): #True if the link is spam
    print "trying " + link
    domain =  re.search("http://\w.*\.\w.+\.\w*/|http://\w.+\.\w*/",link).group().decode('utf-8')
    submission = r.get_submission(submission_id='2rwpxt')
    submission.add_comment(domain)
    print "adding comment"
    max_tries = 5
    #user2.get_submission(submission_id='2rwpxt')
    for i in xrange(max_tries): #it will keep checking if the link shows up for max_tries
        time.sleep(1)
        done = False
        start_time = time.time()
        while not done:
            done = True
            try:
                #headers = {}
                #headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
                #submission_html = requests.get("http://www.reddit.com/r/nagasgura/comments/2rwpxt/infobot_spam_tester/?sort=new", headers=headers).content.decode('utf-8')
                submission_html = urllib2.urlopen("http://www.reddit.com/r/nagasgura/comments/2rwpxt/infobot_spam_tester/?sort=new?"+str(random.randint(100000,1000000))).read().decode('utf-8')
            except:
                print "error in spam checker!"
                i-=1
                time.sleep(2)
                done = False
        print time.time()-start_time

        #comments = [c.body for c in user2.get_submission(submission_id='2rwpxt').comments]
        print domain
        if domain in submission_html:
            print domain + " is clean! " + str(i+1) + "try."
            return False,domain
    print domain + " is spam!"
    return True,domain

def get_nonspam_links(results):
    #First, PM the links to the alt account
    for i in results:
        link = i[0]
        print link
        domain =  re.search("http\w?://\w.*\.\w.+\.\w*/|http://\w.+\.\w*/",link).group().decode('utf-8')
        r.send_message('bottester1234','Link Test',domain)
        print "sent: "+domain
    time.sleep(2)
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
    print nonspam_links
    return nonspam_links

def format_results(results):
    ascii = [[''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2)] for i in results] #eliminates non-ascii characters
    #filter the links and words.
    ascii_filtered = []
    for i in ascii:
        if not any(j in i[1] for j in bad_words):
            ascii_filtered.append(i)
            """
            if any(j in i[0] for j in approved_links):
                ascii_filtered.append(i)
            elif not any(j in i[0] for j in bad_links+other_bad_links): #if it doesn't match with the spam lists
                spam_results = check_spam(i[0])
                if spam_results[0]: #the link didn't show up
                    #bad_links.append(spam_results[1])
                    pass

                else: #the link isn't spam
                    approved_links.append(spam_results[1])
                    ascii_filtered.append(i)
            """
    ascii_final = get_nonspam_links(ascii_filtered)
    if len(ascii_final) > 5:
        ascii_final = ascii_final[:5]
    linkified = ["["+i[1]+"]("+i[0]+")" for i in ascii_final] #reformats the results into markdown links
    formatted = ''.join(i for i in '\n\n'.join(linkified))
    return formatted

def give_more_info(comment):
    extra_message = config["EXTRA_MESSAGE"]
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

use_keywords = config['USE_KEYWORDS']

keyword_list = config['KEYWORDS']
time_limit_minutes = config['TIME_LIMIT_MINUTES'] #how long before a comment will be ignored for being too old
comment_deleting_wait_time = config["DELETE_WAIT_TIME"] #how many minutes to wait before deleting downvoted comments
r = praw.Reddit(config['BOT_NAME'])
r.login(config['USER_NAME'],config['PASSWORD'])

r2 = praw.Reddit(config['BOT_NAME'])
r2.login('bottester1234','bottester1234')

user = r.get_redditor(config['USER_NAME'])
already_done = pickle.load(open("already_done.p", "rb"))
start_time = int(time.time()/60) #time in minutes for downvote checking

nagasgura = r.get_subreddit("nagasgura")
subreddit_list = [r.get_subreddit(i).display_name for i in config['SUBREDDITS']]
#check_spam(r,"http://www.hdfsfwedv.com/hello")
bad_words = get_filter('text')
bad_links = pickle.load(open("bad_links.p","rb")) #from the file
other_bad_links = get_filter('link') #from the online spam list
approved_links = pickle.load(open("approved_links.p","rb"))

while True:
    try:
        all_comments = r.get_comments(subreddit = r.get_subreddit('all'),limit = None)
        parse_comments(all_comments)
        start_time = check_downvotes(user,start_time)

        pickle.dump(already_done, open("already_done.p", "wb"))
        pickle.dump(bad_links, open("bad_links.p", "wb"))
        pickle.dump(bad_links, open("approved_links.p", "wb"))

        print 'Finished a round of comments. Waiting two seconds.\n'
        time.sleep(2)
    except ConnectionError:
        print 'Connection Error'
    except HTTPError:
        print 'HTTP Error'
main()
