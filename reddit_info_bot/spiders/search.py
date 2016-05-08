# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import json
import base64
import six
from collections import OrderedDict
from w3lib.html import get_meta_refresh
from urllib3.filepost import encode_multipart_formdata
from six.moves.urllib.parse import (
    unquote, urlparse, urlsplit, urlunsplit, parse_qsl, urlencode,
)
try:
    from ..util import BytesIO
except ImportError:
    from six import BytesIO
from PIL import Image
from scrapy.http import Request, FormRequest, HtmlResponse
from ..search import find_media_url, SearchResultItem
try:
    from . import InfoBotSpider
except ImportError:
    from scrapy.spiders import Spider

    class InfoBotSpider(Spider):
        def parse_result(self, result):
            return result
        def isredditspam_link(self, link):
            return False
        def isredditspam_text(self, text):
            return False


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

    def parse(self, response):
        content = response.xpath('//body') or ''
        if content:
            self.serp = response.url
        self.logger.info('Visited %s', response.url)

        return self.parse_search(response, content)

    def parse_search(self, response, content):
        raise NotImplementedError


class ImageSearch(Search):

    name = 'imagesearch'

    def __init__(self, *args, **kwargs):
        # search by URL
        if 'image_url' in kwargs:
            self.image_url = kwargs.pop('image_url')
        # search by image
        if 'image_data' in kwargs:
            self.image_data = kwargs.pop('image_data')
            self.filetype = None
            self.fileext = kwargs.get('image_ext') or 'jpg'

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
            request = self.from_data(self.image_data,
                                     filetype=self.filetype,
                                     fileext=self.fileext)
        yield self.pre_search(request)


