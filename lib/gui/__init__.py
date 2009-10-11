from __future__ import with_statement
import os, sys, wx, time, re, threading, itertools
from wx import PyDeadObjectError

from lib.gui.scripteditor import EditorFrame
from lib.gui.preview import PreviewFrame, PreviewBase
from lib.gui.filetree import TreePanel
from lib.gui.menu import CreateMenu
from lib.gui.toolbar import CreateToolBar
from lib.gui.constants import ID
from lib.gui.maineditor import MainNotebook
from lib.gui.xformeditor import XformTabs
from lib.gui.renderer import Renderer
from lib.gui._events import InMain
from lib.gui.itemdata import ItemData
from lib.gui.renderdialog import RenderDialog
from lib.gui.config import config, init_config
from lib.gui.savedialog import SaveDialog

from lib import fr0stlib
from lib.fr0stlib import Flame
from lib.pyflam3 import Genome
from lib.decorators import *
from lib.threadinterrupt import ThreadInterrupt, interruptall


class Fr0stApp(wx.App):
    def __init__(self):
        wx.App.__init__(self, redirect=False)
        self.SetAppName('fr0st')
        self.standard_paths = wx.StandardPaths.Get()
        self.config_dir = os.path.join(self.standard_paths.GetUserConfigDir(),
                                       '.fr0st')
        if not os.path.isdir(self.ConfigDir):
            os.makedirs(self.ConfigDir)
        init_config()

    def MainLoop(self):
        frame = MainWindow(None, wx.ID_ANY)
        wx.App.MainLoop(self)

    @property
    def ConfigDir(self):
        return self.config_dir


class MainWindow(wx.Frame):
    wildcard = "Flame file (*.flame)|*.flame|" \
               "All files (*.*)|*.*"
    newfilename = ("Untitled%s.flame" % i for i in itertools.count(1)).next
    scriptrunning = False


    @BindEvents
    def __init__(self,parent,id):
        self.title = "Fractal Fr0st"
        wx.Frame.__init__(self,parent,wx.ID_ANY, self.title)

        # This icon stuff is not working...
##        ib=wx.IconBundle()
##        ib.AddIconFromFile("Icon.ico",wx.BITMAP_TYPE_ANY)
##        self.SetIcons(ib)
        self.CreateStatusBar()
        self.SetDoubleBuffered(True)

        # Launch the render threads
        self.renderer = Renderer(self)
        self.renderdialog = None

        # Creating Frame Content
        CreateMenu(parent=self)
        CreateToolBar(self)
        self.image = ImagePanel(self)
        self.XformTabs = XformTabs(self)
        self.notebook = MainNotebook(self)
        self.grad = self.notebook.grad
        self.canvas = self.notebook.canvas
        self.adjust = self.notebook.adjust

        self.editorframe = EditorFrame(self)
        self.editor = self.editorframe.editor
        self.log = self.editorframe.log

        self.TreePanel = TreePanel(self)
        self.tree = self.TreePanel.tree

        sizer3 = wx.BoxSizer(wx.VERTICAL)
        sizer3.Add(self.notebook,1,wx.EXPAND)

        sizer2 = wx.BoxSizer(wx.VERTICAL)
        sizer2.Add(self.image,0,wx.EXPAND)
        sizer2.Add(self.XformTabs.Selector,0)
        sizer2.Add(self.XformTabs,1,wx.EXPAND)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.TreePanel,0,wx.EXPAND)
        sizer.Add(sizer3,1,wx.EXPAND)
        sizer.Add(sizer2,0,wx.EXPAND)

        self.SetSizer(sizer)

        self._namespace = self.CreateNamespace()
        self.flame = Flame()
        self.flame.add_xform()

        self.previewframe = PreviewFrame(self)

        # Calculate the correct minimum size dynamically.
        sizer.Fit(self)
        self.SetMinSize(self.GetSize())

        # Load frame positions from file
        for window, k in ((self, "Rect-Main"),
                          (self.editorframe, "Rect-Editor"),
                          (self.previewframe, "Rect-Preview")):
            if config[k]:
                rect, maximize = config[k]
                window.SetDimensions(*rect)
                window.Maximize(maximize)

        # Set up paths
        sys.path.append(os.path.join(sys.path[0],"scripts")) # imp in scripts
        self.flamepath = os.path.join(sys.path[0], config["flamepath"])

        if os.path.exists('paths.temp'):
            # TODO: check if another fr0st process is running.
            # Previous session was interrupted
            # TODO: display a message to user explaining situation.
            paths = [i.strip() for i in open('paths.temp')]
            self.TreePanel.RecoverSession(paths)

        else:
            # Normal startup
            try:
                self.OpenFlame(self.flamepath)
            except:
                self.OnFlameNew(e=None)
