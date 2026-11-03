"""Mock HTTP lifecycle and monotonic deadlines; never provider-latency evidence."""
import asyncio,json,time
import httpx
import pytest
from app.config import Settings
from app.services.meta.bounded_sam import video_events
from app.services.meta.sam import sam_request
from app.services.meta.errors import MetaTimeout,MetaUnavailable


def test_slow_background_response_is_cancelled_and_file_cleanup_attempted(tmp_path):
    paths=[]
    async def handler(req):
        path=req.url.path;paths.append((req.method,path))
        if path=='/files' and req.method=='POST':return httpx.Response(200,json={'id':'file-fictional'})
        if path=='/responses' and req.method=='POST':
            body=json.loads(req.content);assert body['background'] and body['stream'] is False
            return httpx.Response(200,json={'id':'response-fictional','status':'queued'})
        if path.endswith('/cancel'):return httpx.Response(200,json={'status':'cancelled'})
        if req.method=='DELETE':return httpx.Response(200,json={'deleted':True})
        return httpx.Response(200,json={'id':'response-fictional','status':'in_progress'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='http://offline/') as client:
            return await video_events(Settings(_env_file=None,data_dir=tmp_path),tmp_path/'color.mp4',sam_request('sam-3.1','pending','person'),client=client,total_seconds=.2)
    (tmp_path/'color.mp4').write_bytes(b'fictional protocol input')
    started=time.monotonic()
    with pytest.raises(MetaTimeout):asyncio.run(run())
    assert time.monotonic()-started<.8
    assert ('POST','/responses/response-fictional/cancel') in paths
    assert ('DELETE','/files/file-fictional') in paths
    assert not (tmp_path/'sam-cleanup-pending.json').exists()
    assert paths.count(('POST','/responses'))==1


def test_failed_cancel_is_explicit_private_journal_not_retried(tmp_path):
    async def handler(req):
        if req.url.path=='/files':return httpx.Response(200,json={'id':'private-file'})
        if req.url.path=='/responses':return httpx.Response(200,json={'id':'private-response','status':'queued'})
        if req.url.path.endswith('/cancel'):return httpx.Response(503)
        return httpx.Response(200,json={'status':'in_progress'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='http://offline/') as client:
            return await video_events(Settings(_env_file=None,data_dir=tmp_path),tmp_path/'x.mp4',sam_request('sam-3.1','pending','person'),client=client,total_seconds=.1)
    (tmp_path/'x.mp4').write_bytes(b'fixture')
    with pytest.raises(MetaTimeout):asyncio.run(run())
    journal=tmp_path/'sam-cleanup-pending.json';assert journal.exists()
    assert json.loads(journal.read_text())[0]['cancellation_confirmed'] is False
    assert journal.stat().st_mode & 0o077 == 0


def test_local_parser_deadline_terminates_child(tmp_path):
    import multiprocessing
    from app.services.meta.parse_deadline import bounded_document
    from app.services.meta.sam_parse import stream_events
    before={p.pid for p in multiprocessing.active_children()}
    with pytest.raises(MetaTimeout):
        bounded_document(stream_events(""),concept="person",fps=10,timeout=.001)
    assert {p.pid for p in multiprocessing.active_children()}==before


@pytest.mark.parametrize("realistic_masks",[False,True])
def test_runtime_background_success_reaches_real_local_parser_and_cleans_up(tmp_path, monkeypatch, realistic_masks):
    from unittest.mock import Mock
    from app.services.meta.sam import SamProvider
    from tests.test_meta_offline import _person_events
    events=_person_events()
    text=''.join(e.get('delta','') for e in events if e.get('type')=='response.output_text.delta')
    width,height=40,30
    if realistic_masks:
        # 218 masks approximate the recent 22-second/10fps uploads. This is
        # generated geometry, not personal footage or accuracy evidence.
        from meta_sam_parser._mask_codec import _encode_raster
        from app.services.meta.sam_parse import mask_wire
        width,height=360,640
        raster_w,raster_h=120,240
        base=[int(15<x<105 and 10<y<230) for y in range(raster_h) for x in range(raster_w)]
        lines=[]
        for i in range(218):
            raster=base.copy();raster[(30+i//80)*raster_w+20+i%80]=0
            payload=_encode_raster(raster,raster_w,raster_h)
            lines.append(mask_wire(frame=i,object_id=0,box=(120,20,240,260),source=(width,height),payload=payload,raster=(raster_h,raster_w),confidence=.95))
        text='\n'.join(lines)+'\n'
    requests=[]
    async def handler(request):
        requests.append((request.method,request.url.path))
        if request.url.path=='/files' and request.method=='POST':
            return httpx.Response(200,json={'id':'file-fixture'})
        if request.url.path=='/responses':
            body=json.loads(request.content)
            assert body['background'] is True and body['stream'] is False
            assert body['input'][0]['content'][1]['file_id']=='file-fixture'
            return httpx.Response(200,json={'id':'response-fixture','status':'completed',
                'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]})
        if request.method=='DELETE':return httpx.Response(200,json={'deleted':True})
        raise AssertionError('Unexpected request')
    constructor=httpx.AsyncClient
    monkeypatch.setattr('app.services.meta.bounded_sam.httpx.AsyncClient',lambda **_:constructor(transport=httpx.MockTransport(handler),base_url='http://offline/'))
    clip=tmp_path/'schematic.mp4';clip.write_bytes(b'fictional protocol video')
    settings=Settings(_env_file=None,data_dir=tmp_path,segmentation_provider='meta_live')
    gateway=Mock()
    result=SamProvider(settings,gateway).segment_video(clip,218 if realistic_masks else 60,fps=10,media={'codec':'h264','width':width,'height':height})
    assert result['available'] and result['tracks'] and result['file_deleted']
    assert result['stage_timings']['parsing']>=0
    if realistic_masks:
        assert len(result['tracks'][0]['frames'])==218
        assert all(frame['polygon'] for frame in result['tracks'][0]['frames'])
    assert requests==[('POST','/files'),('POST','/responses'),('DELETE','/files/file-fixture')]
    assert not (tmp_path/'sam-cleanup-pending.json').exists()


def test_decode_failure_has_specific_private_safe_diagnostics(tmp_path,monkeypatch):
    from unittest.mock import Mock
    from app.services.meta.sam import SamProvider
    from tests.test_meta_offline import _person_events
    async def provider(*args,**kwargs):
        assert kwargs['total_seconds']>90  # Provider still has its own bounded allocation.
        return _person_events(),{'file_deleted':True,'timings':{}}
    def decode(*args,**kwargs):
        assert 40<kwargs['timeout']<=45
        raise MetaTimeout('Optional outline parsing exceeded its deadline.')
    monkeypatch.setattr('app.services.meta.bounded_sam.video_events',provider)
    monkeypatch.setattr('app.services.meta.parse_deadline.bounded_document',decode)
    gateway=Mock()
    with pytest.raises(MetaTimeout):
        SamProvider(Settings(_env_file=None,data_dir=tmp_path,segmentation_provider='meta_live'),gateway).segment_video(tmp_path/'private-name.mp4',218,media={'codec':'h264'})
    record=gateway.note.call_args.kwargs
    assert record['stage']=='parsing' and record['error_type']=='MetaTimeout'
    assert 'private-name' not in json.dumps(record)


def test_pending_remote_cleanup_blocks_another_request(tmp_path):
    from unittest.mock import Mock
    from app.services.meta.sam import SamProvider
    from app.services.meta.gateway import MetaBlocked
    (tmp_path/'sam-cleanup-pending.json').write_text('[]')
    gateway=Mock()
    with pytest.raises(MetaBlocked,match='cleanup review'):
        SamProvider(Settings(_env_file=None,data_dir=tmp_path,segmentation_provider='meta_live'),gateway).segment_video(tmp_path/'x.mp4',50,media={'codec':'h264'})
    assert not gateway.method_calls


def test_child_cache_preserves_official_results_without_patching_parent():
    import meta_sam_parser
    from app.services.meta.sam_parse import document_from_events
    from app.services.meta.parse_deadline import bounded_document
    from tests.test_meta_offline import _person_events
    original=meta_sam_parser.decode_mask_to_raster
    events=_person_events()
    expected=document_from_events(events,concept='person',fps=10)
    assert bounded_document(events,concept='person',fps=10,timeout=10)==expected
    assert meta_sam_parser.decode_mask_to_raster is original


def test_cache_keeps_strict_validation_and_bounds_memory():
    from dataclasses import replace
    from unittest.mock import Mock
    from types import SimpleNamespace
    from meta_sam_parser import SegmentationMask,decode_mask_to_raster
    from meta_sam_parser._errors import InvalidSegmentationMaskError
    from app.services.meta.parse_deadline import _ValidatedMaskCache
    from tests.test_meta_offline import _rectangle
    decoder=Mock(wraps=decode_mask_to_raster);cache=_ValidatedMaskCache(decoder)
    mask=SegmentationMask(encoding='one_bit',payload=_rectangle(),width=8,height=6)
    assert cache(mask)==cache(mask);assert decoder.call_count==1
    with pytest.raises(InvalidSegmentationMaskError):cache(replace(mask,width=True))
    with pytest.raises(InvalidSegmentationMaskError):cache(replace(mask,payload='!invalid'))
    bounded=_ValidatedMaskCache(lambda _:b'1234',max_bytes=10)
    for value in ('a','b','c'):
        bounded(SimpleNamespace(encoding='one_bit',payload=value,width=4,height=1))
    assert bounded.size<=10 and len(bounded.entries)==2
