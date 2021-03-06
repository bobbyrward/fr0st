from runscript import *

"""
Interpolation options:
  keys      - list of frames to interpolate in order
  n         - distance between keyframes
  settings  - interpolation settings (see bottom of script)
"""
def interpolation(keys, n=50, **kwargs):
    last = 0
    cache = []

    #Set defaults
    loop      = kwargs.get('loop',True)
    loops     = kwargs.get('loops',True)

    tmp = []
    if loop:
        for i in xrange(len(keys)-1):
            k1 = Flame(string=keys[i].to_string())
            k2 = Flame(string=keys[i+1].to_string())
            equalize_flame_attributes(k1, k2)
            if loops: tmp.append(k1)
            tmp.append(k1)
            if i==len(keys)-2:tmp.append(k2)
        tmp.append(Flame(string=keys[-1].to_string()))
    else:
        for i in xrange(len(keys)):
            k1 = Flame(string=keys[i-1].to_string())
            k2 = Flame(string=keys[i].to_string())
            equalize_flame_attributes(k1, k2)
            if loops: tmp.append(k2)
            tmp.append(k2)
    keys = tmp

    nk = len(keys)
    if loop: nf = nk * n
    else:    nf = (nk-1) * n
            
    while last < nf:
        if len(cache) < last + 1:
            cache.append(get_flame(keys, n, last, **kwargs))
            if last%10<>9: print '.',
            if last%10==9: print str(last+1) + '/' + str(nf)
            if last==nf-1: print "Calculations complete"
        yield cache[last]
        last += 1
        if last >= nf:
            last = 0
#---end

def get_flame(keys, n, i, **kwargs):
    #Make new, empty flame
    flame = Flame()
    flame.name = kwargs.get('flamename') + str(kwargs.get('offset')+i)
    rotate = kwargs.get('rotate')
    pivot = kwargs.get('pivot')

    #Flame attrs
    interp_attrs = ['scale', 'rotate', 'brightness', 'gamma']
    for name, test in keys[0].iter_attributes():
        cps = []
        
        if name in interp_attrs:
            for k in keys:
                tmp = getattr(k,name)
                if type(tmp) == list: cps.append(tuple(tmp))
                else:                 cps.append(tmp)
            val = interp(cps, n, i, **kwargs)
            if type(val)==tuple: setattr(flame, name, list(val))
            else:                setattr(flame, name, val)
        else:
            pass
    #end flame attrs
    
    maxi = 0
    for k in keys:
        if len(k.xform)>maxi: maxi=len(k.xform)
    
    #Xform attrs
    for x in xrange(maxi):
        #Add xform
        flame.add_xform()
        
        #coef interp
        cpsx = []
        cpsy = []
        cpso = []
        attrset = []
        for k in keys:
            if len(k.xform)<x+1:
                cpsx.append((1,0))
                cpsy.append((0,1))
                cpso.append((0,0))
            else:
                a,d,b,e,c,f = k.xform[x].coefs
                cpsx.append((a,d))
                cpsy.append((b,e))
                cpso.append((c,f))
                attrset += set(attrset).union(k.xform[x].attributes)
        vx = interp(cpsx, n, i, **kwargs)
        vy = interp(cpsy, n, i, **kwargs)
        vo = interp(cpso, n, i, **kwargs)
        flame.xform[x].coefs = tuple(vx + vy + vo)
        if rotate['count']<>0:
            spin = drange(0,rotate['count']*360,n,i%n,**rotate)
            flame.xform[x].rotate(spin)
        if pivot['count']<>0:
            spin = drange(0,pivot['count']*360,n,i%n,**pivot)
            flame.xform[x].orbit(spin)
        
        #attribute intep
        for name in attrset:
            cps = []
            for k in keys:
                if len(k.xform)>x and hasattr(k.xform[x], name):
                    cps.append(getattr(k.xform[x], name))
                else:
                    cps.append(0)
            val = interp(cps, n, i, **kwargs)
            if name=='weight': val = clip(val, 0, 100)
            setattr(flame.xform[x], name, val)
    #end xforms
    
    #gradient
    for c, cps in enumerate(zip(*(key.gradient for key in keys))):
        val = interp(cps, n, i, **kwargs)
        flame.gradient[c] = val
    return flame
#end get_flame
#end interpolation