class KarmaDecay(ImageSearch):

    name = 'imagesearch-karmadecay'

    search_url = 'http://karmadecay.com/'
    search_image_url = 'http://karmadecay.com/index/'

    def from_url(self, image_url):
        # do not 'optimize' .gifv links for KD
        if not image_url.endswith('.gifv'):
            image_url = find_media_url(image_url, self.settings)

        #form_urlencoded = OrderedDict([
        #    ('kdtoolver', 'b1'),
        #    ('q', image_url),
        #])
        #return FormRequest(self.search_url, method='GET', formdata=form_urlencoded)

        # use POST, more in line with browser
        form_multipart = OrderedDict([
            ('MAX_FILE_SIZE', '10485760'),
            ('image', ''),
            ('url', image_url),
            ('search', 'search'),
            ('nsfwfilter', 'off'),
            ('subreddit[pics]', 'off'),
            ('subreddit[funny]', 'off'),
            ('subreddit[wtf]', 'off'),
            ('subreddit[nsfw]', 'off'),
            ('subreddit[others]', 'off'),
            ('subreddit[all]', 'off'),
        ])
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
        headers = {
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def from_data(self, image_data, filetype=None, fileext='png'):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            image_data = ('image.%s' % fileext, image_data)
        form_multipart = OrderedDict([
            ('MAX_FILE_SIZE', '10485760'),
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
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
        headers = {
            b'Content-Type': content_type,
            b'X-Requested-With': b'XMLHttpRequest',
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse_search(self, response, content):
        no_results = content.xpath('//tr[contains(@class, "ns")]') # "No very similar images were found on Reddit."
        if no_results:
            self.logger.info('No search results')
            return

        # ignore 'less similar' results. they're usually completely different
        results = content.xpath('.//div[@id="content"]/table[@class="search"]//tr[@class="result"][following-sibling::tr[@class="ls"]]')
        if not results:
            results = content.xpath('.//div[@id="content"]/table[@class="search"]//tr[@class="result"]')
            if not results:
                self.logger.info('No search results')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
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
                'url': source_link,
                'display_url': None, # has none
                'title': source_title,
                'description': source_text,
                'serp': self.serp,
                'image_url': source_image,
                'image_size': source_image_size,
                'image_filesize': None,
                'image_format': None,
            }

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_link(result['url']):
                result['spam'] = 'url'
            elif self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            result = SearchResultItem(result)
            yield self.parse_result(result)


class Yandex(ImageSearch):

    name = 'imagesearch-yandex'

    search_url = 'https://www.yandex.com/images/search'
    search_image_url = search_url

    def from_url(self, image_url):
        image_url = find_media_url(image_url, self.settings)

        form_urlencoded = OrderedDict([
            ('img_url', image_url),
            ('rpt', 'imageview'),
            ('uinfo', 'sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900'), # some fake browser info
        ])
        return FormRequest(self.search_url, method='GET', formdata=form_urlencoded)

    def from_data(self, image_data, filetype=None, fileext='png'):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            image_data = ('image.%s' % fileext, image_data)
        form_multipart = OrderedDict([
            ('upfile', image_data),
            #('format', 'json'),
            #('request', '[{"block":"b-page_type_search-by-image__link"}]'),
            ('rpt', 'imageview'),
        ])
        form_urlencoded = OrderedDict([
            ('uinfo', 'sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900'), # some fake browser info
            ('rpt', 'imageview'),
        ])
        qstring = '?' + urlencode(form_urlencoded)
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
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
            result['url'] = url

        # mark probable spam
        if self.isredditspam_link(result['url']):
            result['spam'] = 'url'

        result = SearchResultItem(result)
        yield self.parse_result(result)

    def parse_search(self, response, content):
        results = content.xpath('.//ul[@class="other-sites__container"]/li')
        if not results:
            self.logger.info('No search results')
            #similar = content.xpath('.//ul[@class="similar__thumbs"]/li/a') # /@href + /img/@src
            return

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            source_image = found.xpath('a[@class="other-sites__preview-link"]/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "other-sites__meta")]/text()').extract_first()
            source_image_size = [s.strip() for s in source_image_size.split('×'.decode('utf-8'))] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('.//a[contains(@class, "other-sites__title-link")]/@href').extract_first()
            source_displaylink = found.xpath('.//a[contains(@class, "other-sites__outer-link")]/text()').extract_first()
            source_title = found.xpath('.//a[contains(@class, "other-sites__title-link")]/text()').extract_first()
            source_text = found.xpath('.//a[contains(@class, "other-sites__desc")]/text()').extract_first() # not in image upload

            result = {
                'provider': self.__class__.__name__,
                'url': source_link,
                'display_url': None,
                'title': source_title,
                'description': source_text,
                'serp': self.serp,
                'image_url': source_image,
                'image_size': source_image_size,
                'image_filesize': None,
                'image_format': None,
            }

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            yield Request(source_link, callback=self.get_url, meta={'dont_redirect': True, 'result': result})

        if num_results > self.num_results:
            return
        # dont seem like relevant results
        #more_link = content.xpath('.//div[contains(@class, "more_direction_next")]/a[contains(@class, "more__button")]/@href').extract_first()
        #if more_link:
        #    yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)


class Bing(ImageSearch):

    name = 'imagesearch-bing'

    search_url = 'https://www.bing.com/images/searchbyimage'
    search_image_url = 'https://www.bing.com/images/search'

    def from_url(self, image_url):
        image_url = find_media_url(image_url, self.settings)

        if False:
            # prefer non-https URLs, BING can't find images in https:// urls!?
            if image_url.startswith('https'):
                image_url = image_url.replace('https', 'http', True)

            form_urlencoded = OrderedDict([
                ('FORM', 'IRSBIQ'),
                ('cbir', 'sbi'),
                ('imgurl', image_url),
            ])
            return FormRequest(self.search_url, method='GET', formdata=form_urlencoded)

        else:
            # this seems to be a newer version of bing, and seems to finds results
            # for more urls as well
            form_multipart = OrderedDict([
                ('imgurl', image_url),
                ('cbir', 'sbi'),
                ('imageBin', ''),
            ])
            form_urlencoded = OrderedDict([
                ('q', 'imgurl:%s' % image_url),
                ('view', 'detailv2'),
                ('iss', 'sbi'),
                ('FORM', 'IRSBIQ'),
            ])
            qstring = '?' + urlencode(form_urlencoded)
            body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
            headers = {
                b'Accept-Language': b'en-US,en;q=0.5',
                b'Content-Type': content_type,
                b'DNT': b'1',
            }
            return Request(self.search_image_url + qstring, method='POST',
                        body=body, headers=headers, callback=self.parse_image)

    def from_data(self, image_data, filetype=None, fileext='png'):
        # bing transcodes images with javascript, then submits base64-encoded jpeg data...
        image_size = len(image_data) / 1024
        image_data, (width, height) = convert_image(image_data)
        image_data = base64.b64encode(image_data) # base64 encoded submission
        image_data = (None, image_data, None)
        form_multipart = OrderedDict([
            ('imgurl', ''),
            ('cbir', 'sbi'),
            ('imageBin', image_data),
        ])
        form_urlencoded = OrderedDict([
            ('q', ''),
            ('view', 'detailv2'),
            ('iss', 'sbi'),
            ('FORM', 'IRSBIQ'),
            # probably nobody cares about that, but fake it anyway
            ('sbifsz', u'%s x %s · %s kB · %s'.encode('utf-8') \
                    % (width, height, image_size, fileext.encode('utf-8'))),
            ('sbifnm', 'image.%s' % fileext), # our "filename"
            ('thw', width),
            ('thh', height),
        ])
        qstring = '?' + urlencode(form_urlencoded)
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url + qstring, method='POST',
                       body=body, headers=headers, callback=self.parse_image)

    def parse_search(self, response, content):
        results = content.xpath('.//div[@id="sbi_sct_sp"]/div[@class="sbi_sp"]')
        if not results:
            self.logger.info('No search results')
            if "Sorry, we can't search by image with" in response.body:
                self.logger.info('Search was not an image link?')
            elif "We couldn't find any matches for this image." not in response.body:
                self.logger.warning('Unknown search fail.')
            return

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            source_image = found.xpath('div[@class="th"]/a/@href').extract_first()
            source_image_metainfo = found.xpath('div[@class="info"]/div[@class="si"][contains(text(), " x ")]/text()').re(ur'^(.*)·(.*)·(.*)$')
            source_image_size = source_image_metainfo[0]
            source_image_filesize = source_image_metainfo[1]
            source_image_format = source_image_metainfo[2]
            source_image_size = [s.strip() for s in source_image_size.split('x')] # w x h
            source_image_size = 'x'.join(source_image_size)

            source_link = found.xpath('div[@class="info"]/a/@href').extract_first()
            source_title = found.xpath('div[@class="info"]/a/text()').extract_first()
            source_displaylink = found.xpath('div[@class="info"]/div[@class="st"]/text()').extract_first()

            result = {
                'provider': self.__class__.__name__,
                'url': source_link,
                'display_url': source_displaylink, # a shortened url
                'title': source_title,
                'description': None, # has no text description
                'serp': self.serp,
                'image_url': source_image,
                'image_size': source_image_size,
                'image_filesize': '%s KiB' % source_image_filesize,
                'image_format': source_image_format,
            }

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_link(result['url']):
                result['spam'] = 'url'
            elif self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            result = SearchResultItem(result)
            yield self.parse_result(result)

        # There doesn't seem to be any pagination in results here ever! :heart:

    def parse_image(self, response):
        content = response.xpath('//body')
        self.logger.info('Visited %s', response.url)

        def gimmefrigginresults():
            # oookay, no f**kin idea what I'm doing here,
            # lets just grab all the hidden params we can get our grubby hands on
            # and throw 'em back at the service, that usually works

            # first, grab us some vars...
            vaaars = response.xpath('//span[@id="ivd"]/@json-data').extract_first()
            vaaars = json.loads(unquote(vaaars))
            if 'web' in vaaars and '0' in vaaars['web']:
                vaaars = vaaars['web']['0']
            else:
                self.logger.info('No search results or query failure')
                return

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
                ('mid', None),
                ('ccid', None),
                ('vw', None),
                ('simid', '0'),
                ('thid', ''),
                ('thh', vaaars.get('height') or ''),
                ('thw', vaaars.get('width') or ''),
                ('q', ''),
                ('mst', None),
                ('mscr', None),
                ('spurl', ''),
                ('vf', ''),
                ('imgurl', ''),
            ])
            for var in ('mid', 'ccid', 'vw', 'mst', 'mscr'):
                if var in vaaars:
                    val = vaaars[var]
                    if isinstance(val, six.string_types):
                        val = val.replace('+', ' ') # urlunencode-something?
                    blended[var] = val
                else:
                    del blended[var]

            # fourth, assemble
            url = response.urljoin(urlunsplit(('', '', uuuuurl.path, urlencode(blended), '')))

            headers = {
                # and lets look the same as in the last request
                b'Accept-Language': b'en-US,en;q=0.5',
                b'DNT': b'1',
            }
            # finally, see if they are willing to communicate with this encoding
            return Request(url, callback=self.parse_image, headers=headers)


        upload_results = content.xpath('.//div[@id="insights"]')
        if upload_results:
            self.logger.debug('Looks like a valid search result page... without results: %s' % response.url)
            self.serp = response.url
            # now we have the result page, but no results yet... hmmm
            # gotta do some XHR fancyness, preferrably without a javascript interpreter or DOM
            yield gimmefrigginresults()

        if not response.body and response.status == 200:
            # trouble here is we don't know if our query was misunderstood
            # (parameters changed) or if there were simply no results
            self.logger.info('No search results or query failure')
            return

        # well whaddaya know... it worked? whew

        # number of results found (if any)
        total_results = content.xpath('.//ul[@class="insights"]//div[contains(@class, "b_focusLabel")]/text()').re_first(r'^(\d+)')
        if total_results:
            total_results = int(total_results)
        else:
            self.logger.info('No search results or query failure?')

        results = content.xpath('.//ul[@class="insights"]//ul[@class="expbody"]/li')
        #results = content.xpath('.//ul[@class="insights"]//ul[@class="expbody"]/li[a]')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            source_link = found.xpath('a/@href').extract_first()
            source_displaylink = found.xpath('a/div[@class="iscbody"]//ul[@class="b_dataList"]/li[1]/text()').extract_first() # preview link [no protocol]

            source_title = found.xpath('a/div//span[@title]/text()').extract_first()
            source_image_metainfo = found.xpath('a/div[@class="iscbody"]//ul[@class="b_dataList"]/li[2]/text()').re(ur'^(\d+) x (\d+) · (\d+) kB · (.*)$')
            try:
                width, height, source_image_filesize, source_image_format = source_image_metainfo
            except ValueError:
                width, height, source_image_filesize, source_image_format = 0, 0, 0, ''
            source_image_size = '%sx%s' % (width, height)

            #if not source_link or not source_title:
            #    continue

            result = {
                'provider': self.__class__.__name__,
                'url': source_link,
                'display_url': source_displaylink, # the shortened thing (missing scheme)
                'title': source_title,
                'description': None, # has no text description
                'serp': self.serp,
                'image_url': None, # FIXME: does not seem to have direct image links [maybe we can get them though. HACKS]
                'image_size': source_image_size,
                'image_filesize': '%s KiB' % source_image_filesize,
                'image_format': source_image_format,
            }

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_link(result['url']):
                result['spam'] = 'url'
            elif self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            result = SearchResultItem(result)
            yield self.parse_result(result)

        # There doesn't seem to be any pagination in results here ever! :heart:


