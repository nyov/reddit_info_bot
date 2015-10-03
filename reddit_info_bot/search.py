# -*- coding: utf-8 -*-
from __future__ import (absolute_import, unicode_literals, print_function)
import os
import logging
import urllib2
import cookielib
import BeautifulSoup
import requests
import re
from parsel import Selector

logger = logging.getLogger(__name__)


def get_google_results(image_url, limit=15): #limit is the max number of results to grab (not the max to display)
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get('https://www.google.com/searchbyimage?image_url={0}'.format(image_url), headers=headers).content
    response_text += requests.get('https://www.google.com/searchbyimage?image_url={0}&start=10'.format(image_url), headers=headers).content
    #response_text = response_text[response_text.find('Pages that include'):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    print(len(response_text))
    print(response_text)
    list_class_results = tree.findAll(attrs={'class':'r'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].find('a')['href'],re.sub('<.*?>', '', re.sub('&#\d\d;', "'", ''.join([str(j) for j in list_class_results[i].find('a').contents])))) for i in xrange(limit)]
    return results

def get_bing_results(image_url, limit=15):
    cj = cookielib.MozillaCookieJar('cookies.txt')
    cj.load()
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', config['SEARCH_USER_AGENT'])]
    response_text = opener.open("https://www.bing.com/images/searchbyimage?FORM=IRSBIQ&cbir=sbi&imgurl="+image_url).read()
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'sbi_sp'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    if limit >= len(list_class_results):
        limit = len(list_class_results)
    results = [(list_class_results[i].findAll(attrs={'class':'info'})[0].find('a')['href'],list_class_results[i].findAll(attrs={'class':'info'})[0].find('a').contents[0]) for i in xrange(limit)]
    return results

def get_yandex_results(image_url, limit=15):
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get("https://www.yandex.com/images/search?img_url={0}&rpt=imageview&uinfo=sw-1440-sh-900-ww-1440-wh-775-pd-1-wp-16x10_1440x900".format(image_url), headers=headers).content
    response_text = response_text[response_text.find("Sites where the image is displayed"):]
    tree = BeautifulSoup.BeautifulSoup(response_text)
    list_class_results = tree.findAll(attrs={'class':'link other-sites__title-link i-bem'})
    if len(list_class_results) == 0:
        raise IndexError('No results')
    results = []
    for a in list_class_results:
        a = str(a)
        b = "https:"+a[a.find('href="')+6:a.find('" target="')]
        filtered_link = re.compile(r'\b(amp;)\b', flags=re.IGNORECASE).sub("",b)
        try:
            redirect_url = urllib2.urlopen(filtered_link).geturl()
            text = a[a.find('"_blank">')+9:a.find('</a>')]
            results.append((redirect_url,text))
        except: pass #this site bands bots and cannot be accessed
    if limit >= len(results):
        limit = len(results)
    return results[:limit]

def get_karmadecay_results(image_url, limit=15):
    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response_text = requests.get("http://www.karmadecay.com/search?kdtoolver=b1&q="+image_url, headers=headers).content
    if "No very similar images were found." in response_text:
        return []
    raw_results_text = response_text[response_text.find(":--|:--|:--|:--|:--")+20:response_text.find("*[Source: karmadecay]")-2]
    raw_results = raw_results_text.split("\n")
    results = [(i[i.find("(",i.find(']'))+1:i.find(")",i.find(']'))],i[i.find("[")+1:i.find("]")]) for i in raw_results]
    return results #[(link,text)]

def get_tineye_results(image_url, limit=15):
    def extract(r, count):
        sel = Selector(text=r.content.decode(r.encoding))
        page = sel.xpath('//div[@class="results"]//div[@class="row matches"]//div[contains(@class, "match-row")]')
        if not page:
            raise IndexError('No search results')
        if 'Your IP has been blocked' in page:
            print('IP banned')
            raise IndexError('No search results')
        if '403 Forbidden' in page: # hmm, something else?
            raise IndexError('No search results')

        results = []
        for found in page:
            count -= 1
            if count < 0:
                break # stop after our search limit
            source_image = found.xpath('.//div[@class="match"]/p[contains(@class, "short-image-link")]/a/@href').extract_first()
            source_image_size = found.xpath('.//div[contains(@class, "match-thumb")]/p/span[2]/text()').extract_first()
            source_link = found.xpath('.//div[@class="match"]/p[not(@class)]/a/@href').extract_first()
            source_title = found.xpath('.//div[@class="match"]/h4[@title]/text()').extract_first()
            #source_text = found.xpath('.//div[@class="match"]/p[@class="crawl-date"]/text()').extract_first()

            if source_image:
                source_image = os.path.basename(source_image)
                text = '{0} {1} on {2}'.format(source_image, source_image_size, source_title)
                results += [(source_link, text)]
        return results # [(link,text)]

    headers = {}
    headers['User-Agent'] = config['SEARCH_USER_AGENT']
    response = requests.post("https://www.tineye.com/search", data={'url': image_url})

    results = extract(response, limit)
    limit = limit - len(results)
    if limit > 0: # try another page
        sel = Selector(text=response.content.decode(response.encoding))
        next_link = sel.xpath('//div[@class="pagination"]/span[@class="current"]/following-sibling::a/@href').extract_first()
        if next_link:
            response = requests.get(response.url + '?page=2')
            results += extract(response, limit)

    return results
