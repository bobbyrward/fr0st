from __future__ import with_statement
import wx, os, sys, re
from wx import stc

from fr0stlib.decorators import *
from fr0stlib.gui.toolbar import CreateEditorToolBar
from fr0stlib.gui.menu import CreateEditorMenu
from fr0stlib.gui.constants import ID
from fr0stlib.gui.scriptutils import DynamicDialog
from fr0stlib.gui._events import EVT_THREAD_MESSAGE, ThreadMessageEvent, InMain


class EditorFrame(wx.Frame):

    _new = False # True when script doesn't have a saved version to revert to.
    
    @BindEvents    
    def __init__(self,parent):
        self.title = "Script Editor"
        self.parent = parent
        wx.Frame.__init__(self,parent,wx.ID_ANY, self.title)

        wx.GetApp().LoadIconsInto(self)

        CreateEditorMenu(self)
        CreateEditorToolBar(self)
        self.SetSize((865,500))

        splitter = wx.SplitterWindow(self, -1)
        self.editor = CodeEditor(splitter, self)
        self.log = MyLog(splitter)
        splitter.SplitVertically(self.editor, self.log, -264)
        splitter.SetSashGravity(1.0) # Keeps the log constant when resizing

        self.wildcard = "Python source (*.py;*.pyw)|*.py;*.pyw|" \
                        "All files (*.*)|*.*"

        # Load the default script
        self.scriptpath = os.path.join(wx.GetApp().AppBaseDir, 'scripts', 'default.py')

        if not os.path.exists(self.scriptpath):
            self.scriptpath = os.path.join(wx.GetApp().ScriptsDir, 'default.py')

        self.OpenScript(self.scriptpath)


    @Bind(wx.EVT_CLOSE)
    @Bind(wx.EVT_MENU,id=ID.EXIT)
    def OnExit(self,e):        
        if self.CheckForChanges() == wx.ID_CANCEL:
            return
        self.Show(False)
        if self.editor._changed:
            self.Title = self.Title[1:]
            self.editor._changed = False
        self.Parent.Raise()


    @Bind(wx.EVT_TOOL,id=ID.SNEW)
    def OnScriptNew(self,e):
        if self.CheckForChanges() == wx.ID_CANCEL:
            return
        self.editor.Clear()
        self._new = True
        self.editor._changed = False

        # Load the default script
        self.scriptpath = '<unknown>'

        self.Title = "untitled - Script Editor"


    @Bind(wx.EVT_TOOL,id=ID.SOPEN)    
    def OnScriptOpen(self,e):
        self._new = False
        if self.CheckForChanges() == wx.ID_CANCEL:
            return
        dDir,dFile = os.path.split(self.scriptpath)
        dlg = wx.FileDialog(
            self, message="Choose a file", defaultDir=dDir,
            defaultFile=dFile, wildcard=self.wildcard, style=wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.scriptpath = dlg.GetPath()
            self.OpenScript(self.scriptpath)
        dlg.Destroy()


    @Bind(wx.EVT_TOOL,id=ID.SSAVE)
    def OnScriptSave(self, e):
        if self._new:
            self.OnScriptSaveAs(e)
            self._new = False
        else:
            self.SaveScript(self.scriptpath, confirm=False)
            self._new = False
        

    @Bind(wx.EVT_TOOL,id=ID.SSAVEAS)
    def OnScriptSaveAs(self, e=None):
        if self._new:
            dDir = wx.GetApp().UserScriptsDir
            dFile = 'untitled.py'
        else:
            dDir,dFile = os.path.split(self.scriptpath)

        dlg = wx.FileDialog(self, message="Save file as ...",
                            defaultDir=dDir, 
                            defaultFile=dFile,
                            wildcard=self.wildcard, style=wx.SAVE)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            self.scriptpath = dlg.GetPath()   
            self.SaveScript(self.scriptpath)
        dlg.Destroy()
        self._new = False
        return  result


    @Bind(wx.EVT_MENU,id=ID.UNDO)
    def OnUndo(self, e):
        self.editor.Undo()


    @Bind(wx.EVT_MENU,id=ID.REDO)
    def OnRedo(self, e):
        self.editor.Redo()

        
    def CheckForChanges(self):
        if (not self._new) and os.path.exists(self.scriptpath):
            filetext = open(self.scriptpath).read()
        else:
            filetext = ""
        if self.editor.GetText() != filetext:
            self.parent.OnStopScript()
            self.SetFocus() # So the user sees where the dialog comes from.
            dlg = wx.MessageDialog(self, 'Save changes to %s?'
                                   % os.path.split(self.scriptpath)[-1],
                                   'Fr0st',wx.YES_NO|wx.CANCEL)
            result = dlg.ShowModal()
            if result == wx.ID_YES:
                if self._new:
                    # Dealing with a file that hasn't been saved.
                    if self.OnScriptSaveAs() == wx.ID_OK:
                        self._new = False
                    else:
                        # HACK: Makes the closing sequence abort. Otherwise the
                        # return value comes from the outer dialog.
                        return wx.ID_CANCEL
                else:
                    self.SaveScript(self.scriptpath, confirm=False)
            elif result == wx.ID_NO:
                # Reset the script to the saved version, so that it looks like
                # the editor was closed.
                self.editor.SetValue(filetext)
            dlg.Destroy()
            return result


    def OpenScript(self, path):
        if os.path.exists(path):
            with open(path) as f:
                self.editor.SetValue(f.read())
        self.SetTitle("%s - Script Editor" % os.path.basename(path))
        self.editor._changed = False
        

    def SaveScript(self, path, confirm=True):
        if not os.access(path, os.W_OK):
            basename = os.path.split(path)[1]
            path = os.path.join(wx.GetApp().UserScriptsDir, basename)

        if os.path.exists(path) and confirm:
            dlg = wx.MessageDialog(self, '%s already exists.\nDo You want to replace it?'
                                   %path,'Fr0st',wx.YES_NO)
            if dlg.ShowModal() == wx.ID_NO: return
            dlg.Destroy()
        try:
            with open(path,"w") as f:
                f.write(self.editor.GetText())
        except Exception:
            wx.MessageDialog(self, "Unable to save file or destination not writable.", 'Fr0st',
                             wx.OK).ShowModal()

        self.SetTitle("%s - Script Editor" % os.path.basename(path))
        self.editor._changed = False


    def make_dialog(self, *a):
        """This method runs from the script thread, so it can't create the
        dialog directly."""
        res = self.OnDialogRequest(*a)
        if isinstance(res, BaseException):
            # If there was an error, propagate it.
            raise res
        return res


    @InMain
    def OnDialogRequest(self, *a):
        """Callback which processes script dialogs in the main threads, then
        arranges for results to be returned."""
        # TODO: instead of isshown, need a method to determine if it's in front
        # of the parent (maybe by checking where the GUI event comes from?)
        if self.IsShown():
            parent = self
        else:
            parent = self.parent
        try:
            name = "%s asks" %os.path.basename(self.scriptpath)
            dlg = DynamicDialog(parent, name, *a)
            res = dlg.ShowModal()
            if res == wx.ID_CANCEL:
                return ThreadInterrupt()
            return [w.GetValue() for w in dlg.widgets]
        except Exception as e:
            return e
            


class MyLog(wx.TextCtrl):
    re_exc = re.compile(r'^.*?(?=  File "<string>")',re.DOTALL)
    re_line = re.compile(r'(Script, line \d*, in .*?)$',re.MULTILINE)
    re_linenum = re.compile(r'Script, line (\d*),')
    _script = None # This is set by the parent


    @BindEvents
    def __init__(self,parent):
        self.parent = parent
        wx.TextCtrl.__init__(self,parent,-1,
                             style = wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL)
        self.SetFont(wx.Font(8, wx.MODERN, wx.NORMAL, wx.NORMAL))
        sys.oldstderr = sys.stderr   # For debugging purposes!
        if "-debug" not in sys.argv:
            # TODO: remove this, it's to supress the editor and get a
            # decent traceback.        
            sys.stdout = self
            sys.stderr = self
            
##        self._suppress = 0
##        self._syntax  = 0


    def write(self, message):
        """Notifies the main thread to print a message."""
        wx.PostEvent(self, ThreadMessageEvent(-1, message))


    @Bind(EVT_THREAD_MESSAGE)
    def OnWrite(self, e):
        self._write(*e.Args)

    def _write(self, message):
        sys.oldstderr.write(message) # For debugging purposes!

        if not message.startswith("Exception"):
            self.AppendText(message)
            return

        # Strip junk from start of exception, and rename 'File "<string>"' to
        # 'Script'
        message = self.re_exc.sub('', message)
        message = message.replace('File "<string>"', 'Script')
        
        # prevent '%' occurring in code from screwing up string formatting
        message = message.replace('%', '%%')
        
        lines = (self._script[int(i)-1].strip()
                 for i in self.re_linenum.findall(message))
        message = self.re_line.sub('\g<1>\n    %s',message) %tuple(lines)
        self.AppendText(message)


    # On windows, wx is threadsafe. This code skips all event processing
    # and sends prints directly to the tc, which is much faster.
    if "win32" in sys.platform:
        write = _write



class CodeEditor(stc.StyledTextCtrl):
    @BindEvents
    def __init__(self, parent, frame):
        stc.StyledTextCtrl.__init__(self, parent, -1)
        self.parent = frame
        self._changed = False
        self.SetUpEditor()


    @Bind(wx.stc.EVT_STC_CHANGE)
    def OnChange(self, e):
        """This method is here to make the editor show if there have been
        changes to the script."""
        if not self._changed:
            self._changed = True
            self.parent.Title = '*' + self.parent.Title
            

    # Some methods to make it compatible with how the wxTextCtrl is used
    def SetValue(self, value):
        if wx.USE_UNICODE:
            value = value.decode('iso8859_1')
        val = self.GetReadOnly()
        self.SetReadOnly(False)
        self.SetText(value)
        self.EmptyUndoBuffer()
        self.SetSavePoint()
        self.SetReadOnly(val)

    def SetEditable(self, val):
        self.SetReadOnly(not val)

    def IsModified(self):
        return self.GetModify()

    def Clear(self):
        self.ClearAll()
        self.EmptyUndoBuffer()

    def SetInsertionPoint(self, pos):
        self.SetCurrentPos(pos)
        self.SetAnchor(pos)

    def ShowPosition(self, pos):
        line = self.LineFromPosition(pos)
        #self.EnsureVisible(line)
        self.GotoLine(line)

    def GetLastPosition(self):
        return self.GetLength()

    def GetPositionFromLine(self, line):
        return self.PositionFromLine(line)

    def GetRange(self, start, end):
        return self.GetTextRange(start, end)

    def GetSelection(self):
        return self.GetAnchor(), self.GetCurrentPos()

    def SetSelection(self, start, end):
        self.SetSelectionStart(start)
        self.SetSelectionEnd(end)

    def SelectLine(self, line):
        start = self.PositionFromLine(line)
        end = self.GetLineEndPosition(line)
        self.SetSelection(start, end)
        
    def SetUpEditor(self):
        """
        This method carries out the work of setting up the demo editor.            
        It's seperate so as not to clutter up the init code.
        """
        import keyword
        
        self.SetLexer(stc.STC_LEX_PYTHON)
        self.SetKeyWords(0, " ".join(keyword.kwlist))

        # Enable folding
##        self.SetProperty("fold", "1" ) 

        # Highlight tab/space mixing (shouldn't be any)
        self.SetProperty("tab.timmy.whinge.level", "1")

        # Set left and right margins
        self.SetMargins(2,2)

        # Set up the numbers in the margin for margin #1
        self.SetMarginType(1, wx.stc.STC_MARGIN_NUMBER)
        # Reasonable value for, say, 4-5 digits using a mono font (40 pix)
        self.SetMarginWidth(1, 40)

        # Indentation and tab stuff
        self.SetIndent(4)               # Proscribed indent size for wx
        self.SetIndentationGuides(True) # Show indent guides
        self.SetBackSpaceUnIndents(True)# Backspace unindents rather than delete 1 space
        self.SetTabIndents(True)        # Tab key indents
        self.SetTabWidth(4)             # Proscribed tab size for wx
        self.SetUseTabs(False)          # Use spaces rather than tabs, or
                                        # TabTimmy will complain!    
        # White space
        self.SetViewWhiteSpace(False)   # Don't view white space

        # EOL: Since we are loading/saving ourselves, and the
        # strings will always have \n's in them, set the STC to
        # edit them that way.            
        self.SetEOLMode(wx.stc.STC_EOL_LF)
        self.SetViewEOL(False)
        
        # No right-edge mode indicator
        self.SetEdgeMode(stc.STC_EDGE_NONE)

        # Setup a margin to hold fold markers
        self.SetMarginType(2, stc.STC_MARGIN_SYMBOL)
        self.SetMarginMask(2, stc.STC_MASK_FOLDERS)
        self.SetMarginSensitive(2, True)
        self.SetMarginWidth(2, 12)

        # and now set up the fold markers
        self.MarkerDefine(stc.STC_MARKNUM_FOLDEREND,     stc.STC_MARK_BOXPLUSCONNECTED,  "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDEROPENMID, stc.STC_MARK_BOXMINUSCONNECTED, "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDERMIDTAIL, stc.STC_MARK_TCORNER,  "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDERTAIL,    stc.STC_MARK_LCORNER,  "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDERSUB,     stc.STC_MARK_VLINE,    "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDER,        stc.STC_MARK_BOXPLUS,  "white", "black")
        self.MarkerDefine(stc.STC_MARKNUM_FOLDEROPEN,    stc.STC_MARK_BOXMINUS, "white", "black")

        # Global default style
        if wx.Platform == '__WXMSW__':
            self.StyleSetSpec(stc.STC_STYLE_DEFAULT, 
                              'fore:#000000,back:#FFFFFF,face:Courier New')
        elif wx.Platform == '__WXMAC__':
            # TODO: if this looks fine on Linux too, remove the Mac-specific case 
            # and use this whenever OS != MSW.
            self.StyleSetSpec(stc.STC_STYLE_DEFAULT, 
                              'fore:#000000,back:#FFFFFF,face:Monaco')
        else:
            defsize = wx.SystemSettings.GetFont(wx.SYS_ANSI_FIXED_FONT).GetPointSize()
            self.StyleSetSpec(stc.STC_STYLE_DEFAULT, 
                              'fore:#000000,back:#FFFFFF,face:Courier,size:%d'%defsize)

        # Clear styles and revert to default.
        self.StyleClearAll()

        # Following style specs only indicate differences from default.
        # The rest remains unchanged.

        # Line numbers in margin
        self.StyleSetSpec(wx.stc.STC_STYLE_LINENUMBER,'fore:#000000,back:#99A9C2')    
        # Highlighted brace
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACELIGHT,'fore:#00009D,back:#FFFF00')
        # Unmatched brace
        self.StyleSetSpec(wx.stc.STC_STYLE_BRACEBAD,'fore:#00009D,back:#FF0000')
        # Indentation guide
        self.StyleSetSpec(wx.stc.STC_STYLE_INDENTGUIDE, "fore:#CDCDCD")

        # Python styles
        self.StyleSetSpec(wx.stc.STC_P_DEFAULT, 'fore:#000000')
        # Comments
        self.StyleSetSpec(wx.stc.STC_P_COMMENTLINE,  'fore:#008000,back:#F0FFF0')
        self.StyleSetSpec(wx.stc.STC_P_COMMENTBLOCK, 'fore:#008000,back:#F0FFF0')
        # Numbers
        self.StyleSetSpec(wx.stc.STC_P_NUMBER, 'fore:#008080')
        # Strings and characters
        self.StyleSetSpec(wx.stc.STC_P_STRING, 'fore:#800080')
        self.StyleSetSpec(wx.stc.STC_P_CHARACTER, 'fore:#800080')
        # Keywords
        self.StyleSetSpec(wx.stc.STC_P_WORD, 'fore:#000080,bold')
        # Triple quotes
        self.StyleSetSpec(wx.stc.STC_P_TRIPLE, 'fore:#800080,back:#FFFFEA')
        self.StyleSetSpec(wx.stc.STC_P_TRIPLEDOUBLE, 'fore:#800080,back:#FFFFEA')
        # Class names
        self.StyleSetSpec(wx.stc.STC_P_CLASSNAME, 'fore:#0000FF,bold')
        # Function names
        self.StyleSetSpec(wx.stc.STC_P_DEFNAME, 'fore:#008080,bold')
        # Operators
        self.StyleSetSpec(wx.stc.STC_P_OPERATOR, 'fore:#800000,bold')
        # Identifiers. I leave this as not bold because everything seems
        # to be an identifier if it doesn't match the above criterae
        self.StyleSetSpec(wx.stc.STC_P_IDENTIFIER, 'fore:#000000')

        # Caret color
        self.SetCaretForeground("BLUE")
        # Selection background
        self.SetSelBackground(1, '#66CCFF')

        self.SetSelBackground(True, wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHT))
        self.SetSelForeground(True, wx.SystemSettings_GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT))

    def RegisterModifiedEvent(self, eventHandler):
        self.Bind(wx.stc.EVT_STC_CHANGE, eventHandler)

