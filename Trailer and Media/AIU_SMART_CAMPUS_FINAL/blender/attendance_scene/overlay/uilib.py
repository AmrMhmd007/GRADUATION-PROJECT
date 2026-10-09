import cairo, math
W,H=1920,1080
NAVY=(0.027,0.047,0.094); WHITE=(0.93,0.95,0.98); BLUE=(0.47,0.63,0.88); GREY=(0.59,0.63,0.71); GREEN=(0.18,0.78,0.45); AMBER=(1.0,0.66,0.15); RED=(0.9,0.3,0.3); INK=(0.10,0.12,0.30)
FONT='Carlito'
def ease(x): x=max(0.,min(1.,x)); return x*x*(3-2*x)
def rr(c,x,y,w,h,r):
    c.new_sub_path(); c.arc(x+w-r,y+r,r,-math.pi/2,0); c.arc(x+w-r,y+h-r,r,0,math.pi/2); c.arc(x+r,y+h-r,r,math.pi/2,math.pi); c.arc(x+r,y+r,r,math.pi,1.5*math.pi); c.close_path()
def tw(c,s,size,bold,sp):
    c.select_font_face(FONT,cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL); c.set_font_size(size)
    return sum(c.text_extents(ch).x_advance+sp for ch in s)-sp
def text(c,s,x,y,size,col,a=1.,bold=False,sp=0.,anchor='l'):
    w=tw(c,s,size,bold,sp); x0=x-w/2 if anchor=='c' else (x-w if anchor=='r' else x)
    c.set_source_rgba(*col,a)
    for ch in s: c.move_to(x0,y); c.show_text(ch); x0+=c.text_extents(ch).x_advance+sp
    return w
def pill(c,x,y,s,size,col,a=1.,fill=True,bold=True,sp=1.6,padx=14,h=None,anchor='l'):
    w=tw(c,s,size,bold,sp)+2*padx; h=h or size+14
    if anchor=='c': x-=w/2
    rr(c,x,y,w,h,h/2)
    if fill: c.set_source_rgba(*col,0.18*a); c.fill_preserve()
    c.set_source_rgba(*col,a); c.set_line_width(1.6); c.stroke()
    text(c,s,x+padx,y+h/2+size*0.34,size,col,a,bold,sp); return w
def chapter(c,ch,sub,a):
    c.set_source_rgba(*BLUE,a); c.rectangle(96,64,4,48); c.fill()
    text(c,ch,120,94,30,WHITE,0.92*a,True,4); text(c,sub,120,124,18,GREY,0.92*a,False,3)
def chip(c,s,a,x=90,y=960):
    w=tw(c,s,19,False,2)+44; rr(c,x,y,w,46,8); c.set_source_rgba(*NAVY,0.67*a); c.fill(); text(c,s,x+22,y+31,19,(0.92,0.93,0.96),0.9*a,False,2)
