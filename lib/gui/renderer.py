import wx, time, sys, traceback
from threading import Thread

from lib.decorators import Catches, Threaded
from lib.render import render
from lib.gui.config import config
from _events import ThreadMessageEvent


class Renderer():
    def __init__(self, parent):
        self.parent = parent
        self.previewqueue = []
        self.bgqueue = []
        self.thumbqueue = []
        self.exitflag = None
        self.previewflag = 0
        self.bgflag = 0
        if "-debug" not in sys.argv:
            # TODO: remove this.
            self.RenderLoop()
            self.bgRenderLoop()


    def ThumbnailRequest(self, callback, *args, **kwds):
        """Schedules a genome to be rendered as soon as there are no previous
        or higher priority requests pending."""
        # These settings are hardcoded on purpose, they can't be overridden
        # by the calling code.
        kwds["nthreads"] = 1
        kwds["fixed_seed"] = True
        kwds["renderer"] = "flam3"
        
        self.thumbqueue.append((callback,args,kwds))


    def PreviewRequest(self, callback, *args, **kwds):
        """Schedules a render immediately after the current render is done.
        Cancels previous requests (assuming they are obsolete), but leaves the
        normal request queue intact."""
        kwds["nthreads"] = 1
        kwds["fixed_seed"] = True
        kwds["renderer"] = kwds.get("renderer", config["renderer"])
        self.previewflag = 1
        
        self.previewqueue = [(callback,args,kwds)]

        
    def LargePreviewRequest(self, callback, *args, **kwds):
        """Makes a preview request with a callback function."""
        prog_func = kwds.get("progress_func", None)
        if not prog_func:
            raise KeyError("You must specify a progress function")
        kwds["progress_func"] = self.prog_wrapper(prog_func, "previewflag")
        kwds["renderer"] = kwds.get("renderer", config["renderer"])
        self.previewflag = 1

        # This is an append so that a simultaneous request for small and
        # large previews goes through.
##        self.previewqueue = [(callback,args,kwds)]
        self.previewqueue.append((callback,args,kwds))


    def RenderRequest(self, callback, *args, **kwds):
        """Makes a render request run in a different thread than previews,
        so it can be paused."""
        prog_func = kwds.get("progress_func", None)
        if not prog_func:
            raise KeyError("You must specify a progress function")
        kwds["progress_func"] = self.prog_wrapper(prog_func, "bgflag")
        kwds["renderer"] = kwds.get("renderer", config["renderer"])

        self.bgqueue = [(callback,args,kwds)]
        

    @Threaded
    @Catches((TypeError, wx.PyDeadObjectError))
    def RenderLoop(self):
        while not self.exitflag:
            queue = self.previewqueue or self.thumbqueue
            if queue:
                self.bgflag = 2 # Pauses the other thread
                self.process(*queue.pop(0))
                self.bgflag = 0
            else:
                time.sleep(.01)  # Ideal interval needs to be tested


    @Threaded
    @Catches((TypeError, wx.PyDeadObjectError))
    def bgRenderLoop(self):
        while not self.exitflag:
            if self.bgqueue:
                self.process(*self.bgqueue.pop(0))
            else:
                time.sleep(.01)


    def process(self, callback, args, kwds):
        self.previewflag = 0
        try:
            output_buffer = render(*args,**kwds)
        except Exception:
            # Make sure render thread never crashes due to malformed flames.
            traceback.print_exc()
            return
        
        if kwds["renderer"] == 'flam4':
            channels = 4
        else:
            channels = kwds.get('channels', 3)
        # args[1] is always size...
        evt = ThreadMessageEvent(-1, callback, args[1], output_buffer, channels)
        wx.PostEvent(self.parent.image, evt)
        

    def prog_wrapper(self, f, flag):
        def prog_func(*args):
            return max(getattr(self, flag), self.exitflag, f(*args))
        return prog_func

    
