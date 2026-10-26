"""New Vietnamese fiction authored for P3.5; not a translation of the English fixture."""
import copy

VI_STORY = ("# [SYNTHETIC TEST] Người đứng dưới đèn\n\n"
    "Minh nhận trông căn hộ của chị trong một đêm. Anh đứng bên cánh cửa khép kín, nghe đèn ngoài hành lang rè rất nhỏ.\n\n"
    "Khi Minh bước ra hành lang, Phương đã đứng dưới đèn. Cô nhìn anh rồi nhìn về đầu dãy nhà, nơi chỉ có một bức tường.\n\n"
    '"Tôi vừa thấy anh đứng ở đằng kia," Phương nói. Nhưng Minh chưa từng rời ngưỡng cửa trước lúc này.\n\n'
    "Minh không trả lời. Hai người đứng yên trong ánh đèn vàng, giữ khoảng cách với bức tường cuối hành lang.\n\n"
    "Tiếng rè bỗng ngừng. Trên tường, bóng của hai người vẫn còn, nhưng giữa chúng xuất hiện thêm một khoảng tối mảnh.\n\n"
    "Minh trở vào căn hộ. Anh không biết Phương còn ở ngoài hay đã về phòng; từ bên trong, anh không nhìn thấy hành lang.\n\n"
    "Ba tiếng gõ chậm vang lên từ phía bức tường. Minh đứng nghe cho đến sáng, không biết ai đã đứng dưới đèn trước khi mình bước ra.")


def vietnamese_draft():
    # Claim remains attributed; the extra darkness is never identified or animated as a person.
    locations = ['LOC_ROOM', 'LOC_HALL', 'LOC_HALL', 'LOC_HALL', 'LOC_HALL', 'LOC_ROOM', 'LOC_ROOM']
    people = [['CHR_MINH'], ['CHR_MINH', 'CHR_PHUONG'], ['CHR_MINH', 'CHR_PHUONG'],
              ['CHR_MINH', 'CHR_PHUONG'], ['CHR_MINH', 'CHR_PHUONG'], ['CHR_MINH'], ['CHR_MINH']]
    events = ['EVT_WAIT', 'EVT_MEET', 'EVT_CLAIM', 'EVT_STILL', 'EVT_BUZZ_END', 'EVT_RETURN', 'EVT_KNOCK']
    def chapter(fmt, indexes):
        return {'intent': 'Tác phẩm hư cấu tự viết; giữ lời kể, lời chứng và kết thúc bỏ ngỏ.',
            'depends_on_changes': [], 'excluded_segments': [], 'chapters': [{'id': f'CH_{fmt}1',
            'title': 'Dưới ngọn đèn', 'beats': [{'id': f'BEAT_{fmt}{i+1:02d}',
                'narration': {'mode': 'verbatim', 'spans': [f'SEG_{n+2:04d}']}, 'event_ids': [events[n]],
                'character_ids': people[n], 'location_id': locations[n],
                'object_ids': ['OBJ_DOOR'] if locations[n] == 'LOC_ROOM' else ['OBJ_LAMP'],
                'sound_cue_ids': ['SND_VI_KNOCK'] if n == 6 else ['SND_VI_BUZZ'] if n in (0, 1) else [],
                'silence_after_seconds': 2 if n in (4, 6) else .6,
                'staging': {'action': 'Giữ nhân vật trong vị trí đã xác lập; không hiện thực hóa lời chứng.',
                    'environment': 'Căn hộ và hành lang ban đêm.', 'camera': 'Giữ khung có chủ ý.',
                    'uncertainty': 'Không xác nhận người được thấy là Minh hoặc xác định nguồn tiếng gõ.',
                    'reveal': False}} for i,n in enumerate(indexes)]}]}
    return {'package_id': 'FIC_P35_VI', 'title': '[SYNTHETIC TEST] Người đứng dưới đèn',
        'authored_by': 'P3.5 synthetic fixture author', 'basis': 'Tác phẩm hư cấu tiếng Việt độc lập viết cho kiểm thử.',
        'semantic_basis': 'Chỉ dựa trên văn bản hư cấu nguồn này.', 'coverage_missing': [],
        'characters': [{'id': cid, 'name': name, 'aliases': [], 'description': 'Người trưởng thành; diện mạo là đề xuất.',
            'identity_status': 'narrated', 'on_screen_policy': 'shown',
            'evidence': [{'segment_id': 'SEG_0002' if cid == 'CHR_MINH' else 'SEG_0003', 'quote': name}]}
            for cid,name in [('CHR_MINH','Minh'),('CHR_PHUONG','Phương')]],
        'locations': [{'id': cid, 'name': name, 'description': name,
            'environment': {'source_details': [name], 'proposed_staging': 'Đề xuất tạo hình cần review.'},
            'evidence': [{'segment_id': 'SEG_0002', 'quote': evidence}]} for cid,name,evidence in [('LOC_ROOM','Căn hộ','căn hộ'),('LOC_HALL','Hành lang','hành lang')]],
        'objects': [{'id': cid, 'name': name, 'description': name, 'persistent': True, 'location_id': loc,
            'evidence': [evidence]} for cid,name,loc,evidence in [('OBJ_DOOR','Cánh cửa','LOC_ROOM','cánh cửa khép kín'),
                                                               ('OBJ_LAMP','Đèn hành lang','LOC_HALL','đèn ngoài hành lang')]],
        'facts': [{'id': 'FACT_CLAIM', 'statement': 'Phương nói đã thấy Minh ở đầu dãy nhà; lời chứng chưa được xác nhận.',
            'kind': 'character_claim', 'reported_by': 'CHR_PHUONG', 'revealed_at': 'SEG_0004',
            'conflicts_with': [], 'evidence': ['"Tôi vừa thấy anh đứng ở đằng kia,"']}],
        'events': [{'id': ev, 'label': label, 'story_phase': 'present', 'certainty': 'depicted',
            'participant_ids': people[i], 'location_id': locations[i],
            'object_ids': ['OBJ_DOOR'] if locations[i]=='LOC_ROOM' else ['OBJ_LAMP'],
            'fact_ids': ['FACT_CLAIM'] if i==2 else [], 'time_markers': [], 'segments': [f'SEG_{i+2:04d}']}
            for i,(ev,label) in enumerate(zip(events,['Minh chờ trong căn hộ','Minh gặp Phương','Phương kể điều đã thấy',
                'Hai người đứng yên','Tiếng rè dừng và khoảng tối xuất hiện','Minh trở vào','Tiếng gõ không rõ nguồn'] ))],
        'dialogue': [{'id': 'DLG_VI', 'channel': 'speech', 'text': '"Tôi vừa thấy anh đứng ở đằng kia,"',
            'speaker_id': 'CHR_PHUONG', 'speaker_label': 'Phương', 'attribution_status': 'proposed',
            'attribution_basis': 'Phương nói', 'evidence': ['"Tôi vừa thấy anh đứng ở đằng kia,"']}],
        'sound_cues': [{'id': 'SND_VI_BUZZ', 'label': 'Tiếng đèn rè', 'kind': 'electronic',
            'event_ids': ['EVT_WAIT','EVT_MEET'], 'proposed_treatment': 'Tiếng điện nhỏ, không lấn lời kể.', 'evidence': ['rè rất nhỏ']},
            {'id': 'SND_VI_KNOCK', 'label': 'Ba tiếng gõ', 'kind': 'diegetic', 'event_ids': ['EVT_KNOCK'],
             'proposed_treatment': 'Ba tiếng gõ khô; không xác định người gõ.', 'evidence': ['Ba tiếng gõ chậm']}],
        'motifs': [], 'ambiguities': [{'id': 'AMB_DOUBLE', 'question': 'Phương đã thấy ai, và ai gõ vào tường?',
            'status': 'unresolved', 'related_ids': ['EVT_CLAIM','EVT_KNOCK','FACT_CLAIM'],
            'production_guidance': 'Giữ lời chứng là lời chứng; không vẽ một Minh thứ hai.', 'evidence': ['không biết ai']}],
        'continuity_rules': [{'id': 'CONT_CLAIM', 'rule': 'Không minh họa lời chứng như sự thật đã biết.',
            'related_ids': ['FACT_CLAIM'], 'evidence': ['Phương nói']}],
        'stickman_production': {'style':'stickman_horror_2d','primary_output':'character_animation_in_horror_environments',
            'forbidden_primary_treatments':['documentary_motion_graphics','text_slideshow','stock_footage_montage',
                'static_image_zoom','infographic_replacement'], 'characters': [],
            'uncertainty_policy':'Không xác nhận người thứ ba hoặc nguồn tiếng gõ.', 'status':'preliminary_not_rendered'},
        'formats': {'short': chapter('S',[1,2,6]), 'long': chapter('L',range(7))}}


