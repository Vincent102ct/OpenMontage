"""P3.5 actual-MP4 QA with viewport-aware facts and complete shot contact sheets."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from tools.story.story_qa import _run, frame_at, gray_frames, loudness, probe, window_volume


def inspect_render(path, video, timeline, subtitle, output, *, scale=1):
    path, output = Path(path), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    facts, issues, warnings = probe(path), [], []
    expected_frames = round(video['duration_seconds'] * video['fps'])
    expected = {'width': round(video['viewport']['width'] * scale), 'height': round(video['viewport']['height'] * scale),
                'fps': float(video['fps']), 'video_codec': 'h264'}
    for key, value in expected.items():
        if facts[key] != value:issues.append(f'{key}: got {facts[key]}, expected {value}')
    if not facts['audio_codec']:issues.append('Missing audio stream')
    if abs(facts['duration_seconds'] - video['duration_seconds']) > 2 / video['fps']:
        issues.append('Container duration differs from the complete planned final boundary')
    decode = _run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], timeout=1800)
    if decode.returncode or decode.stderr.strip():issues.append('Full video/audio decode failed: ' + decode.stderr[:500])
    counter = _run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                    '-show_entries', 'stream=nb_read_frames', '-of', 'json', str(path)])
    try:decoded = int(json.loads(counter.stdout)['streams'][0]['nb_read_frames'])
    except (ValueError, KeyError, IndexError):decoded = -1
    if decoded != expected_frames:issues.append(f'Decoded frame count {decoded} differs from {expected_frames}')
    audio = _run(['ffmpeg', '-hide_banner', '-i', str(path), '-vn', '-af', 'volumedetect', '-f', 'null', '-'])
    maximum = re.findall(r'max_volume:\s*(-?[0-9.]+) dB', audio.stderr)
    max_db = float(maximum[-1]) if maximum else None
    if max_db is None or max_db >= 0:issues.append('Audio peak is missing or reaches clipping level')
    audible = []
    for unit in video['narration']:
        mean = window_volume(path, unit['start_seconds'], unit['end_seconds'])
        audible.append({'unit_id': unit['id'], 'start': unit['start_seconds'], 'end': unit['end_seconds'], 'mean_db': mean})
        if mean is None or mean < -45:issues.append(f'Near-silent narration {unit["id"]}')
    silence = _run(['ffmpeg','-hide_banner','-i',str(path),'-vn','-af',
                    'silencedetect=noise=-45dB:d=0.5','-f','null','-'])
    intervals, beginning = [], None
    for event, value in re.findall(r'silence_(start|end):\s*([0-9.]+)', silence.stderr):
        if event == 'start':beginning = float(value)
        elif beginning is not None:
            intervals.append([beginning,float(value)]);beginning = None
    if beginning is not None:intervals.append([beginning,facts['duration_seconds']])
    for start,end in intervals:
        for unit in video['narration']:
            if min(end,unit['end_seconds']) - max(start,unit['start_seconds']) > 1.5:
                issues.append('Excessive silence inside measured narration '+unit['id'])
    def stamp(value):
        hh, mm, ss, ms = map(int, re.split('[:,]', value))
        return hh * 3600 + mm * 60 + ss + ms / 1000
    srt = Path(subtitle).read_text(encoding='utf-8-sig')
    captions = []
    for block in re.split(r'\n\s*\n', srt.strip()):
        lines = block.splitlines()
        if len(lines) < 3:continue
        a,b = lines[1].split(' --> ');start,end = stamp(a),stamp(b)
        text = ' '.join(lines[2:])
        captions.append({'start':start,'end':end,'text':text})
        if not any(n['start_seconds']-.002 <= start < end <= n['end_seconds']+.002 for n in video['narration']):
            issues.append('Subtitle leaves its measured narration window')
    if ''.join(c['text'] for c in captions).replace(' ','') != ''.join(n['text'] for n in video['narration']).replace(' ',''):
        issues.append('Subtitle source text does not cover every narration unit')
    shots, thumbs = [], []
    for shot in video['shots']:
        at = (shot['start_seconds'] + shot['end_seconds']) / 2
        target = frame_at(path, at, output / (shot['id'] + '.png'), width=320)
        with Image.open(target) as im:
            rgb = im.convert('RGB');gray = np.asarray(rgb.convert('L'))
            blank = float(gray.std()) < 1 or float(gray.mean()) < 1
            if blank:issues.append('Blank/unintended black shot ' + shot['id'])
            thumb = rgb.copy();thumb.thumbnail((320,180))
            tile = Image.new('RGB',(320,205),'#17232a');tile.paste(thumb,((320-thumb.width)//2,0))
            ImageDraw.Draw(tile).text((8,184),f'{shot["id"]} {shot["start_seconds"]:.2f}-{shot["end_seconds"]:.2f}',fill='white')
            thumbs.append(tile)
        shots.append({'shot_id':shot['id'],'start':shot['start_seconds'],'end':shot['end_seconds'],
                      'evidence':str(target),'blank':blank,'environment':shot['location'],
                      'characters':[a['id'] for a in shot['actors']]})
    rows = math.ceil(len(thumbs)/4)
    sheet = Image.new('RGB',(1280,205*rows),'#0c151b')
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%4)*320,(i//4)*205))
    sheet.save(output/'contact-sheet.jpg',quality=90)
    # Seek timestamps rounded to milliseconds can land beyond the final PTS.
    # Select the exact decoded frame index, including the final frame at 30fps.
    final = output/'final-frame.png'
    last = _run(['ffmpeg','-v','error','-i',str(path),'-vf',
                 f'select=eq(n\\,{expected_frames-1}),scale=640:-2','-frames:v','1',str(final)])
    if last.returncode or not final.is_file():issues.append('Final decoded frame is missing: '+last.stderr[:300])
    motion=[]
    for scene in timeline['scenes']:
        for action in scene['actions']:
            if action['action'] not in ('cautious_walk','guarded_reach','startled_reaction','listening_freeze'):continue
            start=action['at_seconds'];end=start+action['duration_seconds']
            frames=gray_frames(path,start,end,step=.2)
            delta=max([float(np.abs(b-a).mean()) for a,b in zip(frames,frames[1:])]+[0])
            motion.append({'shot_id':scene['scene_id'],'action':action['action'],'max_pixel_delta':delta})
    if not motion or not any(v['max_pixel_delta'] > .01 for v in motion):
        issues.append('No actual rendered pixel motion in approved acting windows')
    if any(v['max_pixel_delta'] <= .01 for v in motion):
        warnings.append('Some restrained/off-frame acting windows have very small measured pixel changes; human review required.')
    if [s['shot_id'] for s in shots] != [s['scene_id'] for s in timeline['scenes']]:
        issues.append('Rendered shot manifest differs from complete action timeline')
    return {'passed':not issues,'issues':issues,'warnings':warnings,'facts':facts,'expected':expected,
            'full_decode':{'returncode':decode.returncode,'stderr':decode.stderr[:500]},
            'decoded_frames':decoded,'expected_frames':expected_frames,'audio':{'peak_db':max_db,
            'integrated_lufs':loudness(path),'narration_windows':audible,
            'silence_intervals':intervals,'silence_returncode':silence.returncode},'subtitle_cues':captions,
            'shots':shots,'action_motion':motion,'final_shot':shots[-1]['shot_id'],'final_frame':str(final),
            'contact_sheet':str(output/'contact-sheet.jpg'),'artistic_audio_acceptance':'pending'}
