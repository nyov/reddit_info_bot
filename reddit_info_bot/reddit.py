# -*- coding: utf-8 -*-
import praw

def r_login(user_agent, username, password):
    """login to reddit account"""

    account = praw.Reddit(user_agent)
    account.login(username, password, disable_warning=True) # drop the warning for now (working on it)
    # 'Logged in as /u/%s' % username
    return account

def reddit_login(config):
    print('Logging into accounts')

    user_agent = config['BOT_NAME']

    account1 = r_login(user_agent, config['USER_NAME'], config['PASSWORD'])
    if config['SECOND_ACCOUNT_NAME'] and config['SECOND_ACCOUNT_PASS']:
        # load a second praw instance for the second account (the one used to check the spam links)
        account2 = r_login(user_agent, config['SECOND_ACCOUNT_NAME'], config['SECOND_ACCOUNT_PASS'])
    else:
        account2 = False

    user = account1.get_redditor(config['USER_NAME'])

    print('Fetching Subreddit list')
    subreddit_list = [account1.get_subreddit(i).display_name for i in config['SUBREDDITS']]

    return (account1, account2, user, subreddit_list)
