import wx

from  wx.lib.filebrowsebutton import FileBrowseButton

class DynamicDialog(wx.Dialog):
    """A dialog class used for interactive script input."""
    def __init__(self, parent, title, intro, *args):
        wx.Dialog.__init__(self, parent)
        self.Title = title
        szrgs = 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5
        fgs = wx.FlexGridSizer(99, 2, 1, 1)

        self.widgets = []
        for i in args:
            text, widget = self.AddWidget(*i)
            fgs.Add(text, *szrgs)
            fgs.Add(widget, 0, wx.ALIGN_LEFT, 5)
            self.widgets.append(widget)

        ok = wx.Button(self, wx.ID_OK)
        cancel = wx.Button(self, wx.ID_CANCEL)
        ok.SetDefault()
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddButton(ok)
        btnsizer.AddButton(cancel)
        btnsizer.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add((0,10))
        sizer.Add(wx.StaticText(self, -1, intro), *szrgs)
        sizer.Add((0,10))
        sizer.Add(fgs)
        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER)

        self.SetMinSize((250,1))
        self.SetSizer(sizer)
        sizer.Fit(self)


    def AddWidget(self, name, ty, default=None):
        if ty == bool:
            widget = wx.CheckBox(self, -1)
            if default:
                widget.SetValue(True)
        elif ty == file:
            widget = FileBrowseButton(self, -1, labelText='',
                                      initialValue=default or "")
            widget.SetMinSize((300, widget.GetSize()[1]))
        elif type(ty) in (list, tuple):
            widget = ValidChoice(self, choices=ty)
        else:
            widget = ValidTextCtrl(self, ty, default)
        return wx.StaticText(self, -1, name), widget      



class ValidTextCtrl(wx.TextCtrl):
    def __init__(self, parent, type_, default):
        wx.TextCtrl.__init__(self, parent, -1)
        self.type = type_
        if default is not None:
            self.AppendText(str(default))
        self.default = default
        self.SetMinSize((200 if type_ is str else 100, 27))

        
    def GetValue(self):
        try:
            return self.type(wx.TextCtrl.GetValue(self))
        except:
            return self.default


class ValidChoice(wx.Choice):
    def __init__(self, parent, choices):
        self.choices = choices
        self.index = 0
        wx.Choice.__init__(self, parent, -1, choices=map(str, choices))
        self.Bind(wx.EVT_CHOICE, self.OnChoice)

    def GetValue(self):
        return self.choices[self.index]

    def OnChoice(self, e):
        self.index = e.GetInt()
        