##                self.OnFlameNew2(e=None)

##        self.tree.ExpandAll()
        self.tree.SelectItem(self.tree.GetItemByIndex((0,0)))

        self.Enable(ID.STOP, False, editor=True)
        self.Show(True)


#-----------------------------------------------------------------------------
# Event handlers

    @Bind(wx.EVT_MENU,id=ID.ABOUT)
    def OnAbout(self,e):
        d= wx.MessageDialog(self,"......",
                            " TODO", wx.OK)
        d.ShowModal()
        d.Destroy()


    @Bind(wx.EVT_CLOSE)
    @Bind(wx.EVT_MENU,id=ID.EXIT)
    def OnExit(self,e):
        # check for renders in progress
        if self.renderdialog and self.renderdialog.OnExit() == wx.ID_NO:
            return

        # check for script diffs
        self.OnStopScript()
##        while self.scriptrunning:
####            self.log.oldstderr.write("sleeping\n")
##            time.sleep(.01)
        if self.editorframe.CheckForChanges() == wx.ID_CANCEL:
            return

        # check for flame diffs
        for itemdata,lst in self.tree.flamefiles:
            if self.CheckForChanges(itemdata, lst) == wx.ID_CANCEL:
                return
            head,ext = os.path.splitext(itemdata[-1])
            path = os.path.join(head + '.temp')
            if os.path.exists(path):
                os.remove(path)

        self.renderer.exitflag = True

        # Remove all temp files
        if os.path.exists('paths.temp'):
            lst = [i.strip()+'.temp' for i in open('paths.temp')]
            for i in lst:
                if os.path.exists(i):
                    os.remove(i)
            os.remove('paths.temp')

        # Save size and pos of each window
        for window, k in ((self, "Rect-Main"),
                          (self.editorframe, "Rect-Editor"),
                          (self.previewframe, "Rect-Preview")):
            maximize = window.IsMaximized()
            # HACK: unmaximizing doesn't seem to work properly in this context,
            # so we just use the previous config settings, even if it's not
            # ideal.
##            window.Maximize(False)
            if maximize:
                (x,y,w,h), _ = config[k]
            else:
                x,y = window.GetPosition()
                w,h = window.GetSize()
            config[k] = (x,y,w,h), maximize
        self.Destroy()


##    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.FNEW)
    def OnFlameNew(self, e):
        path = self.newfilename()
        self.tree.item = self.tree.SetFlames(path)

