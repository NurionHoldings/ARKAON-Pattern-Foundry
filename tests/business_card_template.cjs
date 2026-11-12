const assert=require('node:assert/strict');const fs=require('node:fs');const {compose,documentHtml}=require('../services/business-card-template.js');
const palettes=[['#ffffff','#203c55','#2686a4'],['#171b23','#f1dfb9','#bd9551'],['#194e4a','#fff9eb','#c5b27d'],['#faf8f1','#222b31','#697d80'],['#e5e8ed','#192534','#4774aa'],['#16366a','#ffffff','#68d9f0'],['#ffffff','#293b43','#399899'],['#542e3b','#f7eede','#c1a57e'],['#fffaf3','#34312c','#e78335'],['#e6dcef','#423554','#8a6eab'],['#e8dfcd','#434b39','#839174'],['#eeeae2','#20282b','#8b806e']];
for(let i=0;i<12;i++){
 const source=fs.readFileSync(`assets/business-card-templates/arkaon-${String(i+1).padStart(2,'0')}.svg`,'utf8');const [background,ink,accent]=palettes[i],palette={background,ink,accent};
 const result=compose(source,{businessName:'<script>alert(1)</script>',personName:'홍길동 & 수정',role:'대표',tagline:'테스트',website:'example.test',address:'서울',addressDetail:'사무실',email:'test@example.test',phone:'010-0000-0000',background:'#123456',ink:'#ffffff',accent:'#abcdef'},palette);
 assert.ok(!result.includes('<script>'));assert.ok(result.includes('&lt;script&gt;'));assert.ok(result.includes('홍길동 &amp; 수정'));assert.ok(result.includes('test@example.test'));assert.ok(result.includes('#123456'));assert.ok(result.includes('#abcdef'));assert.ok(documentHtml(result).includes(result));
}
console.log('PASS: all 12 selected templates, content replacement, XML escaping, contact details, palette and export parity');
