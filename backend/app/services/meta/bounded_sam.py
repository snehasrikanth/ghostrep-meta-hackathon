"""A cancellable, wall-clock-bounded SAM request. No retry or detached HTTP work.

Background Responses permit explicit cancellation; foreground stream read
 timeouts do not. IDs exist only in a private cleanup journal, never logs.
"""
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
import httpx
from app.services.meta.errors import MetaTimeout, MetaUnavailable


async def video_events(settings, path: Path, body: dict, *, client=None, total_seconds=90.0) -> tuple[list[dict], dict]:
    owned = client is None
    client = client or httpx.AsyncClient(base_url=settings.meta_base_url.rstrip('/')+'/',
        headers={'Authorization':'Bearer '+settings.model_api_key}, transport=httpx.AsyncHTTPTransport(retries=0))
    started=time.monotonic(); reserve=min(10,total_seconds*.2); file_id=response_id=None; terminal=False; cancelled=False; deleted=False
    journal=settings.data_dir/'sam-cleanup-pending.json'
    def remaining(): return max(.01,total_seconds-reserve-(time.monotonic()-started))
    async def request(method,url,**kwargs):
        response=await client.request(method,url,timeout=min(10,remaining()),**kwargs)
        response.raise_for_status();return response.json()
    error=None; events=[]; timings={}; stamp=time.monotonic()
    try:
        async with asyncio.timeout(max(.01,total_seconds-reserve)):
            with path.open('rb') as handle:
                upload=await request('POST','files',data={'purpose':'user_data'},files={'file':(path.name,handle,'video/mp4')})
            file_id=upload['id'];timings['upload']=round(time.monotonic()-stamp,3);stamp=time.monotonic()
            request_body={**body,'stream':False,'background':True}
            request_body['input'][0]['content']=[p if p.get('type')!='input_video' else {**p,'file_id':file_id} for p in body['input'][0]['content']]
            response=await request('POST','responses',json=request_body)
            response_id=response.get('id')
            while response.get('status') in {'queued','in_progress'}:
                if not response_id: raise ValueError('Background response has no id')
                await asyncio.sleep(min(.5,remaining()))
                response=await request('GET','responses/'+response_id)
            timings['provider']=round(time.monotonic()-stamp,3)
            terminal=response.get('status') in {'completed','failed','cancelled','incomplete'}
            if response.get('status')!='completed': raise ValueError('SAM did not complete')
            text=''.join(part.get('text','') for item in response.get('output',[]) for part in item.get('content',[]) if part.get('type')=='output_text')
            events=[{'type':'response.output_text.delta','delta':text,'item_id':'sam-result','output_index':0,'content_index':0},
                    {'type':'response.output_text.done','text':text,'item_id':'sam-result','output_index':0,'content_index':0},
                    {'type':'response.completed','response':response}]
    except TimeoutError:
        error=MetaTimeout('Optional outlines exceeded their total deadline. Skeleton replay is available; no automatic retry was made.')
    except Exception:
        error=MetaUnavailable('Optional outlines were unavailable. Skeleton replay is available; no automatic retry was made.')
    finally:
        # These are explicit remote operations, separately bounded. A network
        # partition cannot prove cancellation; retain a private recovery journal.
        if response_id and not terminal:
            try:
                async with asyncio.timeout(reserve/2):
                    r=await client.post('responses/'+response_id+'/cancel',timeout=max(.01,reserve/2));r.raise_for_status()
                    cancelled=r.json().get('status') in {'cancelled','completed','failed','incomplete'}
            except Exception: pass
        if file_id:
            try:
                async with asyncio.timeout(reserve/2):
                    r=await client.delete('files/'+file_id,timeout=max(.01,reserve/2));r.raise_for_status();deleted=True
            except Exception: pass
        if file_id and (not deleted or (not terminal and not cancelled)):
            pending=[]
            if journal.exists():
                try:pending=json.loads(journal.read_text())
                except ValueError:pass
            pending.append({'file_id':file_id,'response_id':response_id,'cancellation_confirmed':cancelled or terminal,'file_deleted':deleted})
            journal.parent.mkdir(parents=True,exist_ok=True);journal.write_text(json.dumps(pending));journal.chmod(0o600)
        if error and file_id and not terminal and not cancelled:
            error.args=(str(error)+" Provider cancellation is unconfirmed; operator cleanup review is needed before another outline request.",)
        if owned: await client.aclose()
    info={'total_seconds':round(time.monotonic()-started,3),'cancellation_confirmed':cancelled or terminal,'file_deleted':deleted,'timings':timings}
    if error:
        setattr(error,'cleanup',info);raise error
    return events,info
