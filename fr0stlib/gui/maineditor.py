import wx, itertools
import copy

from fr0stlib.decorators import *
from fr0stlib.gui.canvas import XformCanvas
from fr0stlib.gui.utils import LoadIcon, MultiSliderMixin, Box, NumberTextCtrl,\
                          SizePanel
from fr0stlib.gui.config import config
from fr0stlib.gui.constants import ID
from fr0stlib.pyflam3 import flam3_colorhist, Genome
from ctypes import c_double

class MainNotebook(wx.Notebook):

    def __init__(self, parent):
        self.parent = parent
        # 390 is just the right width for the gradient to be entirely visible.
        # 573 seems to be the right height for all sliders to be visible.
        wx.Notebook.__init__(self, parent, -1, size=(390,573), style=
                             wx.BK_DEFAULT
                             )

        self.transform = TransformPanel(self)
        self.canvas = self.transform.canvas
        self.AddPage(self.transform, "Transform Editor")

        self.grad = GradientPanel(self)
        self.AddPage(self.grad, "Gradient Editor")

        self.adjust = AdjustPanel(self)
        self.AddPage(self.adjust, "Adjust")


    def UpdateView(self, rezoom=False):
        for i in self.grad, self.adjust:
            i.UpdateView()
        self.canvas.ShowFlame(rezoom=rezoom)
        self.transform.toolbar.ToggleTool(ID.EditPostXform,
                                          config['Edit-Post-Xform'])



class TransformPanel(wx.Panel):

    @BindEvents
    def __init__(self, parent):
        self.parent = parent.parent
        wx.Panel.__init__(self,parent,-1)
        self.toolbar = self.AddToolbar()
        self.canvas = XformCanvas(self)

        szr = wx.BoxSizer(wx.VERTICAL)
        szr.Add(self.toolbar, 0, wx.EXPAND)
        szr.Add(self.canvas, 1, wx.EXPAND)

        self.SetSizer(szr)
        self.Layout()


    def AddToolbar(self):
        self.tool_ids = {}

        self.toolbar = wx.ToolBar(self, -1, style=wx.TB_HORIZONTAL|wx.TB_FLAT)

        def add_tool(name, toggle=False):
            name_nodash = name.replace("-","")
            id = getattr(ID, name_nodash)
            self.tool_ids[id] = name_nodash
            
            self.toolbar.AddSimpleTool(id, LoadIcon('toolbar', name),
                                       name_nodash, isToggle=toggle)
            if toggle:
                self.toolbar.ToggleTool(id, config[name])
                self.MakeConfigFunc(name)

        add_tool('Clear-Flame')
        add_tool('Add-Xform')
        add_tool('Add-Final-Xform')
        add_tool('Duplicate-Xform')
        add_tool('Delete-Xform')
        add_tool('Zoom-To-Fit')

        add_tool('World-Pivot', True)
        add_tool('Lock-Axes', True)
        add_tool('Variation-Preview', True)
        add_tool('Edit-Post-Xform', True)            

        self.toolbar.Realize()

        return self.toolbar


    def MakeConfigFunc(self, i):
        def onbtn():
            config[i] = not config[i]
            # HACK: This is a setflame so the post xform flag updates correctly
            self.parent.SetFlame(self.parent.flame, rezoom=False)
        setattr(self, "Func%s" %i.replace("-",""), onbtn)


    @Bind(wx.EVT_TOOL)
    def OnButton(self, e):
        getattr(self, "Func%s" % self.tool_ids[e.GetId()])()

    def modifyxform(f):
        """This decorator wraps away common code in the button functions."""
        def inner(self):
            # TODO: does this pass post-xforms correctly?
            f(self, self.parent.ActiveXform)
            self.parent.TreePanel.TempSave()
        return inner

    @modifyxform
    def FuncClearFlame(self, xform):
        self.parent.flame.clear()
        self.parent.ActiveXform = self.parent.flame.add_xform()

    @modifyxform
    def FuncAddXform(self, xform):
        self.parent.ActiveXform = self.parent.flame.add_xform()

    @modifyxform
    def FuncAddFinalXform(self, xform):
        # add_final already checks if a final xform exists.
        self.parent.ActiveXform = self.parent.flame.add_final()

    @modifyxform
    def FuncDuplicateXform(self, xform):
        self.parent.ActiveXform = xform.copy()

    @modifyxform
    def FuncDeleteXform(self, xform):
        lst = xform._parent.xform
        if not xform.isfinal() and len(lst) == 1:
            return #  Can't delete last remaining xform.
        index = xform.index or 0 # None is turned to 0 
        xform.delete()
        self.parent.ActiveXform = lst[min(index, len(lst) - 1)]

    def FuncZoomToFit(self):
        self.canvas.ZoomToFit()
        


