## python reddit-part1.py --username myUsername --password 12345 --subreddit "all" -- search "more information" --limit 1000

import praw             # For reddit API
import sys              # Used for stderr message output
import time             # To make the bot sleep
import threading        # To run second thread that cleans up downvoted posts
import urllib2          # To except HTTPError
import argparse         # To get arguments from command line
import logging			# To log all the script outputs

class redditSearch:
	def __init__(self,username,password,subReddit,searchString,limit=1000):
		self.username = username
		self.password = password
		self.subReddit = subReddit
		self.searchString = searchString
		self.limit = limit
		self.logger = logging.getLogger('redditSearch')
		self.logger.setLevel(logging.ERROR)
		formatter = logging.Formatter(' %(asctime)s [%(levelname)s]: %(message)s')
		handler = logging.StreamHandler()
		handler.setFormatter(formatter)
		self.logger.addHandler(handler)
		self.greenLight = True
		self.MoreInfoReply="More Information"
		self.botAuthor="WhoIsThatBot"
    
	def startSearch(self):
		r = praw.Reddit()
            r.login(self.username, self.password)
            self.logger.info("Logged in.")
            
            # Old comment scanner-deleter to delete <1 point comments every half hour
            deleteCommentThread = threading.Thread(target=deleteDownvotedPosts, args=(r,))
            deleteCommentThread.start()
            
            
            # Neverending loop to run bot continuously
            while (True):
                self.logger.info("Initializing Comment Scanner")
                commentScanner(r, self.searchString)
                self.logger.info("15 Seconds Sleep")
                time.sleep(15)
                self.logger.warning("I'm full.")
        
        def commentScanner(self,session, searchString):
            self.logger.info("Fetching comments")
            # comments now stores all the comments pulled using comment_stream
            # Change "all" to "subreddit-name" to scan a particular sub
            # limit = None fetches max possible comments (about 1000)
            # See PRAW documentation for verbosity explanation (it is not used here)
            comments = praw.helpers.comment_stream(session, self.subReddit,
                                                   limit = self.limit, verbosity = 0)
                                                   commentCount = 0   # Number of comments scanned (for stderr message)
                                                   
                                                   # Read each comment
                                                   for comment in comments:
                                                       self.logger.info("Scanning comments")
                                                       commentCount += 1
                                                       self.greenLight = True
                                                       self.logger.info("Comments Count: %d") %(comment_count)
                                                       # Scan for each phrase
                                                       for phrase in searchString:
                                                           self.logger.info("Searching for Phrase %s") %(phrase)
                                                               # If phrase found
                                                               if phrase in comment.body:
                                                                   # Check replies to see if already replied
                                                                   for reply in comment.replies:
                                                                       if reply.author.name == self.botAuthor:
                                                                           self.logger.info ("Already replied.")
                                                                           self.greenLight = False
                                                                           break
                                                                   
                                                                   # If not already replied
                                                                   if (self.greenLight == True):
                                                                       self.logger.info ("Something found!")
                                                                       postComment(comment)
                                                                       self.logger.info("Posting Reply.")
                                                                       break
                                                       
                                                       if commentCount == self.limit:
                                                           return;
        
        def postComment(self,replyTo):
            # Post comment
            try:
                self.logger.info("Posting Reply")
                replyTo.reply(self.MoreInfoReply)
            
            # If reddit returns error (when bot tries to post in unauthorized sub)
            except urllib2.HTTPError as e:
                self.logger.ERROR("Got HTTPError from reddit:" + e.code)
                if e.code == 403:
                    self.logger.ERROR("Posting in restricted subreddit.")
                self.logger.info("Nothing to see here. Moving on.")
            
            # To catch any other exception
            except Exception as e:
                self.logger.ERROR("Got some non-HTTPError exception.")
        
        
        def deleteDownvotedPosts(self,session):
            
            while (True):
                self.logger.info("Starting old comments scanner.")
                                 # Get own account
                                 myAccount = session.get_redditor(self.username)
                                 # Get last 25 comments
                                 myComments = myAccount.get_comments(limit = 10)
                                 
                                 # Delete all comments with <1 point
                                 for oldComment in myComments:
                                 if oldComment.score <= 0:
                                 self.logger.warning("Found disliked comment. Deleting.")
                                 oldComment.delete()
                                 
                                 # Sleep for half hour
                                 self.logger.info("Turning down old comment scanner for 30 mins")
                                 time.sleep(1800)
                                 
                                 
                                 
                                 if __name__ == "__main__":
                                 
                                 parser = argparse.ArgumentParser(description='Get arguments to run the script')
                                 parser.add_argument('-user', dest='username', help='username for reddit authentication')
                                 parser.add_argument('-pass', dest='password', help='password for reddit authentication')
                                 parser.add_argument('-subreddit', dest='subreddit', help='define which subreddit to search in for comments. Type all for all.')
                                 parser.add_argument('-search',dest='searchString',help='Enter the string to search for in the comments')
                                 parser.add_argument('-limit',dest='limit',help='Number of comments to search for in one run')
                                 args = parser.parse_args()
                                 
                                 mySearchBot = redditSearch(args.username,args.password,args.subreddit,args.searchString,args.limit)
                                 mySearchBot.startSearch()