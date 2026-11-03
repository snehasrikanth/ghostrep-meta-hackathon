"""A killable local parser after remote inference has reached a terminal state."""
import json
import multiprocessing
from collections import OrderedDict
from app.services.meta.errors import MetaTimeout, MetaUnavailable


class _ValidatedMaskCache:
    """Reuse strictly validated rasters inside one disposable parser process."""
    def __init__(self, decoder, max_bytes=64*1024*1024):
        self.decoder=decoder;self.max_bytes=max_bytes;self.size=0;self.entries=OrderedDict()

    def __call__(self, mask):
        if type(mask.payload) is not str or type(mask.encoding) is not str or type(mask.width) is not int or type(mask.height) is not int:
            return self.decoder(mask)
        key=(mask.encoding,mask.width,mask.height,mask.payload)
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key]
        raster=self.decoder(mask)  # Official structural/canonical checks still run.
        cost=len(raster)+len(mask.payload.encode())
        if cost<=self.max_bytes:
            while self.entries and (self.size+cost>self.max_bytes or len(self.entries)>=2048):
                old_key,old=self.entries.popitem(last=False)
                self.size-=len(old)+len(old_key[3].encode())
            self.entries[key]=raster;self.size+=cost
        return raster


def _parse(send, events, concept, fps):
    try:
        import meta_sam_parser
        from meta_sam_parser import _segmentation
        # The official parser validates each raster, then polygon extraction
        # requests that same raster. Share the strict result, only in this
        # single-request child; never patch the API server's parser bindings.
        cached=_ValidatedMaskCache(meta_sam_parser.decode_mask_to_raster)
        _segmentation.decode_mask_to_raster=cached
        meta_sam_parser.decode_mask_to_raster=cached
        from app.services.meta.sam_parse import document_from_events
        send.send((True, document_from_events(events,concept=concept,fps=fps)))
    except Exception:
        send.send((False,None))
    finally: send.close()


def bounded_document(events, *, concept, fps, timeout=10):
    if len(json.dumps(events).encode()) > 32*1024*1024:
        raise MetaUnavailable('Optional outline response exceeded the parser size limit.')
    context=multiprocessing.get_context('spawn');receive,send=context.Pipe(duplex=False)
    worker=context.Process(target=_parse,args=(send,events,concept,fps),daemon=True)
    worker.start();send.close()
    try:
        if not receive.poll(max(.01,timeout)):
            raise MetaTimeout('Optional outline parsing exceeded its deadline. Skeleton replay is available.')
        ok,result=receive.recv()
        if not ok:raise MetaUnavailable('Optional outline parsing failed. Skeleton replay is available.')
        return result
    finally:
        receive.close();worker.join(.1)
        if worker.is_alive():worker.terminate();worker.join(1)
        if worker.is_alive():worker.kill();worker.join(1)
