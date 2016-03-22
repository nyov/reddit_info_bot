# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import logging
import json
import base64
from collections import OrderedDict
from w3lib.html import get_meta_refresh
from urllib3.filepost import encode_multipart_formdata
from six.moves.urllib.parse import (
    unquote, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode,
)
try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO
from PIL import Image
from scrapy.http import Request, FormRequest, HtmlResponse
try:
    from . import InfoBotSpider
except ImportError:
    from scrapy.spiders import Spider

    class InfoBotSpider(Spider):
        def write(self, data):
            yield data

from ..search import optimize_image_url


def convert_image(data):
    """ Convert image to jpeg """
    image = Image.open(BytesIO(data))
    width, height = image.size

    if image.format == 'PNG' and image.mode == 'RGBA':
        background = Image.new('RGBA', image.size, (255, 255, 255))
        background.paste(image, image)
        image = background.convert('RGB')
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    imgbuf = BytesIO()
    image.save(imgbuf, 'JPEG')
    imgbuf.seek(0)
    #return imgbuf
    image = imgbuf.read()
    return image, (width, height)


class Search(InfoBotSpider):

    name = 'search'

    search_url = ''

    def __init__(self, *args, **kwargs):
        self.num_results = 10
        if 'num_results' in kwargs:
            self.num_results = kwargs.pop('num_results')

        super(Search, self).__init__(*args, **kwargs)

    def pre_search(self, request):
        return request


class ImageSearch(Search):

    name = 'imagesearch'

    def __init__(self, *args, **kwargs):
        # search by URL
        if 'image_url' in kwargs:
            self.image_url = kwargs.pop('image_url')
        # search by image
        if 'image_data' in kwargs:
            self.image_data = kwargs.pop('image_data')

        super(ImageSearch, self).__init__(*args, **kwargs)

    def from_url(self, image_url, method='GET', params={}):
        # 'application/x-www-form-urlencoded'
        return FormRequest(self.search_url, method=method, formdata=params)

    def from_data(self, image_data, method='POST', params={}):
        # 'multipart/form-data'
        return Request(self.search_image_url, method=method, body=params)

    def start_requests(self):
        if self.image_url:
            request = self.from_url(self.image_url)
        elif self.image_data:
            request = self.from_data(self.image_data)
        yield self.pre_search(request)


