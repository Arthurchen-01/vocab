# -*- coding: utf-8 -*-
import os, sys, json, re

with open('server.py', 'r', encoding='utf-8') as sf:
    orig = sf.read()

# Execute orig to get SERIES_DATA and EPISODE_DATA
ns = {'__file__': os.path.abspath('server.py')}
exec(orig[:orig.find('class RequestHandler')], ns)
SERIES_DATA = ns['SERIES_DATA']
EPISODE_DATA = ns['EPISODE_DATA']

# Update series data banner
SERIES_DATA['harvard_philosophy']['banner_scene'] = '/assets/scenes/banner_harvard_series.jpg'

# Update episode covers and audio_url
EPISODE_DATA['ep01']['cover_scene'] = '/assets/scenes/scene_trolley.jpg'
EPISODE_DATA['ep02']['cover_scene'] = '/assets/scenes/scene_mignonette.jpg'
EPISODE_DATA['ep03']['cover_scene'] = '/assets/scenes/scene_libertarian.jpg'

for ep_id, ep in EPISODE_DATA.items():
    for w in ep.get('words', []):
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', w['word'].lower()).strip('_')
        w['audio_url'] = f'/assets/audio/{ep_id}_{safe}.mp3'

print('SERIES_DATA and EPISODE_DATA updated in memory.')
