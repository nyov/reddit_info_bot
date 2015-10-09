# -*- coding: utf-8 -*-
from __future__ import print_function
import praw
import time
import uuid

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
    if 'SECOND_ACCOUNT_NAME' in config and config['SECOND_ACCOUNT_NAME'] \
            and 'SECOND_ACCOUNT_PASS' in config and config['SECOND_ACCOUNT_PASS']:
        # load a second praw instance for the second account (the one used to check the spam links)
        account2 = r_login(user_agent, config['SECOND_ACCOUNT_NAME'], config['SECOND_ACCOUNT_PASS'])
    else:
        account2 = False

    user = account1.get_redditor(config['USER_NAME'])

    print('Fetching Subreddit list')
    subreddit_list = [account1.get_subreddit(i).display_name for i in config['SUBREDDITS']]

    return (account1, account2, user, set(subreddit_list))


def reddit_msg_linkfilter(messages, sending_account, receiving_account, submission_id):
    """ Post reddit comments with one account and check from second account
    to see if they were filtered out.
    """
    queue = {}
    submission = sending_account.get_submission(submission_id=submission_id)
    # post with first account
    print('reddit_msg_linkfilter posting messages: ', end='')
    for message in messages:
        # use a unique id in the message so we'll always recognize it
        # (even if the text got mangled, e.g. unicode or other strangeness)
        id = uuid.uuid4()
        try:
            _message = '[%s] %s' % (id, message)
            submission.add_comment(_message)
        except Exception as e:
            print('\nreddit_msg_linkfilter failed to post "%s"' % (message,))
            print(e)
            # FIXME: check exception for http errors (retry?) or other (spam?)
            continue
        queue.update({id: message})
        print('<', end='')
    print()

    time.sleep(7) # wait a bit

    # fetch posts on second account
    print('reddit_msg_linkfilter verifying messages: ', end='')
    verified_messages = []
    fetched_messages = receiving_account.get_unread(limit=40)
    for msg in fetched_messages:
        if not msg.body.startswith('['):
            # skip unknown messages
            #print('\nreddit_msg_linkfilter skipping unknown message "%s..."' % msg.body[:10])
            continue
        for id in queue.keys():
            if str(id) not in msg.body:
                continue
            message = queue.pop(id)
            #if message != str(msg.body).replace('[%s] ' % id, ''):
            #    print('(message got mangled?)')
            msg.mark_as_read()
            verified_messages += [message]
            print('>', end='')
    print()
    if queue: # shouldnt have any messages left at this point
        print('reddit_msg_linkfilter posted but did not find: %s' % str(queue.values()))
    failed_messages = [m for m in messages if (m not in verified_messages and m not in queue.values())]
    if failed_messages:
        print('reddit_msg_linkfilter failed on: %s' % str(failed_messages))
    return verified_messages