##        with open('paths.temp','a') as f:
##            f.write(path + '\n')

        return self.tree.item


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.FNEW2)
    def OnFlameNew2(self, e=None, string=None):
        if string:
            flame = Flame(string)
        else:
            flame = Flame()
            flame.add_xform()
            flame.gradient.random(**config["Gradient-Settings"])
        data = ItemData(flame.to_string())

        self.tree.GetChildren((0,)).append((data,[]))
        self.tree.RefreshItems()

        # This is needed to avoid an indexerror when getting child.
        self.tree.Expand(self.tree.itemparent)

        child = self.tree.GetItemByIndex((0, -1))
        self.tree.SelectItem(child)

        # This adds the flame to the temp file, but without any actual changes.
        data.pop(0)
        self.tree.SetItemImage(child, 2)
        self.TreePanel.TempSave(force=True)

        return child


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.FOPEN)
    def OnFlameOpen(self,e):
        dDir,dFile = os.path.split(self.flamepath)
        dlg = wx.FileDialog(
            self, message="Choose a file", defaultDir=dDir,
            defaultFile=dFile, wildcard=self.wildcard, style=wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.flamepath = dlg.GetPath()
            self.OpenFlame(self.flamepath)
        dlg.Destroy()


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.FSAVE)
    def OnFlameSave(self,e):
        self.flamepath = self.tree.GetFlameData(self.tree.itemparent)[-1]
        self.SaveFlame(self.flamepath, confirm=False)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.FSAVEAS)
    def OnFlameSaveAs(self,e):
        path = self.tree.GetFilePath()
        dlg = SaveDialog(self, path=path, name=self.flame.name)
        if dlg.ShowModal() == wx.ID_OK:
            self.flamepath = dlg.GetPath()
            if self.flamepath == path:
                self.flame.name = str(dlg.GetName())
                self.OnFlameNew2(string=self.flame.to_string())
            
            self.SaveFlame(self.flamepath)
        dlg.Destroy()


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.SOPEN)
    def OnScriptOpen(self,e):
        self.editorframe.OnScriptOpen(e)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.RUN)
    def OnRunScript(self,e):
        self.BlockGUI(flag=True)
        self.Execute(self.editor.GetText())


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.STOP)
    def OnStopScript(self,e=None):
        interruptall("Execute")


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.EDITOR)
    def OnEditorOpen(self,e):
        self.editorframe.Show(True)
        self.editorframe.Raise()
        self.editorframe.SetFocus() # In case it's already open in background


    @Bind(wx.EVT_TOOL, id=ID.PREVIEW)
    def OnPreviewOpen(self, e):
        self.previewframe.Show(True)
        self.previewframe.Raise()
        self.previewframe.RenderPreview()


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.UNDO)
    def OnUndo(self,e):
        data = self.tree.itemdata
        self.SetFlame(Flame(string=data.Undo()), rezoom=False)
        self.tree.RenderThumbnail()
        self.tree.SetItemText(self.tree.item, data.name)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.UNDOALL)
    def OnUndoAll(self, e):
        data = self.tree.itemdata
        self.SetFlame(Flame(string=data.UndoAll()), rezoom=False)
        self.tree.RenderThumbnail()
        self.tree.SetItemText(self.tree.item, data.name)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.REDO)
    def OnRedo(self,e):
        data = self.tree.itemdata
        self.SetFlame(Flame(string=data.Redo()), rezoom=False)
        self.tree.RenderThumbnail()
        self.tree.SetItemText(self.tree.item, data.name)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.REDOALL)
    def OnRedoAll(self,e):
        data = self.tree.itemdata
        self.SetFlame(Flame(string=data.RedoAll()), rezoom=False)
        self.tree.RenderThumbnail()
        self.tree.SetItemText(self.tree.item, data.name)


    @Bind((wx.EVT_MENU, wx.EVT_TOOL),id=ID.RENDER)
    def OnRender(self,e):
        if self.renderdialog:
            self.renderdialog.Raise()
        else:
            self.renderdialog = RenderDialog(self, ID.RENDER)

#------------------------------------------------------------------------------

    def OpenFlame(self, path):
        if self.tree.flamefiles:
            filedata, lst = self.tree.flamefiles[0]
            if path == filedata[-1]:
                # File is already open
                dlg = wx.MessageDialog(self, "%s is already open. Do you want to revert to its saved status?" % path,
                                       'Fr0st',wx.YES_NO|wx.CANCEL)
                if dlg.ShowModal() != wx.ID_YES:
                    return
            elif self.CheckForChanges(filedata, lst) == wx.ID_CANCEL:
                # User cancelled when prompted to save changes.
                return

        if os.path.exists(path):
            # scan the file to see if it's valid
            flamestrings = Flame.load_file(path)
            if not flamestrings:
                dlg = wx.MessageDialog(self, "It seems %s is not a valid flame file. Please choose a different flame." % path,
                                       'Fr0st',wx.OK)
                dlg.ShowModal()
                self.OnFlameOpen(None)
                return
        else:
            flamestrings = []

        # Add flames to the tree
        item = self.tree.SetFlames(path, *flamestrings)
        if not flamestrings:
            self.OnFlameNew2(None)

        # Dump the path to file for bookkeeping