def prepare_vi(store, project_id='vi-proof'):
    from tests.studio.visual_bible_fixture import prepare_story
    from studio.visual_bible import prepare_visual_bible, approve_visual_bible
    from studio.scene_plan import prepare_scene_plan, approve_scene_plan
    prepare_story(store, project_id, authored=vietnamese_draft(), source=VI_STORY)
    visual = prepare_visual_bible(store, project_id, {})
    choices = copy.deepcopy(visual['manifest']['choices'])
    for cid,row in choices['characters'].items():
        row.update(asset={'id':'victor_hale' if cid=='CHR_MINH' else 'nora_vale','revision':1},reviewed=True)
    for lid,row in choices['locations'].items():
        row.update(environment={'id':'old_apartment_room' if lid=='LOC_ROOM' else 'dark_apartment_corridor','revision':1},
            lighting={'id':'cold_moonlight' if lid=='LOC_ROOM' else 'flickering_interior','revision':1},reviewed=True)
        if lid=='LOC_HALL':row['flicker_lamp']='lamp_mid'
    for oid,row in choices['props'].items():
        row.update(asset={'id':'interior_door' if oid=='OBJ_DOOR' else 'ceiling_lamp','revision':1},
            anchor='doors.room_door.handle' if oid=='OBJ_DOOR' else 'lamps.lamp_mid.bulb',reviewed=True)
    choices['continuity_reviewed']=True
    visual=prepare_visual_bible(store,project_id,{'base_version':visual['version'],'package_sha256':visual['package_sha256'],
        'manifest_sha256':visual['manifest_sha256'],'choices':choices})
    approve_visual_bible(store,project_id,visual['version'],visual['package_sha256'],visual['manifest_sha256'])
    plan=prepare_scene_plan(store,project_id,{})
    picks=copy.deepcopy(plan['manifest']['choices'])
    for fmt in picks['formats'].values():
        for row in fmt['scenes'].values():row['reviewed']=True
        for row in fmt['shots'].values():
            for line in row['dialogue']:row['dialogue'][line]='voice_over_narration';row['editorial_acknowledged']=True
    picks['coverage_reviewed']=picks['continuity_reviewed']=True
    plan=prepare_scene_plan(store,project_id,{'base_version':plan['version'],'package_sha256':plan['package_sha256'],
        'manifest_sha256':plan['manifest_sha256'],'choices':picks})
    return approve_scene_plan(store,project_id,plan['version'],plan['package_sha256'],plan['manifest_sha256'])
