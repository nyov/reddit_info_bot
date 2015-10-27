"""PRAWAWAWawawrapwrapwapapppffft

wrapping the wrapper

This module is licensed GNU GPLv3
"""
from __future__ import (absolute_import, unicode_literals)
import six
import praw
from praw import *

# SimpleOAuth2 for script access

@praw.decorators.require_oauth
def get_bearer_access(self, username, password):
    data = {'grant_type': 'password',
            'username': username,
            'password': password}
    retval = self._handle_oauth_request(data)
    return {'access_token': retval['access_token'],
            'scope': set(retval['scope'].split(' '))}

@property
def has_oauth_app_info(self):
    return all((self.client_id is not None,
                self.client_secret is not None))

def set_oauth_app_info(self, client_id, client_secret, redirect_uri=None):
    self.client_id = client_id
    self.client_secret = client_secret
    if redirect_uri:
        self.redirect_uri = redirect_uri

praw.OAuth2Reddit.get_bearer_access = get_bearer_access
praw.OAuth2Reddit.has_oauth_app_info = has_oauth_app_info
praw.OAuth2Reddit.set_oauth_app_info = set_oauth_app_info

# AuthenticatedReddit
#
# Support `*` scope

def has_scope(self, scope):
    """Return True if OAuth2 authorized for the passed in scope(s)."""
    if not self.is_oauth_session():
        return False
    if '*' in self._authentication:
        return True
    if isinstance(scope, six.string_types):
        scope = [scope]
    return all(s in self._authentication for s in scope)

praw.AuthenticatedReddit.has_scope = has_scope