##        with open('paths.temp','a') as f:
##            f.write(path + '\n')


    def SaveFlame(self, path, confirm=True):
        lst = Flame.load_file(path) if os.path.exists(path) else []

        if self.tree.parentselected:
            itr = (i for i,_ in self.tree.flamefiles[0][1])
        else:
            itr = (self.tree.itemdata,)

        for i, data in enumerate(itr):
            if data[0] in lst:
                index = lst.index(data[0])
                lst[index] = data[-1]
            else:
                index = len(lst)
                lst.append(data[-1])

            data.Reset()
            
            if path == self.tree.GetFilePath():
                self.tree.SetItemText(self.tree.GetItemByIndex((0,index)),
                                      data.name)
                
        fr0stlib.save_flames(path, *lst)

        # Make sure GUI updates properly
        self.SetFlame(self.flame)


    def CheckForChanges(self, itemdata, lst):
        if any(data.HasChanged() for data,_ in lst):
            path = itemdata[-1]
            dlg = wx.MessageDialog(self, 'Save changes to %s?' % path,
                                   'Fr0st',wx.YES_NO|wx.CANCEL)
            result = dlg.ShowModal()
            if result == wx.ID_YES:
                fr0stlib.save_flames(path, *(data[-1] for data,_ in lst))
            dlg.Destroy()
            return result


    @InMain
    def EndOfScript(self, update):
        self.SetFlame(self.flame, rezoom=False)
        if update:
            self.TreePanel.TempSave()
        self.BlockGUI(False)


    @CallableFrom('MainThread')
    def BlockGUI(self, flag=False):
        """Called before and after a script runs."""
        # TODO: prevent file opening, etc
        self.Enable(ID.RUN, not flag, editor=True)
        self.Enable(ID.STOP, flag, editor=True)
        self.editor.SetEditable(not flag)
        self.scriptrunning = flag


    @CallableFrom('MainThread')
    def Enable(self, id, flag, editor=False):
        """Enables/Disables toolbar and menu items."""
        flag = bool(flag)
        self.tb.EnableTool(id, flag)
        self.menu.Enable(id, flag)
        if editor:
            self.editorframe.tb.EnableTool(id, flag)


    @CallableFrom('MainThread')
    def SetFlame(self, flame, rezoom=True):
        """Changes the active flame and updates all relevant widgets.
        This function can only be called from the main thread, because wx is
        not thread-safe under linux (wxgtk)."""
        self.flame = flame
        if not self.ActiveXform:
            self.ActiveXform = flame.xform[0]
        elif self.ActiveXform._parent != flame:
            if self.ActiveXform.index == None:
                self.ActiveXform = flame.final or flame.xform[0]
            else:
                index = min(self.ActiveXform.index, len(flame.xform)-1)
                self.ActiveXform = flame.xform[index]

        self.image.RenderPreview(flame)
        self.large_preview()
        self.XformTabs.UpdateView()
        self.notebook.UpdateView(rezoom=rezoom)
        if self.renderdialog:
            self.renderdialog.UpdateView()

        # Set Undo and redo buttons to the correct value:
        data = self.tree.itemdata
        self.Enable(ID.UNDOALL, data.undo)
        self.Enable(ID.UNDO, data.undo)
        self.Enable(ID.REDO, data.redo)
        self.Enable(ID.REDOALL, data.redo)


    def CreateNamespace(self):
        """Recreates the namespace each time the script is run to reassign
        the flame variable, etc."""
        namespace = {}
        exec("from lib.fr0stlib import *; __name__='__main__'",namespace)
        namespace.update(dict(self = self, # for debugging only!
                              get_flames = self.tree.GetFlames,
                              save_flames = self.save_flames,
                              load_flames = self.load_flames,
                              preview = self.preview,
                              large_preview = self.large_preview,
                              dialog = self.editorframe.make_dialog,
                              get_file_path = self.tree.GetFilePath,
                              VERSION = fr0stlib.VERSION,
                              update_flame = True))
        return namespace


    @Threaded
    @Locked(blocking=True)
    def Execute(self,string):
        print time.strftime("\n---------- %H:%M:%S ----------")
        start = time.time()

        # split and join fixes linebreak issues between windows and linux
        text = string.splitlines()
        script = "\n".join(text) +'\n'
        self.log._script = text
        flame = Flame(self.flame.to_string())

        try:
            # _namespace is used as globals and locals, to emulate top level
            # module behaviour.
            exec(script,self._namespace)
        except SystemExit:
            pass
        except ThreadInterrupt:
            print("\n\nScript Interrupted")
        finally:
            # Restore the scripting environment to its default state.
            # self.flame is stored in the dict, needs to be transferred.
            update = self._namespace["update_flame"]
            if update:
                flame = self.flame
            self._namespace = self.CreateNamespace()
            self.flame = flame

            # This lets the GUI know that the script has finished.
            self.EndOfScript(update)

        # Keep this out of the finally clause!
        print "\nSCRIPT STATS:\n"\
              "Running time %.2f seconds\n" %(time.time()-start)


    @property
    def flame(self):
        return self._namespace['flame']
    @flame.setter
    def flame(self, flame):
        if not isinstance(flame,Flame):
            raise TypeError("Argument must be a Flame object")
        self._namespace['flame'] = flame


    def preview(self):
        # WARNING: This function is called from the script thread, so it's not
        # Allowed to change any shared state.
        self.image.RenderPreview()
        self.OnPreview()
        time.sleep(.01) # Avoids spamming too many requests.


    def large_preview(self):
        if self.previewframe.IsShown():
            self.previewframe.RenderPreview()


    @InMain
    def OnPreview(self):
        # only update a select few of all the panels.
        # TODO: need to test if this is really necessary.
