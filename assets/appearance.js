/* Browser-local appearance preferences, restricted to validated color values. */
(() => {
  document.body.classList.add('appearance-workspace');
  const key='apf.appearance.v1';
  const defaults={background:'#c3c1bb',page:'#c3c1bb',panel:'#fffdf8',button:'#194e4a'};
  const valid=value=>typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value);
  const ink=color=>{const v=color.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);const l=v[0]*.2126+v[1]*.7152+v[2]*.0722;return (l+.05)/.05>=1.05/(l+.05)?'#000000':'#ffffff';};
  function sanitize(value){if(!value||typeof value!=='object')return null;return ['background','panel','button'].every(k=>valid(value[k]))?Object.fromEntries(Object.keys(defaults).map(k=>[k,valid(value[k])?value[k]:value.background])):null;}
  let saved=null;try{saved=sanitize(JSON.parse(localStorage.getItem(key)));}catch{/* optional storage */}
  function apply(colors){const root=document.documentElement;root.toggleAttribute('data-custom-appearance',!!colors);if(!colors)return;const lightPanel=ink(colors.panel)==='#000000';root.style.setProperty('--appearance-logo-filter',lightPanel?'invert(1) hue-rotate(180deg)':'none');root.style.setProperty('--appearance-logo-blend',lightPanel?'multiply':'screen');for(const [name,color]of Object.entries(colors)){root.style.setProperty(`--appearance-${name}`,color);root.style.setProperty(`--appearance-${name}-ink`,ink(color));}}
  apply(saved);
  const button=document.createElement('button');button.type='button';button.className='appearance-toggle';button.textContent='화면 색상';button.setAttribute('aria-haspopup','dialog');
  const dialog=document.createElement('dialog');dialog.className='appearance-dialog';dialog.setAttribute('aria-labelledby','appearanceHeading');
  const heading=document.createElement('h2');heading.id='appearanceHeading';heading.textContent='나만의 화면 색상';
  const note=document.createElement('p');note.textContent='이 브라우저의 아르카온 화면에 적용합니다. 제작물의 색상은 제작 화면에서 별도로 선택하세요.';
  const inputs={};dialog.append(heading,note);
  for(const [name,labelText]of Object.entries({background:'플랫폼 전체 바탕',page:'페이지 작업 배경',panel:'패널·메뉴 영역',button:'메뉴·실행 버튼'})){const label=document.createElement('label');label.textContent=labelText;const input=document.createElement('input');input.type='color';input.value=(saved||defaults)[name];input.id=`appearance-${name}`;label.append(input);dialog.append(label);inputs[name]=input;}
  const status=document.createElement('p');status.setAttribute('role','status');
  const actions=document.createElement('div');actions.className='appearance-actions';
  for(const [text,handler]of [
    ['적용·저장',()=>{const colors=sanitize(Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value])));if(!colors)return;apply(colors);try{localStorage.setItem(key,JSON.stringify(colors));saved=colors;status.textContent='저장했습니다. 다른 페이지에도 같은 색상이 적용됩니다.';}catch{status.textContent='현재 화면에 적용했지만 저장하지 못했습니다. 브라우저 저장 설정을 확인해 주세요.';}}],
    ['기본 색상 복원',()=>{apply(null);saved=null;Object.entries(inputs).forEach(([k,v])=>{v.value=defaults[k];});try{localStorage.removeItem(key);status.textContent='기본 색상으로 복원했습니다.';}catch{status.textContent='화면은 복원했지만 저장된 설정을 지우지 못했습니다.';}}],
    ['닫기',()=>dialog.close()]
  ]){const action=document.createElement('button');action.type='button';action.textContent=text;action.addEventListener('click',handler);actions.append(action);}
  dialog.append(actions,status);document.body.append(button,dialog);button.addEventListener('click',()=>{status.textContent='';dialog.showModal();});
})();
