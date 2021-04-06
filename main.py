#!/usr/bin/env python3
import logging
from datetime import timedelta
from pathlib import Path

from requests.packages.urllib3.util.retry import Retry
from spoofbot import Firefox
from spoofbot.adapter import FileCacheAdapter

from imslipper.api import Imslp

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)
logging.getLogger('chardet.charsetprober').setLevel(logging.INFO)
logging.getLogger('chardet.universaldetector').setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s %(levelname)-8s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
log = logging.getLogger(__name__)

if __name__ == '__main__':
    sess = Firefox()
    jsn = sess.get('https://ipinfo.io/json', headers={'Accept': 'application/json'}).json()
    log.info(f"Public ip: {jsn['ip']}")
    sess.adapter = FileCacheAdapter(max_retries=Retry(total=5, backoff_factor=3, status_forcelist=[502, 503, 504]))
    sess.request_timeout = timedelta(seconds=2.0)
    sess.cookies['imslp_wikiLanguageSelectorLanguage'] = 'en'
    sess.cookies['imslpdisclaimeraccepted'] = 'yes'
    imslp = Imslp(sess)
    # imslp.get_score(parse_url('https://imslp.org/wiki/Special:ImagefromIndex/551285'))
    # imslp.get_score(parse_url('https://imslp.org/wiki/Special:ImagefromIndex/284577'))
    # exit(0)
    composer_offset = 0
    composition_offset = 0
    score_offset = 0
    for composer_name, url in list(imslp.get_composers().items())[composer_offset:]:
        log.info(f"Fetching composer: {composer_name}")
        for composition_name, url in list(imslp.get_compositions(url).items())[composition_offset:]:
            log.info(f"  Fetching composition: {composition_name}")
            for title, dl_id, url in list(imslp.get_composition(url))[score_offset:]:
                path = Path('out', composer_name, composition_name.replace('/', '_'))
                files = list(path.glob(f"IMSLP{dl_id}*"))
                if len(files) == 0:
                    log.info(f"    Fetching score: {title} ({dl_id})")
                    filename, bytes = imslp.get_score(url)
                    if filename is None or bytes is None:
                        log.warning("      Failed to fetch score")
                        continue
                    path /= Path(filename)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with open(path, 'wb') as fp:
                        fp.write(bytes)
                    del bytes
                elif len(files) == 1:
                    log.info(f"    Score already present: {title} ({dl_id}) at '{files[0]}'")
                else:
                    log.error(f"    Matched too many files!\n{list(filter(str, files))}")
                    exit(1)
                score_offset = 0
            composition_offset = 0
