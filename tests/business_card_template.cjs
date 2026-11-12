const assert=require('node:assert/strict');const fs=require('node:fs');const {compose,documentHtml}=require('../services/business-card-template.js');
const palettes=[['#ffffff','#203c55','#2686a4'],['#171b23','#f1dfb9','#bd9551'],['#194e4a','#fff9eb','#c5b27d'],['#faf8f1','#222b31','#697d80'],['#e5e8ed','#192534','#4774aa'],['#16366a','#ffffff','#68d9f0'],['#ffffff','#293b43','#399899'],['#542e3b','#f7eede','#c1a57e'],['#fffaf3','#34312c','#e78335'],['#e6dcef','#423554','#8a6eab'],['#e8dfcd','#434b39','#839174'],['#eeeae2','#20282b','#8b806e']];
for(let i=0;i<12;i++){
 const source=fs.readFileSync(`assets/business-card-templates/arkaon-${String(i+1).padStart(2,'0')}.svg`,'utf8');const [background,ink,accent]=palettes[i],palette={background,ink,accent};
 const result=compose(source,{businessName:'<script>alert(1)</script>',personName:'홍길동 & 수정',role:'대표',tagline:'테스트',website:'example.test',address:'서울',addressDetail:'사무실',email:'test@example.test',phone:'010-0000-0000',background:'#123456',ink:'#ffffff',accent:'#abcdef'},palette);
 assert.ok(!result.includes('<script>'));assert.ok(result.includes('&lt;script&gt;'));assert.ok(result.includes('홍길동 &amp; 수정'));assert.ok(result.includes('test@example.test'));assert.ok(result.includes('#123456'));assert.ok(result.includes('#abcdef'));assert.ok(documentHtml(result).includes(result));
}
console.log('PASS: all 12 selected templates, content replacement, XML escaping, contact details, palette and export parity');
const newPalettes=[['#f7f8fa','#22324a','#536cb7'],['#ffffff','#273b39','#246f61'],['#fff9ee','#493c2f','#c47540'],['#eee9df','#2d302c','#8d7160'],['#101d31','#edf5ff','#73aeda'],['#e3e9e2','#314c40','#7c9b87'],['#f5f5f2','#27313a','#9b8863'],['#fffaf6','#5b3944','#a86c7d'],['#ffffff','#273747','#4685a4'],['#1d2928','#f2eee4','#c8af7b'],['#233c53','#ffffff','#9fc5cb'],['#f2eee5','#252f30','#b16a48']];
const {faceSvg}=require('../services/business-card-template.js');
for(let i=0;i<24;i++){
 const [background,ink,accent]=[...palettes,...newPalettes][i],palette={background,ink,accent};const source=fs.readFileSync(`assets/business-card-templates/arkaon-${String(i+1).padStart(2,'0')}.svg`,'utf8');
 const values={...palette,businessName:'(주)아르카온',personName:'홍길동 수정',role:'대표',tagline:'소개',website:'example.test',address:'서울',addressDetail:'1102호',email:'test@example.test',phone:'010-0000-0000'};
 const single=compose(source,{...values,sides:'single'},palette),double=compose(source,{...values,sides:'double'},palette);
 assert.equal((single.match(/data-card-rendered=/g)||[]).length,1);assert.equal((double.match(/data-card-rendered=/g)||[]).length,2);
 assert.ok(single.includes('홍길동 수정'));assert.ok(single.includes('test@example.test'));assert.equal(faceSvg(single,'back'),'');assert.ok(faceSvg(single,'front').includes('<rect'));
 assert.ok(faceSvg(double,'front').includes('(주)아르카온'));assert.ok(!faceSvg(double,'front').includes('test@example.test'));assert.ok(faceSvg(double,'back').includes('test@example.test'));
 assert.ok(documentHtml(double).includes('<h2>앞면</h2>'));assert.ok(documentHtml(double).includes('<h2>뒷면</h2>'));assert.ok(!documentHtml(single).includes('<h2>뒷면</h2>'));
 if(i===20||i===21)assert.ok(faceSvg(double,'back').includes('viewBox="0 0 305 550"'));
}
console.log('PASS: 24 layouts, single/double face counts, contact retention, separate exports, portrait dimensions');
