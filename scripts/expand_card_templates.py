"""Generate additional original card layouts; keep editable faces explicit."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for p in (ROOT/'assets/business-card-templates').glob('*.svg'):
 s=p.read_text().replace('<g transform="translate(45 70)">','<g data-card-face="front" transform="translate(45 70)">').replace('<g transform="translate(405 290)">','<g data-card-face="back" transform="translate(405 290)">')
 p.write_text(s)
styles=[('13','센터 심벌','#f7f8fa','#22324a','#536cb7','center'),('14','사이드 밴드','#ffffff','#273b39','#246f61','band'),('15','상단 리본','#fff9ee','#493c2f','#c47540','ribbon'),('16','에디토리얼','#eee9df','#2d302c','#8d7160','editorial'),('17','테크 그리드','#101d31','#edf5ff','#73aeda','grid'),('18','소프트 아치','#e3e9e2','#314c40','#7c9b87','arch'),('19','건축 라인','#f5f5f2','#27313a','#9b8863','architect'),('20','시그니처','#fffaf6','#5b3944','#a86c7d','signature'),('21','세로 화이트','#ffffff','#273747','#4685a4','portrait'),('22','세로 다크','#1d2928','#f2eee4','#c8af7b','portrait'),('23','볼드 하프','#233c53','#ffffff','#9fc5cb','half'),('24','넘버 인덱스','#f2eee5','#252f30','#b16a48','index')]
for num,label,bg,ink,accent,kind in styles:
 w,h=(305,550) if kind=='portrait' else (550,305)
 def text(x,y,content,size=16,weight=400,anchor='start'):
  return f'<text x="{x}" y="{y}" fill="{ink}" font-family="Noto Sans CJK KR,sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{content}</text>'
 base=f'<rect width="{w}" height="{h}" fill="{bg}"/>'
 deco=''
 if kind=='center':deco=f'<circle cx="275" cy="80" r="30" fill="none" stroke="{accent}" stroke-width="2"/>'
 elif kind=='band':deco=f'<rect width="80" height="305" fill="{accent}"/><path d="M20 150H60" stroke="{bg}" stroke-width="3"/>'
 elif kind=='ribbon':deco=f'<path d="M0 0H550V50L275 72L0 50Z" fill="{accent}"/>'
 elif kind=='editorial':deco=f'<path d="M30 35H520M30 270H520" stroke="{accent}" stroke-width="2"/>'
 elif kind=='grid':deco=''.join(f'<path d="M{x} 0V305" stroke="{accent}" opacity=".12"/>' for x in range(0,551,35))+''.join(f'<path d="M0 {y}H550" stroke="{accent}" opacity=".12"/>' for y in range(0,306,35))
 elif kind=='arch':deco=f'<path d="M365 305V120A90 90 0 0 1 545 120V305Z" fill="{accent}" opacity=".3"/>'
 elif kind=='architect':deco=f'<path d="M380 260V65H510V260M398 260V95H490V260M30 260H520" fill="none" stroke="{accent}" stroke-width="2"/>'
 elif kind=='signature':deco=f'<path d="M35 220C95 130 150 280 225 198S340 160 400 220" fill="none" stroke="{accent}" stroke-width="3"/>'
 elif kind=='portrait':deco=f'<rect x="25" y="25" width="255" height="500" fill="none" stroke="{accent}"/><circle cx="152" cy="125" r="40" fill="none" stroke="{accent}" stroke-width="2"/>'
 elif kind=='half':deco=f'<path d="M360 0H550V305H430L300 0" fill="{accent}" opacity=".5"/>'
 elif kind=='index':deco=f'<text x="365" y="235" fill="{accent}" opacity=".2" font-family="sans-serif" font-size="170" font-weight="700">01</text>'
 if kind=='portrait':
  front=base+deco+text(152,140,'A',45,500,'middle')+text(152,250,'(주)아르카온',26,700,'middle')+text(152,282,'ARKAON',12,500,'middle')+text(152,450,'상상에 형태를. 가능성에 생명력을.',9,400,'middle')
  back=base+f'<rect y="0" width="305" height="12" fill="{accent}"/>'+text(30,80,'(주)아르카온',22,700)+text(30,170,'홍길동',32,700)+text(30,201,'담당자 · 이름 표기 예시',12)+text(30,310,'www.아르카온.com',14)+text(30,353,'서울 서초구 방배동 952-2',12)+text(30,378,'디엠그레이스서초 1102호',12)
 else:
  x=115 if kind=='band' else 40
  if kind=='center':front=base+deco+text(275,91,'A',28,500,'middle')+text(275,171,'(주)아르카온',34,700,'middle')+text(275,202,'ARKAON',13,500,'middle')+text(275,260,'상상에 형태를. 가능성에 생명력을.',12,400,'middle')
  else:front=base+deco+text(x,118,'ARKAON',17,600)+text(x,170,'(주)아르카온',34,700)+text(x,244,'상상에 형태를. 가능성에 생명력을.',11)
  back=base+f'<rect x="{w-12}" width="12" height="{h}" fill="{accent}"/>'+text(35,55,'(주)아르카온',20,700)+text(35,125,'홍길동',31,700)+text(35,150,'담당자 · 이름 표기 예시',12)+f'<path d="M35 174H510" stroke="{accent}"/>'+text(35,205,'www.아르카온.com',13)+text(35,235,'서울 서초구 방배동 952-2',11)+text(35,257,'디엠그레이스서초 1102호',11)
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1000 650" data-face-width="{w}" data-face-height="{h}" data-contact-x="{30 if kind=="portrait" else 305}" data-contact-y="{440 if kind=="portrait" else 205}"><rect width="1000" height="650" fill="#d8d7d2"/><text x="40" y="35" font-family="Noto Sans CJK KR,sans-serif" font-size="17" fill="#303e39">{num} · {label}</text><g data-card-face="front" transform="translate({80 if kind=="portrait" else 45} 65)">{front}</g><g data-card-face="back" transform="translate({560 if kind=="portrait" else 405} {65 if kind=="portrait" else 290})">{back}</g></svg>'
 (ROOT/f'assets/business-card-templates/arkaon-{num}.svg').write_text(svg)