class KarmaDecay(ImageSearch):

    name = 'imagesearch-karmadecay'

    search_url = 'http://karmadecay.com/'
    search_image_url = 'http://karmadecay.com/index/'

    def from_url(self, image_url):
        params = OrderedDict([
            ('kdtoolver', 'b1'),
            ('q', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def from_data(self, image_data, filetype=None, fileext=None):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            if not fileext:
                fileext = 'png'
            image_data = ('image.%s' % fileext, image_data)
        params = OrderedDict([
            ('MAX_FILE_SIZE', '10485760'),
            #('image', ''),
            #('url', image_url),
            ('image', image_data),
            ('url', ''),
            ('search', 'search'),
            ('nsfwfilter', 'off'),
            ('subreddit[pics]', 'off'),
            ('subreddit[funny]', 'off'),
            ('subreddit[wtf]', 'off'),
            ('subreddit[nsfw]', 'off'),
            ('subreddit[others]', 'off'),
            ('subreddit[all]', 'off'),
        ])
        body, content_type = encode_multipart_formdata(params, boundary=None)
        headers = {
            b'Content-Type': content_type,
            b'X-Requested-With': b'XMLHttpRequest',
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse(self, response):
        page_content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        results = page_content.xpath('.//div[@id="content"]/table[@class="search"]//tr[@class="result"]')
        if not results:
            self.logger.info('No search results')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_image = found.xpath('td[@class="img"]/a/@href').extract_first()
            source_image_size = found.xpath('td[@class="info"]/div[@class="similar"]/span[contains(.//text(), " x ")]//text()').extract_first()
            source_image_size = [s.strip() for s in source_image_size.split('x')] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('td[@class="info"]/div[@class="title"]/a/@href').extract_first()
            source_title = found.xpath('td[@class="info"]/div[@class="title"]/a/text()').extract_first()
            source_text = found.xpath('td[@class="info"]/div[@class="submitted"]//text()[normalize-space()]')
            stext = []
            for s in source_text.extract():
                s = s.split()
                s = [x.strip() for x in s]
                s = ' '.join(s)
                stext += [s]
            source_text = ' '.join(stext)

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_title,
                'text': source_text,
                'image_url': source_image,
                'image_size': source_image_size,

                #'source': response.request.url,
                #'source': response.meta.get('redirect_urls')[0],
                'search': response.url,
            }
            self.write(result)


class Yandex(ImageSearch):

    name = 'imagesearch-yandex'

    search_url = 'https://www.yandex.com/images/search'
    search_image_url = search_url

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('img_url', image_url),
            ('rpt', 'imageview'),
            ('uinfo', 'sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900'), # some fake browser info
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def from_data(self, image_data, filetype=None, fileext=None):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            if not fileext:
                fileext = 'png'
            image_data = ('image.%s' % fileext, image_data)
        params = OrderedDict([
            ('upfile', image_data),
            #('format', 'json'),
            #('request', '[{"block":"b-page_type_search-by-image__link"}]'),
            ('rpt', 'imageview'),
        ])
        urlparams = OrderedDict([
            ('uinfo', 'sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900'), # some fake browser info
            ('rpt', 'imageview'),
            #('serpid', 'tXFwPxlgPacPB2xU7yJFZw'), # ???
        ])
        qstring = '?' + urlencode(urlparams)
        body, content_type = encode_multipart_formdata(params, boundary=None)
        headers = {
            b'Content-Type': content_type,
            b'X-Requested-With': b'XMLHttpRequest',
            b'DNT': b'1',
        }
        return Request(self.search_image_url + qstring, method='POST', body=body, headers=headers)

    def get_url(self, response):
        result = response.meta['result']

        url = None
        if isinstance(response, HtmlResponse):
            interval, url = get_meta_refresh(response.body, response.url, response.encoding, ignore_tags=())
            result['link'] = url

        self.write(result)

    def parse(self, response):
        page_content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        results = page_content.xpath('.//ul[@class="other-sites__container"]/li')
        if not results:
            self.logger.info('No search results')
            #similar = page_content.xpath('.//ul[@class="similar__thumbs"]/li/a') # /@href + /img/@src

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_image = found.xpath('a[@class="other-sites__preview-link"]/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "other-sites__meta")]/text()').extract_first()
            source_image_size = [s.strip() for s in source_image_size.split('×'.decode('utf-8'))] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('.//a[contains(@class, "other-sites__title-link")]/@href').extract_first()
            source_displaylink = found.xpath('.//a[contains(@class, "other-sites__outer-link")]/@href').extract_first()
            source_title = found.xpath('.//a[contains(@class, "other-sites__title-link")]/text()').extract_first()
            source_text = found.xpath('.//a[contains(@class, "other-sites__desc")]/text()').extract_first() # not in image upload

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_title,
                'text': source_text,
                'image_url': source_image,
                'image_size': source_image_size,
                'display_link': source_displaylink, # the shortened thing

                #'source': response.request.url,
                #'source': response.meta.get('redirect_urls')[0],
                'search': response.url,
            }
            yield Request(source_link, callback=self.get_url, meta={'dont_redirect': True, 'result': result})

        if num_results > self.num_results:
            return
        # dont seem like relevant results
        #more_link = page_content.xpath('.//div[contains(@class, "more_direction_next")]/a[contains(@class, "more__button")]/@href').extract_first()
        #if more_link:
        #    yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)


class Bing(ImageSearch):

    name = 'imagesearch-bing'

    search_url = 'https://www.bing.com/images/searchbyimage'
    search_image_url = 'https://www.bing.com/images/search'

    def from_url(self, image_url):
        # prefer non-https URLs, BING can't find images in https:// urls!?
        image_url = optimize_image_url(image_url)
        if image_url.startswith('https'):
            image_url = image_url.replace('https', 'http', True)

        params = OrderedDict([
            #('FORM', 'IRSBIQ'),
            ('cbir', 'sbi'),
            ('imgurl', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def from_data(self, image_data, fileext='png'):
        # bing transcodes images with javascript, then submits base64-encoded jpeg data...
        image_size = len(image_data) / 1024
        image_data, (width, height) = convert_image(image_data)
        image_data = base64.b64encode(image_data) # base64 encoded submission
        image_data = (None, image_data, None)
        params = OrderedDict([
            ('imgurl', ''),
            ('cbir', 'sbi'),
            ('imageBin', image_data),
        ])
        urlparams = OrderedDict([
            ('q', ''),
            ('view', 'detailv2'),
            ('iss', 'sbi'),
            ('FORM', 'IRSBIQ'),
            ('sbifsz', '%s x %s · %s kB · %s' % (width, height, image_size, fileext)), # probably nobody cares about that, but fake it anyway
            ('sbifnm', 'image.%s' % fileext), # our "filename"
            ('thw', width),
            ('thh', height),
        ])
        qstring = '?' + urlencode(urlparams)
        body, content_type = encode_multipart_formdata(params, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url + qstring, method='POST', body=body, headers=headers)

    def parse(self, response):
        page_content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        upload_results = page_content.xpath('.//div[@id="insights"]')
        if upload_results:
            return self.parse_image(response)

        results = page_content.xpath('.//div[@id="sbi_sct_sp"]/div[@class="sbi_sp"]')
        if not results:
            self.logger.info('No search results')
            if "Sorry, we can't search by image with" in response.body:
                self.logger.info('Search was not an image link?')
            elif "We couldn't find any matches for this image." not in response.body:
                self.logger.warning('Unknown search fail.')
            return

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_image = found.xpath('div[@class="th"]/a/@href').extract_first()
            source_image_metainfo = found.xpath('div[@class="info"]/div[@class="si"][contains(text(), " x ")]/text()').re(ur'^(.*)·(.*)·(.*)$')
            source_image_size = source_image_metainfo[0]
            #source_image_filesize = source_image_metainfo[1]
            #source_image_format = source_image_metainfo[2]
            source_image_size = [s.strip() for s in source_image_size.split('x')] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('div[@class="info"]/a/@href').extract_first()
            source_title = found.xpath('div[@class="info"]/a/text()').extract_first()
            source_displaylink = found.xpath('div[@class="info"]/div[@class="st"]/text()').extract_first()
            #source_text = found.xpath('td[@class="info"]/div[@class="submitted"]//text()[normalize-space()]')
            #source_text = ' '.join(source_text.extract())

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_title,
                #'text': source_text,
                'image_url': source_image,
                'image_size': source_image_size,
                'display_link': source_displaylink, # the shortened thing

                #'source': response.request.url,
                #'source': response.meta.get('redirect_urls')[0],
                'search': response.url,
            }
            self.write(result)

        # There doesn't seem to be any pagination in results here ever! :heart:

    def parse_image(self, response):

        def gimmefrigginresults():
            # oookay, no f**kin idea what I'm doing here,
            # lets just grab all the hidden params we can get our grubby hands on
            # and throw 'em back at the service, that usually works

            # first, grab us some vars...
            vaaars = response.xpath('//span[@id="ivd"]/@json-data').extract_first()
            vaaars = json.loads(unquote(vaaars))
            vaaars = vaaars['web']['0'] # lets hope that is always there

            # second, grab us some moar vars...
            iiidx = response.body.find('IIConfig')
            if iiidx < 0: # not found? we failed
                return
            moaaarvars = response.body[iiidx:]
            iiidx = moaaarvars.find('};')
            if iiidx < 0: # not found? we failed
                return
            moaaarvars = moaaarvars[:iiidx+1]
            moaaarvars = moaaarvars.lstrip('IIConfig=')
            moaaarvars = json.loads(moaaarvars)
            lessvaaars = moaaarvars['aut']
            uuuuurl = urlparse(lessvaaars)
            lessvaaars = dict(parse_qsl(uuuuurl.query))

            # third, mush them somewhat together into
            # something the service seems to expect
            blended = OrderedDict([
                ('IG', lessvaaars['IG']),
                ('IID', lessvaaars['IID']),
                ('SFX', '1'),
                ('iss', 'sbi'),
                ('mid', vaaars['mid']),
                ('ccid', vaaars['ccid']),
                ('vw', vaaars['vw'].replace('+', ' ')),
                ('simid', '0'),
                ('thid', ''),
                ('thh', vaaars['height']),
                ('thw', vaaars['width']),
                ('q', ''),
                ('mst', vaaars['mst']),
                ('mscr', vaaars['mscr']),
                ('spurl', ''),
                ('vf', ''),
                ('imgurl', ''),
            ])

            # fourth, assemble
            url = response.urljoin(urlunsplit(('', '', uuuuurl.path, urlencode(blended), '')))

            headers = {
                # and lets look the same as in the last request
                b'Accept-Language': b'en-US,en;q=0.5',
                b'DNT': b'1',
            }
            # finally, see if they are willing to communicate with this encoding
            return Request(url, callback=self.parse_image, headers=headers)


        if not response.body and response.status == 200:
            # now we have the result page, but no results yet... hmmm
            # gotta do some XHR fancyness, preferrably without a javascript interpreter or DOM
            return gimmefrigginresults()


        # well whaddaya know... it worked? whew
        page_content = response.xpath('//body')

        # number of results found (if any)
        total_results = page_content.xpath('.//ul[@class="insights"]//div[contains(@class, "b_focusLabel")]/text()').re_first(r'^(\d+)')
        if total_results:
            total_results = int(total_results) # oh my. that was worth it
        else:
            self.logger.info('No search results')
            return

        results = page_content.xpath('.//ul[@class="insights"]//ul[@class="expbody"]/li')
        #results = page_content.xpath('.//ul[@class="insights"]//ul[@class="expbody"]/li[a]')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_link = found.xpath('a/@href').extract_first()
            source_displaylink = found.xpath('a/div[@class="iscbody"]//ul[@class="b_dataList"]/li[1]/text()').extract_first() # preview link [no protocol]

            source_title = found.xpath('a/div//span[@title]/text()').extract_first()
            source_image_metainfo = found.xpath('a/div[@class="iscbody"]//ul[@class="b_dataList"]/li[2]/text()').re(ur'^(\d+) x (\d+) · (\d+) kB · (.*)$')
            width, height, source_image_filesize, source_image_format = source_image_metainfo
            source_image_size = '%sx%s' % (width, height)

            if not source_link or not source_title:
                continue

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_title,
                #'text': source_text,
                #'image_url': source_image,
                'image_size': source_image_size,
                'image_filesize': source_image_filesize,
                'image_format': source_image_format,
                'display_link': source_displaylink, # the shortened thing

                #'source': response.request.url,
                #'source': response.meta.get('redirect_urls')[0],
                'search': response.url,
            }
            self.write(result)

        # There doesn't seem to be any pagination in results here ever! :heart:


class Tineye(ImageSearch):

    name = 'imagesearch-tineye'

    search_url = 'https://www.tineye.com/search'
    search_image_url = search_url

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('search_button', ''),
            ('url', image_url),
        ])
        return FormRequest(self.search_url, method='POST', formdata=params)

    def from_data(self, image_data, filetype=None, fileext=None):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            if not fileext:
                fileext = 'png'
            image_data = ('image.%s' % fileext, image_data)
        params = OrderedDict([
            ('image', image_data),
        ])
        body, content_type = encode_multipart_formdata(params, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse(self, response):
        page_content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        results = page_content.xpath('.//div[@class="results"]//div[@class="row matches"]//div[contains(@class, "match-row")]')
        if not results:
            self.logger.info('No search results')
        if 'Your IP has been blocked' in response.body:
            self.logger.error('Tineye IP ban')
        if '403 Forbidden' in response.body: # hmm, error shouldn't even reach us
            self.logger.error('Tineye blocked us')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_image = found.xpath('.//div[@class="match"]/p[contains(@class, "short-image-link")]/a/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[2]/text()').extract_first()
            source_image_size = [s.strip() for s in source_image_size.split('x')] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('.//div[@class="match"]/p[not(@class)]/a/@href').extract_first()
            source_title = found.xpath('.//div[@class="match"]/h4[@title]/text()').extract_first()
            source_text = found.xpath('.//div[@class="match"]/p[@class="crawl-date"]/text()').extract_first()

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_title,
                'text': source_text,
                'image_url': source_image,
                'image_size': source_image_size,

                #'source': response.request.url,
                #'source': response.meta.get('redirect_urls')[0],
                'search': response.url,
            }

            if source_image:
                source_image = os.path.basename(source_image)
                text = '{0} {1} on {2}'.format(source_image, source_image_size, source_title)
                result['title'] = text + ' (%s)' % result['text']

            self.write(result)

        if num_results > self.num_results:
            return
        more_link = page_content.xpath('.//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)


class Google(ImageSearch):

    name = 'imagesearch-google'

    search_url = 'https://www.google.com/searchbyimage'
    search_image_url = 'https://www.google.com/searchbyimage/upload'

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('image_url', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def from_data(self, image_data, filetype=None, fileext=None):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            if not fileext:
                fileext = 'png'
            image_data = ('image.%s' % fileext, image_data)
        params = OrderedDict([
            ('image_url', ''),
            ('encoded_image', image_data),
            ('image_content', ''),
            ('filename', ''),
            ('hl', 'en'),
        ])
        body, content_type = encode_multipart_formdata(params, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse(self, response):
        page_content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        # exclude ads, thanks
        results = page_content.xpath('.//div[contains(@class, "normal-header")][div[contains(text(), "Pages that include matching images")]]/following-sibling::*//*[@class="rc"]')
        if not results:
            results = page_content.xpath('.//*[@class="rc"]')
            if not results:
                self.logger.info('No search results')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_link = found.xpath('.//*[@class="r"]//a/@href').extract_first()
            source_title = found.xpath('.//*[@class="r"]//a/text()').extract()
            source_title = ''.join(source_title)

            source_displaylink = found.xpath('.//*[@class="s"]//cite/text()').extract_first()
            source_text = found.xpath('.//*[@class="s"]//*[@class="st"]//text()').extract()
            source_text = found.xpath('.//*[@class="s"]//*[@class="st"]//text()[not(parent::span[@class="f"])]').extract()
            source_text = ''.join(source_text)

            #source_image_metainfo = found.xpath('.//*[@class="f"]//text()').re(ur'^(\d+) × (\d+) - (.*) - ')
            #source_image_metainfo = found.xpath('.//*[@class="f"]//text()').re(ur'^(\d+) × (\d+)(- (.*) )? - ')
            #if source_image_metainfo and len(source_image_metainfo) == 3:
            #    width, height, date = source_image_metainfo

            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_text,
                'text': source_text,
                'display_link': source_displaylink, # the shortened thing

                #'source': response.request.url,
                'search': response.url,
            }
            self.write(result)

        if num_results > self.num_results:
            return
        more_link = page_content.xpath('.//*[@id="nav"][@role="presentation"]//td[@class="cur"]/following-sibling::td/a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)
