#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Imgur API client helpers

    Info: https://github.com/Imgur/imgurpython
    API : https://api.imgur.com/endpoints
          https://api.imgur.com/models
"""
from imgurpython import ImgurClient


def imgur_login(settings={}, client_id=None, client_secret=None):
    #user_agent = settings.get('BOT_AGENT')

    if not client_id:
        client_id = settings.get('IMGUR_CLIENT_ID')
    if not client_secret:
        client_secret = settings.get('IMGUR_CLIENT_SECRET')
    client = ImgurClient(client_id, client_secret)

    return client

def image_upload(client, image, config={}, anon=True):
    """ upload image from fileobject """
    """
    album_id = None
    default_config = {
        'album': album_id,
        'name': '',
        'title': '',
        'description': '',
    }
    """

    image.seek(0)
    image_meta = client.upload(image, config, anon)
    return image_meta # image_meta['link']

def album_add_images(client, album_id, image_ids):
    # image_ids: list or comma-delimited string
    return client.album_add_images(album_id, image_ids)

def create_album(client, fields={}):
    """ create (anonymous) album """
    """
    default_fields = {
        'ids': [],
        'title': '',
        'description': '',
        'privacy': 'hidden', # public | hidden | secret
        'layout': '', # blog | grid | horizontal | vertical
        'cover': '',
    }
    """
    album = client.create_album(fields)
    return album

def album_delete(client, album_id):
    """ delete album """
    # album id or deletehash
    success = client.album_delete(album_id)
    return success

if __name__ == '__main__':
    import sys

    # creates an album by running:
    # python ./imgur.py <client-id> <client-secret>

    id, = sys.argv[1:2] or ['']
    secret, = sys.argv[2:3] or ['']
    imgur = imgur_login(client_id=id, client_secret=secret)

    fields = {
        'privacy': 'hidden',
    }
    album = create_album(imgur, fields)

    print (type(album))
    print (album)

    sys.exit()