class Tineye(ImageSearch):

    name = 'imagesearch-tineye'

    search_url = 'https://www.tineye.com/search'
    search_image_url = search_url

    def from_url(self, image_url):
        image_url = find_media_url(image_url, self.settings)

        form_urlencoded = OrderedDict([
            ('search_button', ''),
            ('url', image_url),
        ])
        return FormRequest(self.search_url, method='POST', formdata=form_urlencoded)

    def from_data(self, image_data, filetype=None, fileext='png'):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            image_data = ('image.%s' % fileext, image_data)
        form_multipart = OrderedDict([
            ('image', image_data),
        ])
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse_search(self, response, content):
        results = content.xpath('.//div[@class="results"]//div[@class="row matches"]//div[contains(@class, "match-row")]')
        if not results:
            self.logger.info('No search results')
        if 'Your IP has been blocked' in response.body:
            self.logger.error('Tineye IP ban')
        if '403 Forbidden' in response.body: # hmm, error shouldn't even reach us
            self.logger.error('Tineye blocked us')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            # NOTE: this ignores possible multiple matches per (sub)domains (of the same file), as listed by tineye
            source_image = found.xpath('.//div[@class="match"]/p[contains(@class, "short-image-link")]/a/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[2]/text()').extract_first()
            source_image_size = source_image_size.strip(',')
            source_image_size = [s.strip() for s in source_image_size.split('x')] # w x h
            source_image_size = 'x'.join(source_image_size)
            # TODO: include these
            source_image_format = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[1]/text()').extract_first()
            source_image_format = source_image_format.strip(',')
            source_image_filesize = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[3]/text()').extract_first()
            source_image_filesize = source_image_filesize.strip(',')

            source_link = found.xpath('.//div[@class="match"]/p[not(@class)]/a/@href').extract_first()
            source_title = found.xpath('.//div[@class="match"]/h4[@title]/text()').extract_first()
            source_text = found.xpath('.//div[@class="match"]/p[@class="crawl-date"]/text()').extract_first()

            result = {
                'provider': self.__class__.__name__,
                'url': source_link,
                'display_url': None,
                'title': source_title,
                'description': source_text,
                'serp': self.serp,
                'image_url': source_image,
                'image_size': source_image_size,
                'image_filesize': source_image_filesize,
                'image_format': source_image_format,
            }

            if source_image:
                source_image = os.path.basename(source_image)
                text = '{0} {1} on {2}'.format(source_image, source_image_size, source_title)
                result['title'] = text + ' (%s)' % result['description']

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_link(result['url']):
                result['spam'] = 'url'
            elif self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            result = SearchResultItem(result)
            yield self.parse_result(result)

        if num_results > self.num_results:
            return

        more_link = content.xpath('.//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)


class Google(ImageSearch):

    name = 'imagesearch-google'

    search_url = 'https://www.google.com/searchbyimage'
    search_image_url = 'https://www.google.com/searchbyimage/upload'

    def from_url(self, image_url):
        image_url = find_media_url(image_url, self.settings)

        form_urlencoded = OrderedDict([
            ('image_url', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=form_urlencoded)

    def from_data(self, image_data, filetype=None, fileext='png'):
        if filetype:
            image_data = ('image.bin', image_data, filetype)
        else:
            # content-type guessed from file extension
            image_data = ('image.%s' % fileext, image_data)
        form_multipart = OrderedDict([
            ('image_url', ''),
            ('encoded_image', image_data),
            ('image_content', ''),
            ('filename', ''),
            ('hl', 'en'),
        ])
        body, content_type = encode_multipart_formdata(form_multipart, boundary=None)
        headers = {
            b'Accept-Language': b'en-US,en;q=0.5',
            b'Content-Type': content_type,
            b'DNT': b'1',
        }
        return Request(self.search_image_url, method='POST', body=body, headers=headers)

    def parse_search(self, response, content):
        if 'Images must be smaller than' in response.body:
            # 20MB limit. Result is empty
            # FIXME: retry with a first-frame picture?
            return

        # exclude ads, thanks
        results = content.xpath('.//div[contains(@class, "normal-header")][div[contains(text(), "Pages that include matching images")]]/following-sibling::*//*[@class="rc"]')
        if not results:
            results = content.xpath('.//*[@class="rc"]')
            if not results:
                self.logger.info('No search results')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            source_link = found.xpath('.//*[@class="r"]//a/@href').extract_first()
            source_title = found.xpath('.//*[@class="r"]//a/text()').extract()
            source_title = ''.join(source_title)

            source_displaylink = found.xpath('.//*[@class="s"]//cite/text()').extract_first()
            source_text = found.xpath('.//*[@class="s"]//*[@class="st"]//text()[not(parent::span[@class="f"])]').extract()
            source_text = ''.join(source_text)

            #source_image_metainfo = found.xpath('.//*[@class="f"]//text()').re(ur'^(\d+) × (\d+) - (.*) - ')
            #source_image_metainfo = found.xpath('.//*[@class="f"]//text()').re(ur'^(\d+) × (\d+)(- (.*) )? - ')
            #if source_image_metainfo and len(source_image_metainfo) == 3:
            #    width, height, date = source_image_metainfo

            preview_image = found.xpath('.//*[@class="s"]//div/a/g-img/img/@src')
            source_image = found.xpath('.//*[@class="s"]//div/a[g-img/img]/@href').extract_first()
            if source_image:
                source_image = dict(parse_qsl(urlsplit(source_image).query))
                source_image, source_link2 = source_image['imgurl'], source_image['imgrefurl']

                if not source_link and source_link2:
                    source_link = source_link2

            result = {
                'provider': self.__class__.__name__,
                'url': source_link,
                'display_url': source_displaylink,
                'title': source_text,
                'description': source_text,
                'serp': self.serp,
                'image_url': source_image,
                'image_size': None,
                'image_filesize': None,
                'image_format': None,
            }

            # mark probable spam (and don't count towards result limit)
            if self.isredditspam_link(result['url']):
                result['spam'] = 'url'
            elif self.isredditspam_text(result['title']):
                result['spam'] = 'title'
            elif self.isredditspam_text(result['description']):
                result['spam'] = 'description'
            else:
                num_results += 1

            result = SearchResultItem(result)
            yield self.parse_result(result)

        if num_results > self.num_results:
            return

        more_link = content.xpath('.//*[@id="nav"][@role="presentation"]//td[@class="cur"]/following-sibling::td/a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)