##        self.XformTabs.UpdateView()
##        self.notebook.UpdateView()
        self.canvas.ShowFlame(rezoom=False)
        self.grad.UpdateView()


    @InMain
    def save_flames(self, path, *flames):
        if not flames:
            raise ValueError("You must specify at least 1 flame to set.")
##        self._namespace["update_flame"] = False
        
        if os.path.exists(path):
            dlg = wx.MessageDialog(self, "%s already exists. Do you want to overwrite?" % path,
                                   'Fr0st',wx.YES_NO)
            if dlg.ShowModal() != wx.ID_YES:
                return
            
        lst = [s if type(s) is str else s.to_string() for s in flames]
        self.tree.SetFlames(path, *lst)
        fr0stlib.save_flames(path, *lst)


    @InMain
    def load_flames(self, path):
        self.OpenFlame(path)


    @InMain
    def OnImageReady(self, callback, (w,h), output_buffer, channels):
        if channels == 3:
            fun = wx.BitmapFromBuffer
        elif channels == 4:
            fun = wx.BitmapFromBufferRGBA
        else:
            raise ValueError("need 3 or 4 channels, not %s" % channels)
        callback(fun(w, h, output_buffer))



class ImagePanel(PreviewBase):

    @BindEvents
    def __init__(self, parent):
        self.parent = parent
        # HACK: we change the class temorarily so the BindEvents decorator
        # catches the methods in the base class.
        self.__class__ = PreviewBase
        PreviewBase.__init__(self, parent)
        self.__class__ = ImagePanel
        self.SetSize((256, 220))
        self.bmp = wx.EmptyBitmap(400,300, 32)


    def GetPanelSize(self):
        return self.Size


    def RenderPreview(self, flame=None):
        """Renders a preview version of the flame and displays it in the gui.

        The renderer takes care of denying repeated requests so that at most
        one redundant preview is rendered."""
        flame = flame or self.parent.flame

        ratio = float(flame.width) / flame.height
        width = 200 if ratio > 1 else int(200*ratio)
        height = int(width / ratio)
        size = width,height
        self.parent.renderer.PreviewRequest(self.UpdateBitmap, flame, size,
                                            **config["Preview-Settings"])


    def UpdateBitmap(self, bmp):
        """Callback function to process rendered preview images."""
        self.bmp = bmp
        self.Refresh()


    @Bind(wx.EVT_PAINT)
    def OnPaint(self, evt):
        fw,fh = self.bmp.GetSize()
        pw,ph = self.GetPanelSize()
        dc = wx.PaintDC(self)
        dc.DrawBitmap(self.bmp, (pw-fw) / 2, (ph-fh) / 2, True)

