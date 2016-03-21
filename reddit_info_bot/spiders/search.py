# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import logging
import json
from collections import OrderedDict
from pprint import pprint
from w3lib.html import get_meta_refresh
from scrapy.http import Request, FormRequest, HtmlResponse
try:
    from . import InfoBotSpider
except ImportError:
    from scrapy.spiders import Spider

    class InfoBotSpider(Spider):
        def write(self, data):
            yield data

from ..search import optimize_image_url


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
        return FormRequest(self.search_url, method=method, formdata=params)

    def start_requests(self):
        if self.image_url:
            request = self.from_url(self.image_url)
        elif self.image_data:
            request = self.from_data(self.image_data)
        yield self.pre_search(request)


class KarmaDecay(ImageSearch):

    name = 'imagesearch-karmadecay'

    search_url = 'http://karmadecay.com/'

    def from_url(self, image_url):
        params = OrderedDict([
            ('kdtoolver', 'b1'),
            ('q', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def parse(self, response):
        page_content = response.xpath('//body')

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

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('img_url', image_url),
            ('rpt', 'imageview'),
            ('uinfo', 'sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900'), # some fake browser info
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def get_url(self, response):
        result = response.meta['result']

        url = None
        if isinstance(response, HtmlResponse):
            interval, url = get_meta_refresh(response.body, response.url, response.encoding, ignore_tags=())
            result['link'] = url

        self.write(result)

    def parse(self, response):
        page_content = response.xpath('//body')

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
            source_text = found.xpath('.//a[contains(@class, "other-sites__desc")]/text()').extract_first()

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

    def parse(self, response):
        page_content = response.xpath('//body')

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

        # There doesn't seem to be any pagination in the results here?
        if num_results > self.num_results:
            return


class Tineye(ImageSearch):

    name = 'imagesearch-tineye'

    search_url = 'https://www.tineye.com/search'

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('search_button', ''),
            ('url', image_url),
        ])
        #headers = {
        #    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        #    'Accept-Language': 'en-US,en;q=0.5',
        #    'Accept-Encoding': 'gzip, deflate',
        #    'DNT': '1',
        #    'Host': 'www.tineye.com',
        #    'Referer': 'https://www.tineye.com/',
        #}
        return FormRequest(self.search_url, method='POST', formdata=params)

    def parse(self, response):
        page_content = response.xpath('//body')

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
                result['title'] = text + ' ' + result['text']

            self.write(result)

        if num_results > self.num_results:
            return
        more_link = page_content.xpath('.//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)


class Google(ImageSearch):

    name = 'imagesearch-google'

    search_url = 'https://www.google.com/searchbyimage'

    def from_url(self, image_url):
        image_url = optimize_image_url(image_url)

        params = OrderedDict([
            ('image_url', image_url),
        ])
        return FormRequest(self.search_url, method='GET', formdata=params)

    def parse(self, response):
        page_content = response.xpath('//body')

        results = page_content.xpath('.//*[@class="rc"]')
        if not results:
            self.logger.info('No search results')

        num_results = response.meta.get('num_results') or 0 # result counter
        for found in results:
            num_results += 1

            source_link = found.xpath('.//*[@class="r"]//a/@href').extract_first()
            source_text = found.xpath('.//*[@class="s"]//*[@class="st"]//text()')
            source_text = ''.join(source_text.extract())
            result = {
                'provider': self.__class__.__name__,
                'link': source_link,
                'title': source_text,
                'text': source_text,

                #'source': response.request.url,
                'search': response.url,
            }
            self.write(result)

        if num_results > self.num_results:
            return
        more_link = page_content.xpath('.//*[@id="nav"][@role="presentation"]//td[@class="cur"]/following-sibling::td/a/@href').extract_first()
        if more_link:
            yield Request(response.urljoin(more_link), meta={'num_results': num_results}, callback=self.parse)
