from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin
import math

W, H = 1080, 1350
OUT = Path("output/carousel/once-for-all")
OUT.mkdir(parents=True, exist_ok=True)

BG = "#F5F1E8"
INK = "#121212"
MUTED = "#756F65"
BLUE = "#246BFD"
ORANGE = "#FF5A36"
LIME = "#CBEF43"
WHITE = "#FFFFFF"
GRID = "#D7D1C5"

SANS = "/System/Library/Fonts/HelveticaNeue.ttc"
MONO = "/System/Library/Fonts/SFNSMono.ttf"

def font(size, bold=False, mono=False):
    path = MONO if mono else SANS
    return ImageFont.truetype(path, size=size, index=1 if bold and not mono else 0)

def canvas():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)

def text(draw, xy, s, size, fill=INK, bold=False, mono=False, anchor=None, spacing=8, align="left"):
    draw.multiline_text(xy, s, font=font(size, bold, mono), fill=fill, anchor=anchor,
                        spacing=spacing, align=align)

def pill(draw, box, label, fill=INK, fg=BG, size=24):
    draw.rounded_rectangle(box, radius=(box[3]-box[1])//2, fill=fill)
    text(draw, ((box[0]+box[2])//2, (box[1]+box[3])//2), label, size, fg, True,
         anchor="mm")

def header(draw, n, kicker):
    text(draw, (72, 54), f"0{n} / 08", 22, MUTED, True, mono=True)
    text(draw, (1008, 54), kicker.upper(), 22, MUTED, True, mono=True, anchor="ra")
    draw.line((72, 92, 1008, 92), fill=GRID, width=2)

def footer(draw, hint="SWIPE →"):
    text(draw, (72, 1295), "ONCE-FOR-ALL · ICLR 2020", 18, MUTED, True, mono=True)
    text(draw, (1008, 1295), hint, 18, INK, True, mono=True, anchor="ra")

def title(draw, s, y=145, size=72, color=INK):
    text(draw, (72, y), s, size, color, True, spacing=0)

def network(draw, cx, cy, scale=1.0, color=INK, active=None):
    cols = [3, 5, 4, 2]
    xs = [cx + int((i-1.5)*150*scale) for i in range(4)]
    nodes = []
    for i, count in enumerate(cols):
        ys = [cy + int((j-(count-1)/2)*82*scale) for j in range(count)]
        nodes.append([(xs[i], y) for y in ys])
    for i in range(3):
        for a in nodes[i]:
            for b in nodes[i+1]:
                draw.line((*a, *b), fill=color, width=max(1, int(2*scale)))
    for i, col in enumerate(nodes):
        for j, (x,y) in enumerate(col):
            fill = ORANGE if active and (i,j) in active else BG
            draw.ellipse((x-10*scale,y-10*scale,x+10*scale,y+10*scale), fill=fill,
                         outline=color, width=max(2,int(3*scale)))

def phone(draw, x, y, w=105, h=180, color=INK):
    draw.rounded_rectangle((x,y,x+w,y+h), radius=18, outline=color, width=4)
    draw.rounded_rectangle((x+w*.33,y+10,x+w*.67,y+16), radius=3, fill=color)
    draw.ellipse((x+w*.46,y+h-17,x+w*.54,y+h-9), fill=color)

def chip(draw, x, y, s=130, color=INK):
    draw.rounded_rectangle((x,y,x+s,y+s), radius=14, outline=color, width=4)
    draw.rounded_rectangle((x+28,y+28,x+s-28,y+s-28), radius=9, fill=color)
    for i in range(5):
        q=(i+1)*s/6
        draw.line((x+q,y-14,x+q,y),fill=color,width=3)
        draw.line((x+q,y+s,x+q,y+s+14),fill=color,width=3)
        draw.line((x-14,y+q,x,y+q),fill=color,width=3)
        draw.line((x+s,y+q,x+s+14,y+q),fill=color,width=3)

def cloud(draw, x, y, color=INK):
    draw.ellipse((x+30,y,x+120,y+80), outline=color, width=4)
    draw.ellipse((x,y+35,x+85,y+105), outline=color, width=4)
    draw.ellipse((x+75,y+30,x+170,y+105), outline=color, width=4)
    draw.rectangle((x+35,y+70,x+135,y+108), fill=BG)
    draw.line((x+32,y+106,x+140,y+106),fill=color,width=4)

def arrow(draw, a, b, color=INK, width=5):
    draw.line((*a,*b), fill=color, width=width)
    ang = math.atan2(b[1]-a[1], b[0]-a[0])
    for da in (2.55, -2.55):
        q=(b[0]+22*math.cos(ang+da), b[1]+22*math.sin(ang+da))
        draw.line((*b,*q), fill=color, width=width)

def save(im, n):
    im.save(OUT / f"slide-{n:02d}.png", quality=95)

# 1 — Hook
im,d=canvas(); header(d,1,"the question")
title(d,"WHAT IF ONE\nAI MODEL COULD\nFIT EVERY DEVICE?",130,84)
network(d,540,790,.88,INK,active={(0,1),(1,2),(2,1),(3,0)})
pill(d,(110,1050,345,1114),"PHONE",BLUE,WHITE)
pill(d,(422,1050,658,1114),"EDGE CHIP",ORANGE,WHITE)
pill(d,(734,1050,970,1114),"CLOUD",INK,BG)
text(d,(540,1190),"Train once. Specialize instantly.",30,MUTED,False,anchor="mm")
footer(d); save(im,1)

# 2 — Problem
im,d=canvas(); header(d,2,"the old way")
title(d,"WHY DEPLOYMENT\nGETS EXPENSIVE",145,76)
text(d,(72,340),"A network optimized for one device may be a poor fit for\nanother. Traditional methods repeat architecture search and\ntraining for every new hardware constraint.",29,MUTED,spacing=9)
devices=[(160,"PHONE",BLUE),(490,"EDGE",ORANGE),(820,"CLOUD",INK)]
for x,label,c in devices:
    d.rounded_rectangle((x-105,585,x+105,825),radius=24,outline=c,width=4)
    network(d,x,705,.26,c)
    pill(d,(x-78,850,x+78,904),label,c,WHITE,20)
text(d,(540,985),"SEARCH + TRAIN, REPEATED",30,INK,True,mono=True,anchor="mm")
d.rounded_rectangle((72,1085,1008,1210),radius=22,fill=INK)
text(d,(110,1148),"DESIGN COST",25,BG,True,mono=True,anchor="lm")
text(d,(965,1148),"O(N)",68,LIME,True,mono=True,anchor="rm")
footer(d); save(im,2)

# 3 — Flip
im,d=canvas(); header(d,3,"the reversal")
title(d,"ONE TRAINING RUN,\nMANY SUBNETWORKS",145,76)
text(d,(72,340),"Once-for-All trains a large network whose weights can be\nshared by many smaller architectures. Each subnetwork uses a\ndifferent portion of the same learned parameters.",29,MUTED,spacing=9)
pill(d,(72,505,360,575),"TRAIN ONCE",INK,BG,26)
arrow(d,(380,540),(610,540),BLUE,6)
text(d,(720,540),">10¹⁹",82,ORANGE,True,anchor="mm")
text(d,(720,610),"possible configurations",25,MUTED,anchor="mm")
network(d,540,870,.72,BLUE,active={(0,0),(1,1),(1,3),(2,2),(3,0)})
text(d,(540,1115),"The architecture changes. The weights are shared.",31,INK,True,anchor="mm")
footer(d); save(im,3)

# 4 — Elastic dimensions
im,d=canvas(); header(d,4,"how it bends")
title(d,"WHAT MAKES THE\nNETWORK ELASTIC?",145,76)
text(d,(72,340),"OFA varies four architectural dimensions. Together, they\ncontrol how much computation a subnetwork needs and how well\nit can match a particular device.",29,MUTED,spacing=9)
rows=[("DEPTH","2  ·  3  ·  4",.35,BLUE),
      ("WIDTH","3  ·  4  ·  6",.68,ORANGE),
      ("KERNEL","3  ·  5  ·  7",.50,INK),
      ("RESOLUTION","128  →  224",.82,LIME)]
for i,(lab,val,pos,c) in enumerate(rows):
    y=540+i*145
    text(d,(72,y),lab,24,MUTED,True,mono=True)
    text(d,(1008,y),val,28,INK,True,mono=True,anchor="ra")
    d.line((72,y+62,1008,y+62),fill=GRID,width=8)
    d.line((72,y+62,72+(936*pos),y+62),fill=c,width=8)
    x=72+936*pos
    d.ellipse((x-18,y+44,x+18,y+80),fill=c,outline=BG,width=3)
text(d,(72,1170),"These choices define the family of available models.",30,INK,True)
footer(d); save(im,4)

# 5 — Interference
im,d=canvas(); header(d,5,"the hard part")
title(d,"WHY NOT TRAIN EVERY\nSIZE AT THE SAME TIME?",145,68)
text(d,(72,340),"Because the subnetworks share weights, their updates can pull\nthose weights in different directions. Randomly sampling every\nconfiguration from the start caused a noticeable loss in accuracy.",29,MUTED,spacing=9)
points=[(180,650),(330,560),(480,720),(620,540),(760,705),(900,600)]
for i,a in enumerate(points):
    for b in points[i+1:]:
        d.line((*a,*b),fill=GRID,width=3)
for i,(x,y) in enumerate(points):
    c=[BLUE,ORANGE,INK][i%3]
    d.ellipse((x-30,y-30,x+30,y+30),fill=BG,outline=c,width=7)
    text(d,(x,y),str(i+1),21,c,True,mono=True,anchor="mm")
arrow(d,(540,820),(540,960),ORANGE,7)
pill(d,(310,995,770,1075),"ACCURACY ↓",ORANGE,WHITE,34)
text(d,(540,1150),"The training process needs a deliberate order.",31,INK,True,anchor="mm")
footer(d); save(im,5)

# 6 — Progressive shrinking
im,d=canvas(); header(d,6,"the fix")
title(d,"PROGRESSIVE\nSHRINKING",145,84)
text(d,(72,340),"The authors first train the largest network. Smaller choices are\nthen introduced gradually, allowing them to inherit useful weights\nfrom a model that already performs well.",29,MUTED,spacing=9)
steps=[("1","FULL MODEL","learn the strongest representation",INK),
       ("2","KERNEL","7 → 5 → 3",BLUE),
       ("3","DEPTH","4 → 3 → 2",ORANGE),
       ("4","WIDTH","6 → 4 → 3",INK)]
for i,(n,lab,sub,c) in enumerate(steps):
    y=510+i*150
    d.rounded_rectangle((72,y,1008,y+112),radius=22,fill=c)
    text(d,(112,y+56),n,27,BG if c!=LIME else INK,True,mono=True,anchor="lm")
    text(d,(188,y+40),lab,30,BG,True,mono=True,anchor="lm")
    text(d,(188,y+77),sub,22,BG,False,anchor="lm")
    if i<3: arrow(d,(540,y+115),(540,y+143),c,4)
text(d,(72,1145),"Knowledge distillation also helps the large model teach the smaller ones.",26,INK,True)
footer(d); save(im,6)

# 7 — Deployment flow
im,d=canvas(); header(d,7,"specialize")
title(d,"SPECIALIZING FOR\nA PARTICULAR DEVICE",145,70)
text(d,(72,340),"Given a target device and latency budget, predictors estimate\nthe accuracy and speed of candidate subnetworks. A lightweight\nsearch then selects the best match without another training run.",29,MUTED,spacing=9)
phone(d,95,470,110,185,BLUE); chip(d,470,500,130,ORANGE); cloud(d,825,500,INK)
for x,lab in [(150,"PHONE"),(535,"EDGE"),(910,"CLOUD")]:
    text(d,(x,710),lab,22,MUTED,True,mono=True,anchor="mm")
arrow(d,(150,770),(470,900),GRID,5); arrow(d,(535,770),(535,900),GRID,5); arrow(d,(910,770),(600,900),GRID,5)
d.rounded_rectangle((310,900,760,1010),radius=24,fill=INK)
text(d,(535,955),"PREDICT → SEARCH → SELECT",24,LIME,True,mono=True,anchor="mm")
text(d,(540,1090),"The selected subnetwork is ready to deploy.",34,INK,True,anchor="mm")
text(d,(540,1150),"The paper reports up to 1.5× faster inference than MobileNetV3 at equal accuracy.",21,MUTED,anchor="mm")
footer(d); save(im,7)

# 8 — Payoff
im,d=canvas(); header(d,8,"the takeaway")
title(d,"WHAT ONCE-FOR-ALL\nCHANGES IN PRACTICE",145,68)
text(d,(72,330),"Training is paid for once, while specialization becomes a small\nsearch problem. As more deployment scenarios are added, the\nexpensive part of the workflow no longer repeats.",29,MUTED,spacing=9)
d.rounded_rectangle((72,520,1008,700),radius=28,fill=INK)
text(d,(120,610),"O(N)",62,BG,True,mono=True,anchor="lm")
arrow(d,(360,610),(660,610),LIME,7)
text(d,(950,610),"O(1)",62,LIME,True,mono=True,anchor="rm")
text(d,(72,775),"16×–1300×",72,ORANGE,True)
text(d,(72,860),"reported reduction in design cost across deployment scenarios",27,INK,True)
text(d,(72,1000),"A useful way to think about OFA:",23,MUTED,True,mono=True)
text(d,(72,1055),"It does not train one final model. It trains a\nfamily from which the final model can be selected.",34,INK,True,spacing=8)
footer(d,"SAVE · SHARE"); save(im,8)

# Contact sheet
thumbs=[]
for i in range(1,9):
    im=Image.open(OUT/f"slide-{i:02d}.png")
    im.thumbnail((270,338))
    thumbs.append(im.copy())
sheet=Image.new("RGB",(1080,676),"#D8D3C8")
for i,im in enumerate(thumbs): sheet.paste(im,((i%4)*270,(i//4)*338))
sheet.save(OUT/"contact-sheet.png")

# Multipage PDF preview
pages=[Image.open(OUT/f"slide-{i:02d}.png").convert("RGB") for i in range(1,9)]
pages[0].save(OUT/"once-for-all-carousel.pdf",save_all=True,append_images=pages[1:],resolution=144)

print(OUT.resolve())
