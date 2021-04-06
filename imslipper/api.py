import json
import re
from pathlib import Path
from typing import Dict, Generator, Tuple

from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from spoofbot import Browser
from spoofbot.adapter import FileCacheAdapter
from urllib3.util import Url, parse_url


class ImslpPage:
    pass


class Composer:
    name: str
    url: Url


class Composition:
    name: str
    url: Url


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

    def get_compositions(self, url: Url) -> Dict[str, Url]:
        # https://imslp.org/wiki/Per_piet%C3%A0%2C_bell'idol_mio_(Bellini%2C_Vincenzo)
        adapter = self.browser.adapter
        if isinstance(adapter, FileCacheAdapter):
            query = dict([kvp.split('=') for kvp in url.query.split('&')])
            adapter.next_request_cache_url = parse_url(f"https://imslp.org/composer/{query['title']}")
        doc = BeautifulSoup(self.browser.navigate(url.url).text, features='html5lib')
        js = doc.select_one('div.jq-ui-tabs > div > script').string
        del doc
        json_str = re.search(r'\{"p1":[^;]*\}(?=\))', js).group(0)
        compositions_by_char = json.loads(json_str)['p1']
        compositions = {}
        for compositions_list in (
                compositions_by_char.values() if isinstance(compositions_by_char, dict) else compositions_by_char):
            for composition in compositions_list:
                title = composition.encode().decode().split('|')[0]
                compositions[title] = parse_url(f"https://imslp.org/wiki/{title.replace(' ', '_')}")
        return compositions

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
