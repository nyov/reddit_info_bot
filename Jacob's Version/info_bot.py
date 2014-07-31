import time
import praw
import pickle
import urllib2
import BeautifulSoup
from requests import HTTPError,ConnectionError
from praw.errors import RateLimitExceeded

def get_bing_results(submission, limit=10): #limit is the max number of results to display
    image = submission.url
    response_text = urllib2.urlopen("https://www.bing.com/images/searchbyimage?FORM=IRSBIQ&cbir=sbi&imgurl="+image)
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'sbi_sp'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)-1
    results = [(list_class_results[i].findAll(attrs={'class':'info'})[0].find('a')['href'],list_class_results[i].findAll(attrs={'class':'info'})[0].find('a').contents[0]) for i in xrange(limit)]
    return results

def give_more_info(comment):
    try:
        bing_result = get_bing_results(comment.submission)
        bing_formatted = ["["+i[1]+"]("+i[0]+")" for i in bing_result] #reformats the results into Markdown
        ascii_bing = ''.join(i for i in '\n\n'.join(bing_formatted) if ord(i)<128)
        reply = "**More Information:**\n\n{0}".format(ascii_bing)
    except IndexError:
        reply = "Sorry, no information is available for this link."
    try:
        comment.reply(reply)
        print 'replied to comment with more info'
    except HTTPError:
        print 'HTTP Error. Bot might be banned from this sub'

def reply_to_potential_comment(comment,attempt):
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
    for comment in all_comments:
        if 'more info info_bot' in comment.body.lower() and comment.id not in already_done and comment.author != user:
            give_more_info(comment)
            already_done.append(comment.id)
        elif any(word in comment.body.lower() for word in keyword_list):
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

comment_deleting_wait_time = 30 #how many minutes to wait before deleting downvoted comments
r = praw.Reddit('Info Bot')
r.login('info_bot','password')
user = r.get_redditor('info_bot')
already_done = pickle.load(open("already_done.p", "rb"))
start_time = int(time.time()/60) #time in minutes for downvote checking

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


