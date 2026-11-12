"""Generate an original 100-design catalog for the editable card workspace."""
from pathlib import Path
import ast,json,re
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'services/business-card-editor.js').read_text()
old=(ROOT/'services/business-card-catalog.js')
if old.exists():
 payload=old.read_text();catalog=json.loads(re.search(r'return (\[.*\]);\}\);',payload).group(1))[:24]
else:
 labels=ast.literal_eval(re.search(r'const labels=(\[.*?\]);',source).group(1))
 colors=ast.literal_eval(re.search(r'const palettes=(\[.*?\])\.map',source).group(1))
 catalog=[{'id':i+1,'name':label,'category':'portrait' if i in (20,21) else 'premium' if i in (1,7,11) else 'tech' if i in (5,16) else 'creative' if i in (8,9,17,19) else 'corporate','palette':dict(zip(['background','ink','accent'],colors[i]))} for i,label in enumerate(labels)]
industries=['플랫폼·IT','법률·전문직','건축·공간','디자인 스튜디오','카페·라이프','뷰티·케어','경영 컨설팅','교육·강사','사진·미디어','브랜드 오피스']
layouts=['심벌 좌측형','센터 로고형','투톤 패널형','라운드 프레임형','테크 라인형','대각 포인트형','세로 에디션','컬러 탑바형','사이드 아치형','세로 네임형']
colors=[('#f5f8fb','#203549','#37798c'),('#1c2534','#f5eee0','#c5a16e'),('#f3f0e9','#3f4239','#818a68'),('#ece5f1','#41374d','#9975a5'),('#f5e4d4','#533f31','#b77d50'),('#f2e2e5','#563949','#b2758a'),('#e0e8e7','#263f42','#5d8a90'),('#e7edf6','#243956','#6885bc'),('#f4efe5','#36332e','#9f8960'),('#174c45','#f6f2df','#b5b984')]
for idx in range(24,100):
 n=idx+1;j=idx-24;kind=j%10;industry=industries[(j//10+kind)%10];bg,ink,accent=colors[(j//10+kind*3)%10];portrait=kind in (6,9)
 w,h=(305,550) if portrait else (550,305)
 label=f'{industry} · {layouts[kind]}'
 category='portrait' if portrait else ['tech','premium','corporate','creative','service','service','corporate','corporate','creative','corporate'][(j//10+kind)%10]
 def text(x,y,value,size=15,weight=500,anchor='start'):
  return f'<text x="{x}" y="{y}" fill="{ink}" font-family="Noto Sans CJK KR,Malgun Gothic,sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{value}</text>'
 base=f'<rect width="{w}" height="{h}" rx="{12 if kind==3 else 0}" fill="{bg}"/>'
 # The mark family changes with each series, in addition to layout and palette.
 mark=[f'<circle cx="80" cy="80" r="25" fill="none" stroke="{accent}" stroke-width="3"/>',f'<path d="M55 103L80 53L105 103Z" fill="none" stroke="{accent}" stroke-width="3"/>',f'<path d="M55 80L80 55L105 80L80 105Z" fill="{accent}"/>',f'<path d="M52 80Q66 45 80 80T108 80M52 93Q66 58 80 93T108 93" fill="none" stroke="{accent}" stroke-width="3"/>'][(j//10)%4]
 if portrait:
  deco=f'<rect x="20" y="20" width="265" height="510" rx="{18 if kind==9 else 0}" fill="none" stroke="{accent}" stroke-width="2"/>'
  front=base+deco+f'<path d="M125 120L152 65L180 120M138 95H166" fill="none" stroke="{accent}" stroke-width="3"/>'+text(152,260,'(주)아르카온',25,700,'middle')+text(152,292,'ARKAON',12,600,'middle')+text(152,457,'상상에 형태를. 가능성에 생명력을.',9,500,'middle')
  back=base+f'<rect x="0" y="0" width="305" height="16" fill="{accent}"/>'+text(30,77,'(주)아르카온',22,700)+text(30,185,'홍길동',31,700)+text(30,213,'담당자 · 이름 표기 예시',12)+text(30,310,'www.아르카온.com',13)+text(30,354,'서울 서초구 방배동 952-2',11)+text(30,378,'디엠그레이스서초 1102호',11)
 elif kind==1:
  front=base+f'<circle cx="275" cy="83" r="36" fill="{accent}" opacity=".25"/>'+text(275,96,'A',35,600,'middle')+text(275,174,'(주)아르카온',34,700,'middle')+text(275,203,'ARKAON',13,600,'middle')+text(275,266,'상상에 형태를. 가능성에 생명력을.',11,500,'middle')
 elif kind==2:
  front=base+f'<rect x="0" width="190" height="305" fill="{accent}"/>'+text(230,136,'(주)아르카온',28,700)+text(230,167,'ARKAON',13,600)+text(230,232,'상상에 형태를. 가능성에 생명력을.',9)
 elif kind==3:
  front=base+f'<rect x="20" y="20" width="510" height="265" rx="30" fill="none" stroke="{accent}" stroke-width="2"/>'+mark+text(45,169,'(주)아르카온',33,700)+text(45,198,'ARKAON',12,600)+text(45,251,'상상에 형태를. 가능성에 생명력을.',11)
 else:
  deco=''
  if kind==4:deco=''.join(f'<path d="M{x} 25V280" stroke="{accent}" opacity=".2"/>' for x in range(350,521,34))+f'<path d="M335 50H525M335 130H525M335 210H525" stroke="{accent}" opacity=".3"/>'
  if kind==5:deco=f'<path d="M405 0H550V305H480L330 0" fill="{accent}" opacity=".5"/>'
  if kind==7:deco=f'<rect width="550" height="45" fill="{accent}"/><rect y="290" width="550" height="15" fill="{accent}"/>'
  if kind==8:deco=f'<path d="M365 305V140A90 90 0 0 1 545 140V305Z" fill="{accent}" opacity=".3"/>'
  front=base+deco+(mark if kind==0 else '')+text(40,169,'(주)아르카온',34,700)+text(42,199,'ARKAON',12,600)+text(42,258,'상상에 형태를. 가능성에 생명력을.',11)
 if not portrait:
  # Three distinct information compositions retain clear contact space.
  variant=(j//10)%3
  if variant==1:
   back=base+f'<rect x="0" width="18" height="305" fill="{accent}"/>'+text(35,55,'(주)아르카온',21,700)+text(35,121,'홍길동',32,700)+text(35,149,'담당자 · 이름 표기 예시',12)+f'<path d="M35 170H510" stroke="{accent}"/>'+text(35,201,'www.아르카온.com',12)+text(35,234,'서울 서초구 방배동 952-2',11)+text(35,257,'디엠그레이스서초 1102호',11)
  elif variant==2:
   back=base+f'<rect width="550" height="12" fill="{accent}"/>'+text(35,62,'홍길동',31,700)+text(35,88,'담당자 · 이름 표기 예시',11)+text(295,62,'(주)아르카온',21,700)+f'<path d="M35 121H510" stroke="{accent}"/>'+text(35,166,'www.아르카온.com',12)+text(35,213,'서울 서초구 방배동 952-2',11)+text(35,237,'디엠그레이스서초 1102호',11)
  else:
   back=base+f'<rect x="520" width="30" height="305" fill="{accent}"/>'+text(35,55,'(주)아르카온',21,700)+text(35,125,'홍길동',32,700)+text(35,151,'담당자 · 이름 표기 예시',12)+text(35,207,'www.아르카온.com',12)+text(35,235,'서울 서초구 방배동 952-2',11)+text(35,258,'디엠그레이스서초 1102호',11)
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1000 650" data-face-width="{w}" data-face-height="{h}" data-contact-x="{30 if portrait else 295}" data-contact-y="{440 if portrait else 207}"><rect width="1000" height="650" fill="#d8d7d2"/><text x="35" y="35" font-family="Noto Sans CJK KR,sans-serif" font-size="17" fill="#303e39">{n:02d} · {label}</text><g data-card-face="front" transform="translate({70 if portrait else 45} 65)">{front}</g><g data-card-face="back" transform="translate({560 if portrait else 405} {65 if portrait else 290})">{back}</g></svg>'
 (ROOT/f'assets/business-card-templates/arkaon-{n:02d}.svg').write_text(svg)
 catalog.append({'id':n,'name':label,'category':category,'palette':{'background':bg,'ink':ink,'accent':accent}})
(ROOT/'services/business-card-catalog.js').write_text('(function(root,factory){const api=factory();if(typeof module===\'object\'&&module.exports)module.exports=api;else root.APFCardCatalog=api;})(typeof window===\'undefined\'?globalThis:window,()=>{return '+json.dumps(catalog,ensure_ascii=False,separators=(',',':'))+';});\n')
print('100 original editable templates and catalog ready')
