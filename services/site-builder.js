(() => {
  const {downloadText,saveProject,readProjects}=APFHomeServices;
  const {compose,normalize,presets}=APFDesignComposer;
  const fields=['title','tagline','body','email','phone','accent','style','layout','motion'];
  const status=document.getElementById('designStatus');
  const values=()=>Object.fromEntries(fields.map(id=>[id,document.getElementById(id).value]));
  const render=()=>{document.getElementById('preview').srcdoc=compose(values());};
  fields.forEach(id=>document.getElementById(id).addEventListener('input',()=>{
    if(id==='style')document.getElementById('accent').value=presets[document.getElementById('style').value].accent;
    render();
    status.textContent='선택한 설정을 미리보기에 반영했습니다. 저장하면 같은 HTML을 내보냅니다.';
  }));
  document.getElementById('loadDesign').addEventListener('click',()=>{
    const saved=readProjects().find(item=>item.type==='site'&&item.designVersion===1&&item.designInput);
    if(!saved){status.textContent='불러올 새 형식의 홈페이지 설정이 없습니다.';return;}
    if(!confirm('현재 입력을 최근 저장한 홈페이지 설정으로 바꿀까요?'))return;
    const v=normalize(saved.designInput);fields.forEach(id=>{document.getElementById(id).value=v[id];});render();
    status.textContent='저장한 설정을 불러왔습니다. 수정 후 저장하면 새 작업으로 남습니다.';
  });
  document.getElementById('form').addEventListener('submit',event=>{
    event.preventDefault();const v=normalize(values());
    if(!v.title.trim()){status.textContent='사이트 이름을 입력해 주세요. 공백만으로는 저장할 수 없습니다.';document.getElementById('title').focus();return;}
    const html=compose(v);
    try{saveProject({type:'site',title:v.title,html,designVersion:1,designInput:v});}
    catch{status.textContent='브라우저 저장에 실패했습니다. 입력은 유지됩니다. 저장 공간과 브라우저 설정을 확인해 주세요.';return;}
    downloadText(`${v.title}-home.html`,html);status.textContent='내 작업에 저장하고 같은 HTML 파일을 내보냈습니다. 게시 화면에서 이어갈 수 있습니다.';
  });
  render();
})();
