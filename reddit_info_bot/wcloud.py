#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wordcloud generation utilities
"""
try:
    from .util import BytesIO
except ValueError:
    from six import BytesIO

# stopwords
from wordcloud import STOPWORDS, WordCloud
STOPWORDS = set(w.decode('utf-8') for w in STOPWORDS)
try:
    from nltk.corpus import stopwords
    stopwords = set(stopwords.words('english'))
    stopwords = stopwords | STOPWORDS
except ImportError:
    stopwords = STOPWORDS or set()
del STOPWORDS

default_settings = {
    #'font_path': '',
    'width': 400,
    'height': 200,
    'max_words': 200,
    'stopwords': stopwords,
    'background_color': 'black',
    'relative_scaling': 0.5,
    'prefer_horizontal': 0.9,
}

def update_stopwords(s_words):
    if isinstance(s_words, (list, tuple)):
        s_words = set(s_words)
    stopwords = s_words
    return s_words

def wordcloud_image(text, **kwargs):
    """ Build wordcloud from text """
    format = 'PNG'
    if kwargs.has_key('file_format'):
        format = kwargs.pop('file_format')

    args = default_settings
    args.update(kwargs)

    wc = WordCloud(**args)
    wc.generate_from_text(text)
    img = wc.to_image()
    del wc
    imgbuf = BytesIO()
    img.save(imgbuf, format)
    width, height = img.size
    imgbuf.seek(0)
    del img
    return imgbuf, (width, height)


if __name__ == '__main__':
    import sys, pprint

    # Print the list of default stopwords
    pprint.pprint(stopwords)

    sys.exit(0)

    # Test wordcloud building
    text = """
        blah
        blah
        blubb
    """
    image, size = wordcloud_image(text)
    export = '/tmp/testcloud.png'
    with open(export, 'wb') as f:
        f.write(image.read())
