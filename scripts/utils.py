"""
This file contains several utility functions that can be imported
from other scripts, through the standard python import mechanism.
"""



def equalize_flame_attributes(flame1,flame2):
    """Make two flames have the same number of xforms and the same
    attributes, so they can be interpolated easier."""
    diff = len(flame1.xform) - len(flame2.xform)
    if diff < 0:
        for i in range(-diff):
            flame1.add_xform()
            flame1.xform[-1].symmetry = 1
    elif diff > 0:
        for i in range(diff):
            flame2.add_xform()
            flame2.xform[-1].symmetry = 1

    if flame1.final or flame2.final:
        flame1.create_final()
        flame2.create_final()


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
               