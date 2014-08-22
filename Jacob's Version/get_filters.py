from splinter import Browser
import BeautifulSoup
import time
import urllib

def get_filters(link, html_id, filter_type, start_index):
    filters = []
    with Browser('firefox') as browser:
        browser.driver.set_window_size(1, 1)
        browser.visit(link)
        time.sleep(5)
        for i in range(5):
         browser.find_by_id(html_id).click()
         time.sleep(2)
         tree = BeautifulSoup.BeautifulSoup(browser.html)
         list_class_results = tree.findAll(attrs={'class':'text-warning'})
         for i in list_class_results:
            if filter_type in str(i):
                filters.append(urllib.unquote(str(i.find('a')['href'][start_index:])))
    return [i for i in filters if len(i) > 3]

def get_link_filters():
    return get_filters('http://spambot.rarchives.com/#filter=link','filter-link-next','link',18)

def get_text_filters():
    return get_filters('http://spambot.rarchives.com/#filter=text','filter-text-next','text',18)