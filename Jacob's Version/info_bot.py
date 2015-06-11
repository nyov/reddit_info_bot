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

class submission:
	def __init__(self,link):
		self.url = link

class comment:
	def __init__(self,link):
		self.submission = submission(link)
		self.id = "dummy comment"
	def reply(self,text):
		print text

def get_google_results(submission, limit=15): #limit is the max number of results to grab (not the max to display)
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get('http://www.google.com/searchbyimage?image_url={0}'.format(image), headers=headers).content
    response_text += requests.get('http://www.google.com/searchbyimage?image_url={0}&start=10'.format(image), headers=headers).content
    #response_text = response_text[response_text.find('Pages that include'):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    print len(response_text)
    print response_text
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

def get_yandex_results(submission, limit=15):
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get("https://www.yandex.com/images/search?img_url={0}&rpt=imageview&uinfo=sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900".format(image), headers=headers).content
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

def get_karmadecay_results(submission, limit=15):
    image = submission.url
    headers = {}
    headers['User-Agent'] = "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.27 Safari/537.17"
    response_text = requests.get("http://www.karmadecay.com/search?kdtoolver=b1&q="+image, headers=headers).content
    if "No very similar images were found." in response_text:
        return []
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(",i.find(']'))+1:i.find(")",i.find(']'))],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def get_domain(link):
    result = re.search("http\w?:///?(\w+\..+\.\w*)/?|http\w?:///?(.+\.\w*)/?",link)
    try:
        group = result.group(1) if result.group(1) else result.group(2)
    except:
        #"ERROR: get_domain("+link+") could not find a working domain. Attempting to skip..."
        group = link
    return group.decode('utf-8')

def get_tld(link):
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
        print link
        good_tld = ''.join(letter for letter in get_tld(link) if letter!='.') not in tld_blacklist
        #not_in_hard_list = not any(item in get_domain(link) for item in hard_blacklist)
        no_spamlinks_in_link = not any(j in link for j in link_filter)
        no_text_spam = not any(j in text for j in text_filter)
        print "Good tld: {0}\nNo spamlinks in link: {1}\nNo text spam: {2}\n".format(good_tld,no_spamlinks_in_link,no_text_spam)
        if good_tld and no_spamlinks_in_link and no_text_spam:
            nonspam_links.append([i[0],i[1]])
            print link + " IS CLEAN\n"
            submission = r.get_submission(submission_id=submission_id)
            if len(link) > 5:
                submission.add_comment(link)
            	print "posted: "+link+"\n"
            else:
            	print "link is NOT!!!!"
        else:
            print link + " IS SPAM\n"
    time.sleep(7)
    for msg in r2.get_unread(limit=40):
        if msg.body in [i[0] for i in nonspam_links]:
            passed_domains.append([i for i in nonspam_links if i[0]==msg.body][0])
            print "read:   " + msg.body
            #print [i for i in nonspam_links if i[0]==msg.body][0]
        msg.mark_as_read()
    print "passed domains: "+ str(passed_domains)
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

    ascii_final = get_nonspam_links(ascii_filtered) #filter the links for spam
    if len(ascii_final) > display_limit:
        ascii_final = ascii_final[:display_limit] #limit the list to 5 items
    linkified = ["["+i[1]+"]("+i[0]+")" for i in ascii_final] #reformats the results into markdown links
    formatted = ''.join(i for i in '\n\n'.join(linkified))
    return formatted

def comment_exists(comment):
    return True
    try:
        if r.get_info(thing_id = comment.id):
            return True
    except:
        pass
    print 'Comment was deleted'
    return False

def give_more_info(comment):
    extra_message = config["EXTRA_MESSAGE"]
    google_available = True
    bing_available = True
    karmadecay_available = True
    yandex_available = True

    google_formatted = []
    bing_formatted = []
    karmadecay_formatted = []
    yandex_formatted = []
    link = re.sub("/","*",comment.submission.url)
    print link
    results = ''
    i = 0
    while not results:
        i += 1
        try:
            results = eval(urllib2.urlopen("https://sleepy-tundra-5659.herokuapp.com/search/"+link).read())
        except urllib2.HTTPError:
            print "503 Service Unavailable. Retrying "+str(i)

    try:
    	print "GOOGLE:"
        google_formatted = format_results(results[0])
    except IndexError,e:
        google_available = False
        print e

    try:
    	print "BING:"
        bing_formatted = format_results(results[1])
    except IndexError:
        bing_available = False

    try:
    	print "YANDEX:"
        yandex_formatted = format_results(results[2])
    except IndexError:
        yandex_available = False

    print "KARMA DECAY:"
    karmadecay_formatted = format_results(results[3])

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
    available_dict = {"google":google_available, "bing":bing_available, "karmadecay":karmadecay_available, "yandex":yandex_available}
    searchengine_dict = {"google":(google_message, google_formatted), "karmadecay":(karmadecay_message,karmadecay_formatted), "bing":(bing_message, bing_formatted), "yandex":(yandex_message, yandex_formatted)}
    reply = ""
    if not any((karmadecay_available, bing_available, google_available, yandex_available)):
        reply = "Sorry, the bot was not able to automatically find results for this link. \n\n We'll try to find it manually and comment back.  Results may be delayed."
    else:
        for availability in ("google", "bing", "yandex", "karmadecay"):
            #for each search engine, add the results if they're available, otherwise say there are no links from that search engine.
            if available_dict[availability]:
                reply += searchengine_dict[availability][0].format(searchengine_dict[availability][1]) #0: message; 1: formatted results
            else:
                reply += searchengine_dict[availability][0].format("No available links from this search engine found.")

    try:
        reply += extra_message
        if comment_exists(comment):
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
            if comment_exists(comment):
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