"""
Erik's secret sauce added for better flava
"""
def get_pad(xform, target):
    HOLES = ['spherical', 'ngon', 'julian', 'juliascope', 'polar', 'wedge_sph', 'wedge_julia']
    
    target.add_xform()
    target.xform[-1] = copy.deepcopy(xform)
    t = target.xform[-1]
    t.coefs = [0.0,1.0,1.0,0.0,0.0,0.0]
    if len(set(t).intersection(HOLES)) > 0:
        #negative ident
        t.coefs = [-1.0,0.0,0.0,-1.0,0.0,0.0]
        t.linear = -1.0
    if 'rectangles' in t.attributes:
        t.rectangles = 1.0
        t.rectangles_x = 0.0
        t.rectangles_y = 0.0
    if 'rings2' in t.attributes:
        t.rings2 = 1.0
        t.rings2_val = 0.0
    if 'fan2' in t.attributes:
        t.fan2 = 1.0
        t.fan2_x = 0.0
        t.fan2_y = 0.0
    if 'blob' in t.attributes:
        t.blob = 1.0
        t.blob_low = 1.0
        t.blob_high = 1.0
        t.blob_waves = 1.0
    if 'perspective' in t.attributes:
        t.perspective = 1.0
        t.perspective_angle = 0.0
    if 'curl' in t.attributes:
        t.curl = 1.0
        t.curl_c1 = 0.0
        t.curl_c2 = 0.0
    if 'super_shape' in t.attributes:
        t.super_shape = 1.0
        t.super_shape_n1 = 2.0
        t.super_shape_n2 = 2.0
        t.super_shape_n3 = 2.0
        t.super_shape_rnd = 0.0
        t.super_shape_holes = 0.0
    if 'fan' in t.attributes:
        t.fan = 1.0
    if 'rings' in t.attributes:
        t.rings = 1.0
    t.weight = 0
#-----------------------------------------------------------------------------

def equalize_flame_attributes(flame1,flame2):
    """Make two flames have the same number of xforms and the same
    attributes. Also moves the final xform (if any) to flame.xform"""
    diff = len(flame1.xform) - len(flame2.xform)
    if diff < 0:
        for i in range(-diff):
#            get_pad(flame2.xform[diff+i], flame1)
            flame1.add_xform()
            flame1.xform[-1].symmetry = 1
    elif diff > 0:
        for i in range(diff):
#            get_pad(flame1.xform[diff+i], flame2)
            flame2.add_xform()
            flame2.xform[-1].symmetry = 1
    if flame1.final or flame2.final:
#        flame1.create_final()
#        flame2.create_final()
        for flame in flame1,flame2:
            flame.create_final()
            flame.xform.append(flame.final)
            flame.final = None
        
    # Size can be interpolated correctly, but it's pointless to
    # produce frames that can't be turned into an animation.
    flame1.size = flame2.size     

    for name in set(flame1.attributes).union(flame2.attributes):
        if not hasattr(flame2,name):
            val = getattr(flame1,name)
            _type = type(val)
            if _type is list or _type is tuple:
                setattr(flame2,name,[0 for i in val])
            elif _type is float:
                setattr(flame2,name,0.0)
            elif _type is str:
                delattr(flame1,name)
            else:
                raise TypeError, "flame.%s can't be %s" %(name,_type)
            
        elif not hasattr(flame1,name):
            val = getattr(flame2,name)
            _type = type(val)
            if _type is list or _type is tuple:
                setattr(flame1,[0 for i in val])
            elif _type is float:
                setattr(flame1,name,0.0)
            elif _type is str:
                delattr(flame2,name)
            else:
                raise TypeError, "flame.%s can't be %s" %(name,_type)


#------------------------------------------------
if __name__ == '__main__':
    #load flames
    f1 = Flame(file='samples.flame',name='linear')
    f2 = Flame(file='samples.flame',name='julia')
    f3 = Flame(file='samples.flame',name='heart')
    f4 = Flame(file='test_interpolation.flame',name='A')
    f5 = Flame(file='test_interpolation.flame',name='B')
    
    settings = {'flamename':'frame'             #base name for frames
               ,'offset':   0                   #offset for frame index value
               ,'curve':    'lin'               #lin, par, npar, cos, sinh, tanh
               ,'a':        1                   #curve parameter (slope)
               ,'t':        0.5                 #spline tension (0.5 = catmull-rom)
               ,'smooth':   True                #use smoothing
               ,'loop':     False                #loop animation
               ,'loops':    True                #loop keyframes between interpolations
               ,'p_space':  'polar'             #coordinate interpolation space: rect, polar
               ,'c_space':  'hls'               #color interpolation space: rgb, hls
               ,'rotate':   {'count':   1       #number of rotations (- for counter-clockwise)
                            ,'curve':   'lin'   #rotation curve
                            ,'a':       1}      #rotation curve param
               ,'pivot':    {'count':   1       #number of pivots (- for counter-clockwise)
                            ,'curve':   'lin'   #pivot curve
                            ,'a':       1}      #pivot curve param
               }

    #interpolation options - check top of file.
    i = interpolation([f2,f3,f4], **settings)
    buff = i.next()   #buffer to take advantage of threading
    while True:
#        SetActiveFlame(buff)
#        preview()
        buff = i.next()
