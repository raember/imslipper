import json
import re
from pathlib import Path
from typing import Dict, Generator, Tuple

from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from spoofbot import Browser
from spoofbot.adapter import FileCacheAdapter
from urllib3.util import Url, parse_url

P2TYPE = {
    'p1': 'Compositions',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    'p2': 'Collaborations',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    # 'p3',  # ???
    'p4': 'Collections',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    'p5': 'As Performer',  # https://imslp.org/wiki/Category:Verbalis,_Anthony
    'p6': 'As Arranger',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    'p7': 'As Editor',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    'p8': 'As Librettist',  # https://imslp.org/wiki/Category:Anonymous
    'p9': 'As Translator',  # https://imslp.org/wiki/Category:Corder,_Frederick
    'p10': 'As Copyist',  # https://imslp.org/wiki/Category:Bach,_Carl_Philipp_Emanuel
    'p11': 'As Dedicatee',  # https://imslp.org/wiki/Category:Brahms,_Johannes
    'p12': 'Books',  # https://imslp.org/wiki/Category:Brahms,_Johannes
}

class Imslp:
    browser: Browser

    def __init__(self, browser: Browser):
        self.browser = browser

    def get_composers(self) -> Dict[str, Url]:
        url = 'https://imslp.org/index.php?title=Category:People_with_recordings&memberitst=Recordings'
        doc = BeautifulSoup(self.browser.navigate(url).text, features='html5lib')
        js = doc.select_one('div.mw-content-ltr:nth-child(1) > div:nth-child(6) > script:nth-child(2)').string
        del doc
        json_str = re.search(r'\{"s1":[^;]*\}(?=\))', js).group(0)
        composer_by_char = json.loads(json_str)
        composers = {}
        for _, composer_list in composer_by_char['s1'].items():
            for composer in composer_list:
                title = composer.encode().decode().replace(' ', '_')
                composers[composer] = parse_url(
                    f"https://imslp.org/index.php?title=Category:{title}&intersect=Recordings")
        return composers

    def get_publications(self, url: Url) -> Dict[str, Url]:
        # https://imslp.org/wiki/Per_piet%C3%A0%2C_bell'idol_mio_(Bellini%2C_Vincenzo)
        adapter = self.browser.adapter
        if isinstance(adapter, FileCacheAdapter):
            query = dict([kvp.split('=') for kvp in url.query.split('&')])
            adapter.next_request_cache_url = parse_url(f"https://imslp.org/composer/{query['title']}")
        doc = BeautifulSoup(self.browser.navigate(url.url).text, features='html5lib')
        publications = {}
        for js_tag in doc.select('div.jq-ui-tabs > div > script'):
            js = js_tag.string
            if js.startswith('if(typeof catpagejs'):
                json_str = re.search(r'\{"p\d+"[^;]*\}(?=\))', js).group(0)
                entries: dict = json.loads(json_str)
                key = list(entries.keys())[0]
                pub_type = P2TYPE[key]
                publications[pub_type] = {}
                entries_by_char = entries[key]
                for entries_list in (
                        entries_by_char.values()
                        if isinstance(entries_by_char, dict)
                        else entries_by_char):
                    for composition in entries_list:
                        title = composition.encode().decode().split('|')[0]
                        publications[pub_type][title] = parse_url(f"https://imslp.org/wiki/{title.replace(' ', '_')}")
        return publications

    def get_composition(self, url: Url) -> Generator[Tuple[str, int, Url], None, None]:
        # https://imslp.org/wiki/Special:ImagefromIndex/66465/pumu
        adapter = self.browser.adapter
        if isinstance(adapter, FileCacheAdapter):
            adapter.next_request_cache_url = parse_url(f"{url.url}.html")
        doc = BeautifulSoup(self.browser.navigate(url.url).text, features='html5lib')
        div: Tag
        for div in doc.select('div#wpscore_tabs > div.jq-ui-tabs'):
            for id_div in div.select('div.we > div[id]'):
                if not id_div['id'].startswith('IMSLP'):
                    continue
                a = id_div.select_one('span.mh555 > a[title]')
                if a is None:
                    continue
                # file_type = a.text.lower()
                # if file_type not in ('pdf', 'mxl', 'mscz'):
                #     # Music score: https://imslp.org/wiki/Herz_und_Mund_und_Tat_und_Leben,_BWV_147_(Bach,_Johann_Sebastian)
                #     if file_type not in ('zip',):
                #         continue
                #     continue
                a = id_div.select_one('a')
                dl_id = id_div['id']
                title = id_div.select_one('span[title]').text.strip()
                yield title, int(dl_id.lstrip('IMSLP')), parse_url(a['href'])

    def get_score(self, url: Url) -> Tuple[str, bytes]:
        adapter, self.browser.adapter = self.browser.adapter, HTTPAdapter()
        resp = self.browser.navigate(url.url)
        self.browser.adapter = adapter
        if isinstance(adapter, FileCacheAdapter):
            adapter.use_cache = True
        if resp.content[:6] in (b'<!DOCT', b'\n<!DOC', b'<html>'):
            doc = BeautifulSoup(resp.text, features='html5lib')
            if doc.select_one('head > title').text.startswith('Error'):
                # In case a file is pending copyright review:
                # https://imslp.org/wiki/Special:ImagefromIndex/685758
                return None, None
            if resp.url.startswith('https://petruccimusiclibrary.ca') or resp.url.startswith('https://imslp.eu'):
                file_url = parse_url(f"https://petruccimusiclibrary.ca{doc.select_one('tr > td > center > a')['href']}")
            else:
                file_url = parse_url(doc.select_one('span#sm_dl_wait')['data-id'])
            resp = self.browser.navigate(file_url.url, headers={'Accept': 'application/pdf'})
        if resp.status_code != 200 or b'404 Not Found' in resp.content[50:]:
            return None, None
        # if resp.content[:5] != b'%PDF-':
        #     print('Not a PDF')
        filename = Path(parse_url(resp.url).path).name
        return filename, resp.content