def find_username_mentions():
    for comment in r.get_unread(limit=100):
        if SEARCH_STRING in comment.body:
            print "search string in body"
            if comment.author: #check if the comment exists
                print "comment.author"
                print comment.subreddit
                if str(comment.subreddit) in subreddit_list: #check if it's in one of the right subs
                    print "comment.subreddit"
                    if (time.time()-comment.created_utc)/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                        print "time"
                        try:
                            isPicture = any(i in str(comment.submission.url) for i in ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png'])
                        except UnicodeEncodeError:
                            isPicture = False #non-ascii url
                        if isPicture:
                            print "isPicture"
                            top_level = [i.replies for i in comment.submission.comments]
                            submission_comments = []
                            for i in top_level:
                                for j in i:
                                    submission_comments.append(j)
                            if not any(i for i in submission_comments if config['EXTRA_MESSAGE'] in i.body): #If there are no link replies
                                print "no link replies"
                                if comment.id not in already_done and comment.author != user:
                                    #print "not already done and not its own user"
                                    give_more_info(comment)
                                    already_done.append(comment.id)
        comment.mark_as_read()


def find_keywords(all_comments):
    for comment in all_comments:
        print ".",
        if comment['author']: #check if the comment exists
            if comment['subreddit'] in subreddit_list: #check if it's in one of the right subs
                if (time.time()-comment['created_utc'])/60 < time_limit_minutes: #if the age of the comment is less than the time limit
                    try:
                        isPicture = any(i in str(comment['link_url']) for i in ['.tif', '.tiff', '.gif', '.jpeg', 'jpg', '.jif', '.jfif', '.jp2', '.jpx', '.j2k', '.j2c', '.fpx', '.pcd', '.png'])
                    except UnicodeEncodeError:
                        isPicture = False #non-ascii url
                    if isPicture:
                        body = comment['body'].lower()
                        if any(word.lower() in body.lower() for word in keyword_list):
                            comment = r.get_submission(url="http://www.reddit.com/r/{0}/comments/{1}/aaaa/{2}".format(comment['subreddit'],comment['link_id'][3:],comment['id'])).comments
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
                                                print "\ndetected keyword: "+ comment.body.lower()
                                            except UnicodeEncodeError:
                                                print "\ndetected keyword: ",
                                                try:
                                                    print comment.body
                                                except: pass #print ''.join(k for k in i[j] if (ord(k)<128 and k not in '[]()')) for j in xrange(2)
                                            if comment.id not in already_done and comment.author != user:
                                                done = False
                                                attempt = 1
                                                while not done:
                                                    done = reply_to_potential_comment(comment,attempt)

def check_downvotes(user,start_time):
    current_time = int(time.time()/60)
    if (current_time - start_time) >= comment_deleting_wait_time:
        my_comments = user.get_comments(limit=None)
        for comment in my_comments:
            if comment.score < 1:
                comment.delete()
                print 'deleted a comment'
        return current_time
    return start_time

def get_filter(filter_type):
    filters=json.load(urllib2.urlopen('http://spambot.rarchives.com/api.cgi?method=get_filters&start=0&count=2000&type={0}'.format(filter_type)))['filters']
    return [i['spamtext'] for i in filters]

def get_comment_stream_urls(subreddit_list):
    MAX_LENGTH = 2010
    url_list = []
    subreddit_chain = ""
    for i in subreddit_list:
        new_element = i + "+"
        if len(subreddit_chain) + len(new_element) > MAX_LENGTH:
            url_list.append("http://reddit.com/r/{0}/comments.json".format(subreddit_chain[:-1]))
            subreddit_chain = ""
        subreddit_chain += new_element
    url_list.append("http://reddit.com/r/{0}/comments.json".format(subreddit_chain[:-1]))
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

blacklist = pickle.load(open("blacklist.p", "rb"))
print 'Adding Rarchives links to blacklist.'
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
whitelist = ["reddit.com"]
tld_blacklist = [''.join(letter for letter in tld if letter!=".") for tld in get_filter('tld')]

with open('config.json') as json_data:
    config = json.load(json_data)

COMMENT = 'comment'
PM = 'PM'
LOG = 'log'
mode = config['MODE']
submission_id = config['SUBMISSION_ID']

SEARCH_STRING = config["SEARCH_STRING"]

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

credentials = {'user': config["USER_NAME"], 'passwd': config["PASSWORD"], 'api_type': 'json',}
headers = {'user-agent': config["BOT_NAME"],}
session_client = requests.session()
r1 = session_client.post('http://www.reddit.com/api/login', data = credentials, headers=headers)
the_json = json.loads(r1.text)
session_client.modhash = the_json['json']['data']['modhash']

comment_stream_urls = get_comment_stream_urls(subreddit_list)

def main():
	start_time = time.time()
	while True:
	    try:
	        for stream in comment_stream_urls: #uses separate comment streams for large subreddit list due to URL length limit
	            a = time.time()
	            all_comments = get_all_comments(stream)
	            if not all_comments:
	                continue
	            print time.time()-a
	            find_keywords(all_comments)
	            print "finding username mentions..."
	            find_username_mentions()
	            start_time = check_downvotes(user,start_time)

	            pickle.dump(already_done, open("already_done.p", "wb"))
	            pickle.dump(blacklist, open("blacklist.p", "wb"))

	            print 'Finished a round of comments. Waiting two seconds.\n'
	            time.sleep(2)
	    except ConnectionError:
	        print 'Connection Error'
	    except HTTPError:
	        print 'HTTP Error'


#give_more_info(comment("http://i.imgur.com/zfJb6nZ.jpg"))

main()