class GradientPanel(wx.Panel):
    _new = None
    _changed = False
    _startval = None
    _flame = None # Only used to check identity

    @BindEvents
    def __init__(self,parent):
        wx.Panel.__init__(self,parent,-1)
        self.parent = parent.parent

        # Double buffering is needed to prevent flickering.
        self.SetDoubleBuffered(True)

        self.config = config["Gradient-Settings"]
        self.dict = {}

        choicelist = (('rotate', (-128, 128)),
                      ('hue',(-180,180)),
                      ('saturation', (-100,100)),
                      ('brightness', (-100,100)))
        self.choices = dict(choicelist)
        self.choice = 'rotate'
        self.func = lambda x: getattr(self.parent.flame.gradient,
                                      self.choice)(x)

        #Gradient image
        self.image = Gradient(self)
        #Controls - choice for method and slider
        self.Selector = wx.Choice(self, -1, choices=[i[0] for i in choicelist])
        self.Selector.SetSelection(0)
        self.Selector.Bind(wx.EVT_CHOICE, self.OnChoice)

        self.slider = wx.Slider(self, -1, 0, -180, 180,
                                style=wx.SL_HORIZONTAL
                                |wx.SL_LABELS)
        self.slider.Bind(wx.EVT_SLIDER, self.OnSlider)
        self.slider.Bind(wx.EVT_LEFT_DOWN, self.OnSliderDown)
        self.slider.Bind(wx.EVT_LEFT_UP, self.OnSliderUp)

        opts = self.MakeTCs("hue", "saturation", "value", "nodes",
                            low=0, high=1, callback=self.OptCallback)
        for i in self.dict["nodes"]:
            i.MakeIntOnly()
            i.SetAllowedRange(1,256)
        # Set Defaults for tcs.
        for k, tcs in self.dict.iteritems():
            [tc.SetFloat(i) for tc,i in zip(tcs, self.config[k])]

        opts = Box(self, "Gradient Generation", opts)

        rdm = wx.Button(self, -1, "Randomize")
        rdm.Bind(wx.EVT_BUTTON, self.OnRandomize)
        inv = wx.Button(self, -1, "Invert")
        inv.Bind(wx.EVT_BUTTON, self.OnInvert)
        rev = wx.Button(self, -1, "Reverse")
        rev.Bind(wx.EVT_BUTTON, self.OnReverse)
        btnszr = wx.BoxSizer(wx.VERTICAL)
        btnszr.AddMany((rdm, inv, rev))

        szr2 = wx.BoxSizer(wx.HORIZONTAL)
        szr2.AddMany((opts, (btnszr, 0 ,wx.ALIGN_RIGHT)))

        sizer1 = wx.BoxSizer(wx.VERTICAL)
        sizer1.Add(self.image,0, wx.EXPAND)
        sizer1.Add(self.Selector,0)
        sizer1.Add(self.slider,0,wx.EXPAND)
        sizer1.Add(szr2, 0, wx.EXPAND)

        self.SetSizer(sizer1)
        self.Layout()


    def MakeTCs(self, *a, **k):
        fgs = wx.FlexGridSizer(99, 3, 1, 1)
        fgs.Add((0,0))
        fgs.AddMany((wx.StaticText(self, -1, i), 0, wx.ALIGN_CENTER)
                    for i in ("Min", "Max"))
        for i in a:
            tcs = tuple(NumberTextCtrl(self, **k) for i in range(2))
            self.dict[i] = tcs
            fgs.Add(wx.StaticText(self, -1, i.replace("_", " ").title()),
                    0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
            fgs.AddMany((tc, 0, wx.ALIGN_LEFT, 5) for tc in tcs)
        return fgs


    def UpdateView(self):
        self.image.Update()
        if self.parent.flame != self._flame:
            # Hack: only change the slider when the flame object id changes.
            self.ResetSlider()
            self._flame = self.parent.flame


    def OptCallback(self, tc, tempsave=None):
        for k,v in self.dict.iteritems():
            self.config[k] = tuple(i.GetFloat() for i in v)


    def OnRandomize(self, e):
        self.parent.flame.gradient.random(**self.config)
        self.parent.TreePanel.TempSave()


    def OnInvert(self, e):
        self.parent.flame.gradient.invert()
        self.parent.TreePanel.TempSave()


    def OnReverse(self, e):
        self.parent.flame.gradient.reverse()
        self.parent.TreePanel.TempSave()


    @Bind(wx.EVT_IDLE)
    def OnIdle(self, e):
        if self._new is not None:

            self.parent.flame.gradient = copy.deepcopy(self._grad_copy)

            self.func(self._new)
            self._new = None
            self._changed = True

            self.image.Update()
            self.parent.image.RenderPreview()

            # HACK: Updating the color tab without calling SetFlame.
            self.parent.XformTabs.Color.UpdateView()


    def OnChoice(self, e):
        self.choice = e.GetString()
        self.ResetSlider()


    def ResetSlider(self):
        self.slider.SetValue(0)
        self.slider.SetRange(*self.choices[self.choice])


    def OnSliderDown(self, e):
        self._grad_copy = copy.deepcopy(self.parent.flame.gradient)
        self._startval = self.slider.GetValue()
        e.Skip()


    def OnSliderUp(self, e):
        if self._changed:
            self.parent.TreePanel.TempSave()
            self._changed = False
        self._startval = None
        e.Skip()


    def OnSlider(self, e):
        if self._startval is not None:
            self._new = e.GetInt() - self._startval



class Gradient(wx.Panel):
    formatstr = "%c" * 256 * 3

    @BindEvents
    def __init__(self,parent):
        self.parent = parent.parent
        wx.Panel.__init__(self, parent, -1)
        self.bmp = wx.EmptyBitmap(1,1,32)
        self.SetMinSize((390,95))
        self._startpos = None

    def Update(self, flame=None):
        flame = flame or self.parent.flame

        img = wx.ImageFromBuffer(256, 1, buffer(flame.gradient.data))
        img.Rescale(384, 50)
        self.bmp = wx.BitmapFromImage(img)

        self.Refresh()

        
    def DrawHistogram(self, dc=None):
        """ Create and draw the color histogram."""
        dc = dc or wx.ClientDC(self)
        genome = Genome.from_string(self.parent.flame.to_string(True))[0]
        array = (c_double *256)()
        flam3_colorhist(genome, 1, array)
        dc.DrawLines([(i*1.5, 30-j*500) for i,j in enumerate(array)], 2, 2)


    @Bind(wx.EVT_PAINT)
    def OnPaint(self, evt):
        dc = wx.PaintDC(self)
        dc.DrawBitmap(self.bmp, 2, 37, True)
        if hasattr(self.parent, '_namespace'):
            self.DrawHistogram(dc)




    @Bind(wx.EVT_MOUSE_CAPTURE_LOST)
    def OnLostMouseCapture(self, e):
        self._startpos = None

    @Bind(wx.EVT_LEFT_DOWN)
    def OnLeftDown(self, e):
        self.CaptureMouse()
        self._startpos = e.GetPosition()
        parent = self.GetParent()
        self._oldchoice = parent.choice
        parent.choice = 'rotate'
        parent.OnSliderDown(e)


    @Bind(wx.EVT_LEFT_UP)
    def OnLeftUp(self, e):
        if self._startpos is None:
            return
        self.ReleaseMouse()
        self._startpos = None
        parent = self.GetParent()
        parent.choice = self._oldchoice
        # HACK: Need to keep the slider value intact. In the parent's code,
        # this is handled by e.Skip(), which passes the event on to
        # the slider handler. This hack simulates that behaviour.
        val = parent.slider.GetValue()
        parent.OnSliderUp(e)
        parent.slider.SetValue(val)


    @Bind(wx.EVT_MOTION)
    def OnMove(self, e):
        if self._startpos is not None:
            offset = int((e.GetPosition()[0] - self._startpos[0])/1.5)
            self.GetParent()._new = offset


    @Bind(wx.EVT_LEFT_DCLICK)
    def OnDoubleClick(self, e):
        self.Parent.OnRandomize(None)



class AdjustPanel(MultiSliderMixin, wx.Panel):

    @BindEvents
    def __init__(self, parent):
        self.parent = parent.parent
        super(AdjustPanel, self).__init__(parent, -1)

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizepanel = SizePanel(self, self.__size_callback)
        sizer.Add(self.sizepanel)
        sizer.Add(Box(self, "Camera Settings",
                      *((self.MakeSlider(*i),0, wx.EXPAND) for i in
                      (("scale", 25, 1, 100, False),
                       ("x_offset", 0, -5, 5, False),
                       ("y_offset", 0, -5, 5, False),
                       ("rotate", 0, -360, 360, True)))), 0, wx.EXPAND)
        sizer.Add(Box(self, "Other Settings",
                      *((self.MakeSlider(*i),0, wx.EXPAND) for i in
                      (("gamma",4,1,10,False),
                       ("brightness",4,0,100,False),
                       ("gamma_threshold",0.01, 0, 1,False),
                       ("highlight_power", -1, -1, 5, False)))), 0, wx.EXPAND)
        self.sliders["gamma_threshold"][1].SetAllowedRange(0, None)
        self.SetSizer(sizer)


    def __size_callback(self):
        self.UpdateFlame()
        self.parent.TreePanel.TempSave()


    def UpdateView(self):
        flame = self.parent.flame
        for name in self.sliders:
            self.UpdateSlider(name, getattr(flame, name))
        self.sizepanel.UpdateSize(flame.size)


    def UpdateFlame(self):
        flame = self.parent.flame
        for name, val in self.IterSliders():
            setattr(flame, name, val)
        flame.size = self.sizepanel.GetInts()
        self.UpdateView()
        self.parent.image.RenderPreview()


